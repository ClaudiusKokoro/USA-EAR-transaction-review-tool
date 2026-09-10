"""Transaction intake data model (Step 1)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import Field, field_validator

from app.models.base import ToolModel


def _empty_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _country_code(value: str) -> str:
    return value.strip().upper()


class TransactionIntake(ToolModel):
    """Core transaction facts collected during Step 1."""

    transaction_name: str = Field(..., min_length=1, max_length=200)
    exporter_name: str = Field(..., min_length=1, max_length=300)
    exporter_country: str = Field(..., min_length=2, max_length=2)
    buyer_name: str = Field(..., min_length=1, max_length=300)
    buyer_country: str = Field(..., min_length=2, max_length=2)
    consignee: str | None = Field(default=None, max_length=300)
    ultimate_end_user: str | None = Field(default=None, max_length=300)
    ultimate_destination: str | None = Field(default=None, max_length=2)
    transaction_value: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    shipment_date: date | None = None
    notes: str = Field(default="", max_length=2000)

    @field_validator("consignee", "ultimate_end_user", mode="before")
    @classmethod
    def _clean_optional(cls, value):
        return _empty_to_none(value)

    @field_validator("notes", mode="before")
    @classmethod
    def _clean_notes(cls, value):
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("currency", mode="before")
    @classmethod
    def _clean_currency(cls, value):
        if value is None or str(value).strip() == "":
            return "USD"
        return str(value).strip().upper()

    @field_validator("exporter_country", "buyer_country")
    @classmethod
    def _normalize_country(cls, value: str) -> str:
        return _country_code(value)

    @field_validator("ultimate_destination", mode="before")
    @classmethod
    def _normalize_destination(cls, value):
        cleaned = _empty_to_none(value)
        return _country_code(cleaned) if cleaned else None

    @field_validator("transaction_value", mode="before")
    @classmethod
    def _blank_value(cls, value):
        if value in ("", None):
            return None
        return value

    @field_validator("shipment_date", mode="before")
    @classmethod
    def _blank_date(cls, value):
        return None if value in ("", None) else value


def normalize_transaction_dict(data: dict) -> dict:
    """Normalize raw form output before model validation."""

    normalized = dict(data or {})
    for key in ("consignee", "ultimate_end_user", "ultimate_destination", "notes", "currency"):
        value = normalized.get(key)
        if key == "notes":
            normalized[key] = (value or "").strip()
        elif key == "currency":
            normalized[key] = str(value or "USD").strip().upper() or "USD"
        else:
            normalized[key] = _empty_to_none(value)
    for key in ("exporter_country", "buyer_country"):
        if normalized.get(key):
            normalized[key] = _country_code(str(normalized[key]))
    if normalized.get("ultimate_destination"):
        normalized["ultimate_destination"] = _country_code(str(normalized["ultimate_destination"]))
    return normalized
