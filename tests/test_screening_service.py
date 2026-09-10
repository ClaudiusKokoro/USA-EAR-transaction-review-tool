"""Tests for the party screening service (Step 6)."""

from __future__ import annotations

import csv
from pathlib import Path

from app.models.party import (
    SCREENING_MANUAL_VERIFICATION,
    SCREENING_NO_APPARENT_MATCH,
    SCREENING_POSSIBLE_MATCH,
)
from app.services.screening_service import screen_parties


def _write_csv(path: Path) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["name", "aliases", "country", "reference", "source", "notes"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "name": "Acme Dynamic Systems Ltd.",
                "aliases": "Acme Dynamic;ADS",
                "country": "GB",
                "reference": "TEST-0001",
                "source": "TEST",
                "notes": "test fixture",
            }
        )
        writer.writerow(
            {
                "name": "Unrelated Freight Group SA",
                "aliases": "UFG",
                "country": "CH",
                "reference": "TEST-0002",
                "source": "TEST",
                "notes": "test fixture",
            }
        )
    return path


def test_exact_match_requires_manual_verification(tmp_path: Path):
    csv_path = _write_csv(tmp_path / "ref.csv")
    output = screen_parties(
        [{"name": "Acme Dynamic Systems Ltd.", "role": "Buyer", "country": "GB"}],
        csv_paths=[csv_path],
    )
    result = output.results[0]
    assert result.status == SCREENING_MANUAL_VERIFICATION
    assert float(result.best_score) >= 0.96
    # Never auto-declare restricted party status.
    assert "restricted party" not in result.status.lower()


def test_fuzzy_similar_party_is_possible_match(tmp_path: Path):
    csv_path = _write_csv(tmp_path / "ref.csv")
    output = screen_parties(
        [{"name": "Acme Dynamic Systems Ltd Co", "role": "Buyer", "country": "GB"}],
        csv_paths=[csv_path],
    )
    result = output.results[0]
    # Token-close match should be a possible or manual match, never a no-match.
    assert result.status in (SCREENING_POSSIBLE_MATCH, SCREENING_MANUAL_VERIFICATION)
    assert float(result.best_score) >= 0.65


def test_no_match(tmp_path: Path):
    csv_path = _write_csv(tmp_path / "ref.csv")
    output = screen_parties(
        [{"name": "Totally Independent Coffee Roasters", "role": "End user", "country": "BR"}],
        csv_paths=[csv_path],
    )
    assert output.results[0].status == SCREENING_NO_APPARENT_MATCH


def test_default_sample_file_loads(tmp_path: Path):
    output = screen_parties(
        [{"name": "Acme Non-Matching Corp", "role": "Buyer"}],
        csv_paths=None,
    )
    assert output.record_count >= 5
    assert output.results[0].status in (
        SCREENING_NO_APPARENT_MATCH,
        SCREENING_POSSIBLE_MATCH,
        SCREENING_MANUAL_VERIFICATION,
    )

