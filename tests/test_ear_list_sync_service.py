"""Tests for the official U.S. screening list synchronization service."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from pathlib import Path

import pytest

from app.services import ear_list_sync_service as sync_service
from app.services import screening_service


SAMPLE_HEADERS = [
    "_id",
    "source",
    "entity_number",
    "type",
    "name",
    "addresses",
    "federal_register_notice",
    "start_date",
    "end_date",
    "license_requirement",
    "license_policy",
    "remarks",
    "source_list_url",
    "alt_names",
    "source_information_url",
]


def make_csl_csv(rows: list[dict]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=SAMPLE_HEADERS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def sample_rows() -> list[dict]:
    return [
        {
            "source": "Entity List (EL) - Bureau of Industry and Security",
            "name": "Northstar Dynamics Ltd.",
            "addresses": "12 King Street, London, GB",
            "federal_register_notice": "90 FR 10001",
            "license_requirement": "For all items subject to the EAR.",
            "alt_names": "Northstar Dynamics; NDS Limited",
            "source_information_url": "https://www.bis.gov/example",
        },
        {
            "source": "Denied Persons List (DPL) - Bureau of Industry and Security",
            "name": "Aurora Global Trading FZE",
            "addresses": "Plot 4, Jebel Ali Free Zone, Dubai, AE",
            "federal_register_notice": "91 FR 20002",
            "license_policy": "Presumption of denial.",
            "source_information_url": "https://www.bis.gov/example",
        },
        {
            "source": "Unverified List (UVL) - Bureau of Industry and Security",
            "name": "Pacific Meridian Industries LLC",
            "addresses": "",
            "alt_names": "PMI",
            "source_information_url": "https://www.bis.gov/example",
        },
        {
            "source": "Military End User (MEU) List - Bureau of Industry and Security",
            "name": "Vector Semiconductor Technology Inc.",
            "addresses": "Hsinchu Science Park, Hsinchu, TW",
            "source_information_url": "https://www.bis.gov/example",
        },
        {
            "source": "Specially Designated Nationals (SDN) - Treasury Department",
            "name": "Some OFAC Entity",
            "addresses": "Tehran, IR",
            "entity_number": "99999",
            "source_information_url": "https://ofac.treasury.gov/example",
        },
    ]


def test_parse_bis_only_filters_other_agencies() -> None:
    dataset = sync_service.parse_csl_dataset(make_csl_csv(sample_rows()))

    assert dataset.total_rows == 5
    assert len(dataset.records) == 4
    codes = [record.source_code for record in dataset.records]
    assert codes == ["EL", "DPL", "UVL", "MEU"]


def test_parse_all_lists_includes_treasury() -> None:
    dataset = sync_service.parse_csl_dataset(make_csl_csv(sample_rows()), include_codes=())
    assert len(dataset.records) == 5
    names = {record.name for record in dataset.records}
    assert "Some OFAC Entity" in names


def test_record_normalization_columns() -> None:
    records = sync_service.parse_csl_csv(make_csl_csv(sample_rows()))
    el = next(record for record in records if record.source_code == "EL")

    assert el.name == "Northstar Dynamics Ltd."
    assert el.aliases == "Northstar Dynamics; NDS Limited"
    assert el.country == "GB"
    assert el.reference == "FR 90 FR 10001"
    assert "License requirement: For all items subject to the EAR." in el.notes
    assert el.key == ("EL", "northstar dynamics ltd")


def test_compare_snapshots_reports_add_remove_and_modified() -> None:
    previous_rows = sample_rows()
    latest_rows = [
        row
        for row in sample_rows()
        if "Military End User" not in row["source"]
        and "Specially Designated" not in row["source"]
    ]
    # Change one DPL detail and add a brand-new EL entry.
    latest_rows[1]["federal_register_notice"] = "92 FR 30003"
    latest_rows.append(
        {
            "source": "Entity List (EL) - Bureau of Industry and Security",
            "name": "Blue Horizon Defense Group",
            "addresses": "Pyongyang, KP",
            "source_information_url": "https://www.bis.gov/example",
        }
    )

    previous = sync_service.parse_csl_csv(make_csl_csv(previous_rows))
    latest = sync_service.parse_csl_csv(make_csl_csv(latest_rows))
    added, removed, modified = sync_service.compare_snapshots(previous, latest)

    assert [record.name for record in added] == ["Blue Horizon Defense Group"]
    assert [record.name for record in removed] == ["Vector Semiconductor Technology Inc."]
    assert len(modified) == 1
    assert modified[0][1].name == "Aurora Global Trading FZE"


def test_fetch_and_compare_and_apply_round_trip(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot.csv"
    update_log = tmp_path / "updates.csv"
    now = datetime(2026, 9, 9, 12, 0, 0)

    def fetcher_first(url: str) -> bytes:
        return make_csl_csv(sample_rows()[:3])

    first = sync_service.fetch_and_compare(
        url="https://example.invalid/csl.csv",
        fetcher=fetcher_first,
        now=now,
        snapshot_path=snapshot,
    )
    assert first.initial_load is True
    assert first.added_count == 3
    assert first.removed_count == 0
    assert first.fetched_total == 3

    sync_service.write_snapshot(first.records, snapshot)
    sync_service.append_update_log(first, update_log)
    assert snapshot.exists()
    with update_log.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = list(csv.DictReader(handle))
    assert reader[0]["action"] == "INITIAL_LOAD"

    # Second fetch: one removed, one added, one unchanged.
    def fetcher_second(url: str) -> bytes:
        rows = sample_rows()[:3]
        rows.pop(1)  # remove DPL row
        rows.append(
            {
                "source": "Entity List (EL) - Bureau of Industry and Security",
                "name": "Newly Added Entity Co.",
                "addresses": "Singapore, SG",
                "source_information_url": "https://www.bis.gov/example",
            }
        )
        return make_csl_csv(rows)

    second = sync_service.fetch_and_compare(
        url="https://example.invalid/csl.csv",
        fetcher=fetcher_second,
        now=now,
        snapshot_path=snapshot,
    )
    assert second.initial_load is False
    assert [record.name for record in second.removed] == ["Aurora Global Trading FZE"]
    assert [record.name for record in second.added] == ["Newly Added Entity Co."]

    sync_service.append_update_log(second, update_log)
    with update_log.open("r", encoding="utf-8-sig", newline="") as handle:
        actions = [row["action"] for row in csv.DictReader(handle)]
    assert actions == ["INITIAL_LOAD", "ADDED", "REMOVED"]


def test_snapshot_round_trips_through_screening_service(tmp_path: Path) -> None:
    records = sync_service.parse_csl_csv(make_csl_csv(sample_rows()))
    snapshot = tmp_path / "reference.csv"
    sync_service.write_snapshot(records, snapshot)

    listed, sources = screening_service.load_restricted_parties([snapshot])
    assert len(listed) == 4
    assert {party.source for party in listed} == {
        "Entity List (EL) - Bureau of Industry and Security",
        "Denied Persons List (DPL) - Bureau of Industry and Security",
        "Unverified List (UVL) - Bureau of Industry and Security",
        "Military End User (MEU) List - Bureau of Industry and Security",
    }


def test_default_source_url_reads_valid_rules_json() -> None:
    url = sync_service.default_source_url()
    assert url.startswith("https://")
    config_path = sync_service.rule_path("ear_sync_sources.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["url"] == url


def test_update_log_csv_bytes_has_expected_headers(tmp_path: Path) -> None:
    rows = sample_rows()
    result = sync_service.SyncResult(
        fetched_at="2026-09-09T12:00:00+08:00",
        url="https://example.invalid/csl.csv",
        fetched_total=len(rows),
        records=sync_service.parse_csl_csv(make_csl_csv(rows)),
        added=sync_service.parse_csl_csv(make_csl_csv([rows[0]])),
        removed=sync_service.parse_csl_csv(make_csl_csv([rows[1]])),
        initial_load=False,
    )
    payload = sync_service.update_log_csv_bytes(result).decode("utf-8-sig")
    reader = list(csv.DictReader(io.StringIO(payload)))
    assert reader[0]["action"] == "ADDED"
    assert reader[1]["action"] == "REMOVED"
    assert set(reader[0]) == set(sync_service.UPDATE_LOG_HEADERS)


def test_snapshot_summary_empty_by_default() -> None:
    summary = sync_service.snapshot_summary()
    assert summary["exists"] is sync_service.SNAPSHOT_FILE.exists()
    if summary["exists"]:
        assert summary["count"] > 0
    else:
        assert summary["count"] == 0
