"""Synchronize EAR-related U.S. Government screening lists into local CSV files.

Primary source: the official U.S. Consolidated Screening List (CSL) CSV published
by the International Trade Administration at data.trade.gov.  The CSL is refreshed
daily and includes the BIS Entity List, Denied Persons List, Unverified List, and
Military End User List, plus lists maintained by the Departments of State and the
Treasury.

The sync never replaces the bundled example list.  It writes two local files:

* ``app/data/ear_synced_lists.csv``        - current snapshot used by screening
* ``app/data/ear_sync_updates.csv``        - append-only log of ADDED/REMOVED/MODIFIED

The results are reference data only.  A match never establishes that a party is
restricted; users must verify identities against the Federal Register and the
source agency lists.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from app.paths import DATA_DIR, rule_path

CSV_HEADERS = ["name", "aliases", "country", "reference", "source", "notes"]
UPDATE_LOG_HEADERS = [
    "synced_at",
    "action",
    "source_list",
    "name",
    "aliases",
    "country",
    "reference",
    "source",
    "notes",
    "detail",
]

SNAPSHOT_FILE = DATA_DIR / "ear_synced_lists.csv"
UPDATE_LOG_FILE = DATA_DIR / "ear_sync_updates.csv"
META_FILE = DATA_DIR / "ear_sync_meta.json"

# Source identifiers and the keywords used to recognize them inside CSL rows.
SOURCE_CODES = {
    "EL": "Entity List",
    "DPL": "Denied Persons List",
    "UVL": "Unverified List",
    "MEU": "Military End User",
}

BIS_ONLY_CODES = ("EL", "DPL", "UVL", "MEU")

_ISO_ALPHA_2 = {
    "AD", "AE", "AF", "AG", "AI", "AL", "AM", "AO", "AQ", "AR", "AS", "AT", "AU",
    "AW", "AX", "AZ", "BA", "BB", "BD", "BE", "BF", "BG", "BH", "BI", "BJ", "BL",
    "BM", "BN", "BO", "BQ", "BR", "BS", "BT", "BV", "BW", "BY", "BZ", "CA", "CC",
    "CD", "CF", "CG", "CH", "CI", "CK", "CL", "CM", "CN", "CO", "CR", "CU", "CV",
    "CW", "CX", "CY", "CZ", "DE", "DJ", "DK", "DM", "DO", "DZ", "EC", "EE", "EG",
    "EH", "ER", "ES", "ET", "FI", "FJ", "FK", "FM", "FO", "FR", "GA", "GB", "GD",
    "GE", "GF", "GG", "GH", "GI", "GL", "GM", "GN", "GP", "GQ", "GR", "GS", "GT",
    "GU", "GW", "GY", "HK", "HM", "HN", "HR", "HT", "HU", "ID", "IE", "IL", "IM",
    "IN", "IO", "IQ", "IR", "IS", "IT", "JE", "JM", "JO", "JP", "KE", "KG", "KH",
    "KI", "KM", "KN", "KP", "KR", "KW", "KY", "KZ", "LA", "LB", "LC", "LI", "LK",
    "LR", "LS", "LT", "LU", "LV", "LY", "MA", "MC", "MD", "ME", "MF", "MG", "MH",
    "MK", "ML", "MM", "MN", "MO", "MP", "MQ", "MR", "MS", "MT", "MU", "MV", "MW",
    "MX", "MY", "MZ", "NA", "NC", "NE", "NF", "NG", "NI", "NL", "NO", "NP", "NR",
    "NU", "NZ", "OM", "PA", "PE", "PF", "PG", "PH", "PK", "PL", "PM", "PN", "PR",
    "PS", "PT", "PW", "PY", "QA", "RE", "RO", "RS", "RU", "RW", "SA", "SB", "SC",
    "SD", "SE", "SG", "SH", "SI", "SJ", "SK", "SL", "SM", "SN", "SO", "SR", "SS",
    "ST", "SV", "SX", "SY", "SZ", "TC", "TD", "TF", "TG", "TH", "TJ", "TK", "TL",
    "TM", "TN", "TO", "TR", "TT", "TV", "TW", "TZ", "UA", "UG", "UM", "US", "UY",
    "UZ", "VA", "VC", "VE", "VG", "VI", "VN", "VU", "WF", "WS", "YE", "YT", "ZA",
    "ZM", "ZW",
}

_COUNTRY_WORD_MAP = {
    "UNITED STATES": "US",
    "UNITED KINGDOM": "GB",
    "UNITED ARAB EMIRATES": "AE",
    "RUSSIA": "RU",
    "HONG KONG": "HK",
    "TAIWAN": "TW",
    "KOREA": "KR",
    "CHINA": "CN",
    "GERMANY": "DE",
    "FRANCE": "FR",
}

_SIGNATURE_COLUMNS = ("aliases", "country", "reference", "notes")


def default_source_url() -> str:
    """Return the configured CSL URL (rules JSON, overridable by env var)."""

    override = os.environ.get("EAR_CSL_URL")
    if override:
        return override
    try:
        config = json.loads(rule_path("ear_sync_sources.json").read_text(encoding="utf-8"))
        url = str(config.get("url") or "").strip()
        if url:
            return url
    except (OSError, ValueError):
        pass
    return "https://data.trade.gov/downloadable_consolidated_screening_list/v1/consolidated.csv"


def http_get_bytes(url: str, timeout: int = 90) -> bytes:
    """Download bytes with a browser-like user agent and safe error handling."""

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) EAR-Review-Tool/1.0",
            "Accept": "text/csv,text/*,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise ConnectionError(
            f"Official CSL server returned HTTP {exc.code} ({exc.reason}). "
            "The daily file may be temporarily unavailable."
        ) from exc
    except urllib.error.URLError as exc:
        raise ConnectionError(
            f"Could not reach the official CSL server: {exc.reason}. "
            "Check your internet connection or proxy settings."
        ) from exc


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    value = unicodedata.normalize("NFKD", str(text))
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.casefold()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return " ".join(value.split())


def source_code_for(source: str | None) -> str:
    """Return the short code (EL/DPL/UVL/MEU) for a CSL source name."""

    text = _normalize(source)
    for code, keyword in SOURCE_CODES.items():
        if _normalize(keyword) in text:
            return code
    return ""


def _country_from_addresses(value: str | None) -> str:
    if not value:
        return ""
    countries: list[str] = []
    for address in str(value).split(";"):
        tail = re.sub(r"\s+", " ", address.strip())
        if not tail:
            continue
        match = re.search(r"([A-Za-z]{2})$", tail)
        if match:
            code = match.group(1).upper()
            if code in _ISO_ALPHA_2:
                countries.append(code)
                continue
        for word, code in _COUNTRY_WORD_MAP.items():
            if tail.upper().endswith(word):
                countries.append(code)
                break
    return ", ".join(dict.fromkeys(countries))


@dataclass(frozen=True)
class EarListRecord:
    """A normalized row compatible with the screening CSV schema."""

    name: str
    aliases: str
    country: str
    reference: str
    source: str
    notes: str

    @property
    def source_code(self) -> str:
        return source_code_for(self.source)

    @property
    def key(self) -> tuple[str, str]:
        identity_source = self.source_code or _normalize(self.source)
        return (identity_source, _normalize(self.name))

    @property
    def signature(self) -> tuple[str, ...]:
        return tuple(_normalize(getattr(self, column)) for column in _SIGNATURE_COLUMNS)

    def as_row(self) -> dict[str, str]:
        return {
            "name": self.name,
            "aliases": self.aliases,
            "country": self.country,
            "reference": self.reference,
            "source": self.source,
            "notes": self.notes,
        }


def _clean_cell(row: dict, key: str) -> str:
    value = row.get(key)
    return "" if value is None else str(value).strip()


def _build_record(row: dict) -> EarListRecord | None:
    name = _clean_cell(row, "name")
    if not name:
        return None
    source = _clean_cell(row, "source")

    reference_parts: list[str] = []
    entity_number = _clean_cell(row, "entity_number")
    if entity_number:
        reference_parts.append(f"CSL ID {entity_number}")
    fr_notice = _clean_cell(row, "federal_register_notice")
    if fr_notice:
        reference_parts.append(f"FR {fr_notice}")
    if not reference_parts:
        list_url = _clean_cell(row, "source_list_url")
        if list_url:
            reference_parts.append(list_url)

    note_parts: list[str] = []
    license_requirement = _clean_cell(row, "license_requirement")
    if license_requirement:
        note_parts.append(f"License requirement: {license_requirement}")
    license_policy = _clean_cell(row, "license_policy")
    if license_policy:
        note_parts.append(f"License policy: {license_policy}")
    remarks = _clean_cell(row, "remarks")
    if remarks:
        note_parts.append(f"Remarks: {remarks}")
    start_date = _clean_cell(row, "start_date")
    if start_date:
        note_parts.append(f"Start: {start_date}")
    end_date = _clean_cell(row, "end_date")
    if end_date:
        note_parts.append(f"End: {end_date}")
    verify_url = _clean_cell(row, "source_information_url")
    if verify_url:
        note_parts.append(f"Verify: {verify_url}")

    notes = " | ".join(note_parts)
    if len(notes) > 1000:
        notes = notes[:997].rstrip() + "..."

    return EarListRecord(
        name=name,
        aliases=_clean_cell(row, "alt_names"),
        country=_country_from_addresses(_clean_cell(row, "addresses")),
        reference="; ".join(reference_parts),
        source=source,
        notes=notes,
    )


def parse_csl_csv(
    raw: bytes,
    include_codes: tuple[str, ...] | list[str] = BIS_ONLY_CODES,
) -> list[EarListRecord]:
    """Parse CSL CSV bytes and return records (filtered to include_codes)."""

    dataset = parse_csl_dataset(raw, include_codes=include_codes)
    return dataset.records


@dataclass
class CslDataset:
    records: list[EarListRecord]
    total_rows: int


def parse_csl_dataset(
    raw: bytes,
    include_codes: tuple[str, ...] | list[str] = BIS_ONLY_CODES,
) -> CslDataset:
    """Parse CSL CSV bytes; include_codes may be empty to keep every list."""

    wanted = {code.upper() for code in include_codes} if include_codes else set()
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("The official file did not contain CSV headers.")

    records: list[EarListRecord] = []
    total_rows = 0
    for row in reader:
        total_rows += 1
        source_code = source_code_for(_clean_cell(row, "source"))
        if wanted and source_code not in wanted:
            continue
        record = _build_record(row)
        if record is not None:
            records.append(record)
    return CslDataset(records=records, total_rows=total_rows)


@dataclass
class SyncResult:
    fetched_at: str
    url: str
    fetched_total: int
    records: list[EarListRecord]
    added: list[EarListRecord] = field(default_factory=list)
    removed: list[EarListRecord] = field(default_factory=list)
    modified: list[tuple[EarListRecord, EarListRecord]] = field(default_factory=list)
    initial_load: bool = False

    @property
    def added_count(self) -> int:
        return len(self.added)

    @property
    def removed_count(self) -> int:
        return len(self.removed)

    @property
    def modified_count(self) -> int:
        return len(self.modified)

    @property
    def record_count(self) -> int:
        return len(self.records)


def _read_snapshot_records(path: Path) -> list[EarListRecord]:
    if not path.exists():
        return []
    records: list[EarListRecord] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(line for line in handle if not line.lstrip().startswith("#"))
        for row in reader:
            name = (row.get("name") or "").strip()
            source = (row.get("source") or "").strip()
            if not name or not source:
                continue
            records.append(
                EarListRecord(
                    name=name,
                    aliases=(row.get("aliases") or "").strip(),
                    country=(row.get("country") or "").strip(),
                    reference=(row.get("reference") or "").strip(),
                    source=source,
                    notes=(row.get("notes") or "").strip(),
                )
            )
    return records


def _index_records(records: list[EarListRecord]) -> dict[tuple[str, str], list[EarListRecord]]:
    indexed: dict[tuple[str, str], list[EarListRecord]] = {}
    for record in records:
        indexed.setdefault(record.key, []).append(record)
    return indexed


def compare_snapshots(
    previous: list[EarListRecord],
    latest: list[EarListRecord],
) -> tuple[list[EarListRecord], list[EarListRecord], list[tuple[EarListRecord, EarListRecord]]]:
    """Compare old and new records and report added / removed / modified entries."""

    old_index = _index_records(previous)
    new_index = _index_records(latest)
    added: list[EarListRecord] = []
    removed: list[EarListRecord] = []
    modified: list[tuple[EarListRecord, EarListRecord]] = []

    for key, new_records in new_index.items():
        old_records = old_index.get(key, [])
        if not old_records:
            added.extend(new_records)
            continue
        new_by_signature = {record.signature: record for record in new_records}
        for old_record in old_records:
            if old_record.signature in new_by_signature:
                new_by_signature.pop(old_record.signature, None)
        # Remaining new records represent a change to an existing entry.
        for new_record in new_by_signature.values():
            modified.append((old_records[0], new_record))

    for key, old_records in old_index.items():
        if key not in new_index:
            removed.extend(old_records)

    added.sort(key=lambda record: (record.source_code, record.name.casefold()))
    removed.sort(key=lambda record: (record.source_code, record.name.casefold()))
    modified.sort(key=lambda item: (item[1].source_code, item[1].name.casefold()))
    return added, removed, modified


def _record_text(record: EarListRecord) -> str:
    return " | ".join(
        [
            record.name,
            record.aliases,
            record.country,
            record.reference,
            record.source,
            record.notes,
        ]
    )


def _write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_snapshot(records: list[EarListRecord], path: Path | None = None) -> Path:
    """Write the applied snapshot to the screening CSV (atomically)."""

    target = Path(path) if path is not None else SNAPSHOT_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    _write_csv(temp, CSV_HEADERS, [record.as_row() for record in records])
    os.replace(temp, target)
    return target


def _update_log_rows(result: SyncResult) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if result.initial_load:
        rows.append(
            {
                "synced_at": result.fetched_at,
                "action": "INITIAL_LOAD",
                "source_list": "",
                "name": "",
                "aliases": "",
                "country": "",
                "reference": "",
                "source": "",
                "notes": "",
                "detail": (
                    f"Initial snapshot from {result.url}: {result.record_count} records "
                    f"({result.fetched_total} rows fetched). No previous snapshot to compare."
                ),
            }
        )
        return rows
    for record in result.added:
        rows.append(
            {
                "synced_at": result.fetched_at,
                "action": "ADDED",
                "source_list": record.source_code,
                **record.as_row(),
                "detail": "Newly present in the official CSL file since the previous sync.",
            }
        )
    for record in result.removed:
        rows.append(
            {
                "synced_at": result.fetched_at,
                "action": "REMOVED",
                "source_list": record.source_code,
                **record.as_row(),
                "detail": "No longer present in the official CSL file; verify against the Federal Register.",
            }
        )
    for old_record, new_record in result.modified:
        rows.append(
            {
                "synced_at": result.fetched_at,
                "action": "MODIFIED",
                "source_list": new_record.source_code,
                **new_record.as_row(),
                "detail": f"Details changed. Previous: {_record_text(old_record)[:600]}",
            }
        )
    return rows


def append_update_log(
    result: SyncResult,
    path: Path | None = None,
) -> Path:
    """Append ADDED / REMOVED / MODIFIED rows to the persistent updates log."""

    target = Path(path) if path is not None else UPDATE_LOG_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = _update_log_rows(result)

    first_write = not target.exists() or target.stat().st_size == 0
    with target.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=UPDATE_LOG_HEADERS, extrasaction="ignore")
        if first_write:
            handle.write("\ufeff")
            writer.writeheader()
        writer.writerows(rows)
    return target


def update_log_csv_bytes(result: SyncResult) -> bytes:
    """Serialize the per-sync update log rows as UTF-8 CSV bytes."""

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=UPDATE_LOG_HEADERS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(_update_log_rows(result))
    return buffer.getvalue().encode("utf-8-sig")


def snapshot_csv_bytes(records: list[EarListRecord]) -> bytes:
    """Serialize records in the screening-compatible CSV schema."""

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_HEADERS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows([record.as_row() for record in records])
    return buffer.getvalue().encode("utf-8-sig")


def read_meta() -> dict:
    if not META_FILE.exists():
        return {}
    try:
        return json.loads(META_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_meta(result: SyncResult | None = None, **extra: object) -> dict:
    meta = read_meta()
    if result is not None:
        meta.update(
            {
                "last_synced_at": result.fetched_at,
                "last_url": result.url,
                "last_total_fetched": result.fetched_total,
                "last_record_count": result.record_count,
                "last_added": result.added_count,
                "last_removed": result.removed_count,
                "last_modified": result.modified_count,
                "source_counts": {
                    code: sum(1 for record in result.records if record.source_code == code)
                    for code in SOURCE_CODES
                },
            }
        )
    meta.update({str(key): value for key, value in extra.items()})
    META_FILE.parent.mkdir(parents=True, exist_ok=True)
    META_FILE.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return meta


def synced_list_path() -> Path | None:
    """Return the snapshot path only when an applied sync snapshot exists."""

    return SNAPSHOT_FILE if SNAPSHOT_FILE.exists() else None


def fetch_and_compare(
    include_codes: tuple[str, ...] | list[str] = BIS_ONLY_CODES,
    url: str | None = None,
    fetcher: Callable[[str], bytes] | None = None,
    now: datetime | None = None,
    snapshot_path: Path | None = None,
) -> SyncResult:
    """Download the latest official CSL file and compare it with the local snapshot."""

    target_url = url or default_source_url()
    get_bytes = fetcher or http_get_bytes
    raw = get_bytes(target_url)
    dataset = parse_csl_dataset(raw, include_codes=include_codes)
    fetched_at = (now or datetime.now()).astimezone().isoformat(timespec="seconds")
    snapshot = Path(snapshot_path) if snapshot_path is not None else SNAPSHOT_FILE
    previous = _read_snapshot_records(snapshot)
    added, removed, modified = compare_snapshots(previous, dataset.records)
    return SyncResult(
        fetched_at=fetched_at,
        url=target_url,
        fetched_total=dataset.total_rows,
        records=dataset.records,
        added=added,
        removed=removed,
        modified=modified,
        initial_load=not previous,
    )


def apply_sync_result(result: SyncResult) -> dict:
    """Write the latest snapshot and metadata after user confirmation."""

    snapshot_path = write_snapshot(result.records)
    log_path = append_update_log(result)
    meta = write_meta(result, snapshot_file=str(snapshot_path), update_log_file=str(log_path))
    return meta


def snapshot_summary() -> dict:
    """Summary of the currently applied local snapshot (empty before first apply)."""

    records = _read_snapshot_records(SNAPSHOT_FILE)
    meta = read_meta()
    return {
        "path": str(SNAPSHOT_FILE) if SNAPSHOT_FILE.exists() else "",
        "exists": SNAPSHOT_FILE.exists(),
        "count": len(records),
        "source_counts": {
            code: sum(1 for record in records if record.source_code == code) for code in SOURCE_CODES
        },
        "last_synced_at": meta.get("last_synced_at", ""),
        "last_added": meta.get("last_added", 0),
        "last_removed": meta.get("last_removed", 0),
        "last_modified": meta.get("last_modified", 0),
        "last_total_fetched": meta.get("last_total_fetched", 0),
        "last_record_count": meta.get("last_record_count", 0),
        "update_log_file": meta.get("update_log_file", ""),
    }
