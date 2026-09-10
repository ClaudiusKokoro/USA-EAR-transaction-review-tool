"""Party screening service (Step 6).

Screening is performed against local CSV reference lists. Exact and fuzzy name
matches never produce a "restricted party" conclusion; the strongest automated
output is MANUAL VERIFICATION REQUIRED.
"""

from __future__ import annotations

import csv
import difflib
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from app.models.party import (
    SCREENING_MANUAL_VERIFICATION,
    SCREENING_NO_APPARENT_MATCH,
    SCREENING_POSSIBLE_MATCH,
    PartyScreeningResult,
    PartyToScreen,
    ScreeningMatch,
    ScreeningOutput,
)
from app.paths import data_path

DEFAULT_RESTRICTED_PARTIES_FILE = data_path("restricted_parties.csv")

MANUAL_THRESHOLD = Decimal("0.96")
POSSIBLE_THRESHOLD = Decimal("0.65")


def _normalize(text: str | None) -> str:
    if text is None:
        return ""
    value = unicodedata.normalize("NFKD", str(text))
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.casefold()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return " ".join(value.split())


def _corporate_words(name: str) -> set[str]:
    return {
        "ltd",
        "limited",
        "inc",
        "incorporated",
        "corp",
        "corporation",
        "co",
        "company",
        "pte",
        "bhd",
        "llc",
        "llp",
        "plc",
        "gmbh",
        "sarl",
        "jsc",
        "holding",
        "group",
        "international",
        "intl",
    }


def _char_ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    return difflib.SequenceMatcher(None, left, right).ratio()


def _token_ratio(left: str, right: str) -> float:
    left_tokens = {token for token in left.split() if token not in _corporate_words(left)}
    right_tokens = {token for token in right.split() if token not in _corporate_words(right)}
    if not left_tokens and not right_tokens:
        return 1.0 if left == right else 0.0
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = left_tokens & right_tokens
    return 2.0 * len(intersection) / (len(left_tokens) + len(right_tokens))


def _combined_similarity(left: str, right: str) -> float:
    left_norm = _normalize(left)
    right_norm = _normalize(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    return max(
        _char_ratio(left_norm, right_norm),
        0.8 * _char_ratio(left_norm, right_norm) + 0.2 * _token_ratio(left_norm, right_norm),
    )


def _status_for_score(score: float) -> str:
    decimal_score = Decimal(str(score))
    if decimal_score >= MANUAL_THRESHOLD:
        return SCREENING_MANUAL_VERIFICATION
    if decimal_score >= POSSIBLE_THRESHOLD:
        return SCREENING_POSSIBLE_MATCH
    return SCREENING_NO_APPARENT_MATCH


@dataclass
class ListedParty:
    name: str
    aliases: list[str]
    country: str
    reference: str
    source: str
    notes: str

    @property
    def names(self) -> list[str]:
        return [self.name, *self.aliases]


def _read_csv(path: Path) -> list[ListedParty]:
    if not path.exists():
        raise FileNotFoundError(f"Reference list not found: {path}")
    parties: list[ListedParty] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(line for line in handle if not line.lstrip().startswith("#"))
        for row in reader:
            name = (row.get("name") or "").strip()
            if not name:
                continue
            aliases = [part.strip() for part in (row.get("aliases") or "").split(";") if part.strip()]
            parties.append(
                ListedParty(
                    name=name,
                    aliases=aliases,
                    country=(row.get("country") or "").strip().upper(),
                    reference=(row.get("reference") or "").strip(),
                    source=(row.get("source") or "LOCAL_CSV").strip(),
                    notes=(row.get("notes") or "").strip(),
                )
            )
    return parties


def load_restricted_parties(
    csv_paths: list[Path | str] | None = None,
) -> tuple[list[ListedParty], list[str]]:
    """Load reference records from CSV files (skipping comment lines)."""

    sources = csv_paths if csv_paths is not None else [DEFAULT_RESTRICTED_PARTIES_FILE]
    parties: list[ListedParty] = []
    loaded: list[str] = []
    for source in sources:
        path = Path(source)
        loaded.append(str(path))
        parties.extend(_read_csv(path))
    return parties, loaded


def screen_parties(
    parties: list[PartyToScreen | dict],
    csv_paths: list[Path | str] | None = None,
    manual_threshold: float | None = None,
    possible_threshold: float | None = None,
) -> ScreeningOutput:
    """Screen parties against reference lists and score name similarity.

    Every party receives one of NO_APPEARANT_MATCH, POSSIBLE_MATCH, or
    MANUAL_VERIFICATION_REQUIRED. The tool never declares that a party is a
    restricted party.
    """

    parsed_parties = [
        party if isinstance(party, PartyToScreen) else PartyToScreen.model_validate(party)
        for party in (parties or [])
    ]
    listed, sources = load_restricted_parties(csv_paths)
    output = ScreeningOutput(results=[], source_files=sources, record_count=len(listed))
    if not parsed_parties:
        return output
    if not listed:
        for party in parsed_parties:
            output.results.append(
                PartyScreeningResult(
                    party=party,
                    status=SCREENING_NO_APPARENT_MATCH,
                    explanation="No reference records were loaded, so no comparison was possible.",
                )
            )
        return output

    global_manual_threshold = float(manual_threshold) if manual_threshold is not None else float(MANUAL_THRESHOLD)
    global_possible_threshold = float(possible_threshold) if possible_threshold is not None else float(POSSIBLE_THRESHOLD)

    for party in parsed_parties:
        matches: list[tuple[float, ListedParty, str]] = []
        seen: set[str] = set()
        for entry in listed:
            for candidate in entry.names:
                key = _normalize(candidate)
                if not key or key in seen:
                    continue
                seen.add(key)
                score = _combined_similarity(party.name, candidate)
                matches.append((score, entry, candidate))

        matches.sort(key=lambda item: item[0], reverse=True)
        top = matches[:5]
        best_score = top[0][0] if top else 0.0
        best_status = _status_for_score(best_score)

        match_models: list[ScreeningMatch] = []
        for score, entry, candidate in top:
            normalized = _normalize(party.name)
            if normalized == _normalize(candidate):
                method = "exact"
            elif score >= 0.9:
                method = "fuzzy (near-exact)"
            else:
                method = "fuzzy (similarity scoring)"
            match_models.append(
                ScreeningMatch(
                    matched_name=entry.name,
                    score=Decimal(str(round(score, 4))),
                    match_method=method,
                    listed_country=entry.country or None,
                    listed_reference=entry.reference or None,
                    listed_source=entry.source or None,
                    listed_notes=entry.notes or None,
                )
            )

        if best_status == SCREENING_NO_APPARENT_MATCH:
            explanation = "No name in the loaded reference lists scored at or above the possible-match threshold."
        elif best_status == SCREENING_POSSIBLE_MATCH:
            explanation = (
                "One or more names are similar to entries in the reference lists. "
                "A similarity score alone does not establish that the party is a restricted party; "
                "verify the exact name, entity type, and geography before relying on this result."
            )
        else:
            explanation = (
                "A name exactly matches or very closely matches an entry in the loaded reference lists. "
                "Manual verification is required to confirm identity. A name match alone never establishes "
                "that a party is a restricted party."
            )

        output.results.append(
            PartyScreeningResult(
                party=party,
                status=best_status,
                best_score=Decimal(str(round(best_score, 4))),
                best_match=match_models[0] if match_models else None,
                matches=match_models,
                explanation=explanation,
            )
        )

    return output
