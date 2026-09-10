"""Product information data model (Step 2)."""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field, field_validator

from app.models.base import ToolModel


class ProductInformation(ToolModel):
    """Product facts collected during Step 2."""

    product_name: str = Field(..., min_length=1, max_length=300)
    model: str | None = Field(default=None, max_length=200)
    product_description: str = Field(default="", max_length=4000)
    category: str | None = Field(default=None, max_length=100)
    manufacturer: str | None = Field(default=None, max_length=300)
    country_of_manufacture: str | None = Field(default=None, max_length=100)
    existing_eccn: str | None = Field(default=None, max_length=20)
    existing_ear_status: str | None = Field(default=None, max_length=60)
    product_value: Decimal | None = Field(default=None, ge=0, decimal_places=2)

    @field_validator("existing_eccn", "existing_ear_status", "model", "category", "manufacturer")
    @classmethod
    def _clean(cls, value):
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None

    @field_validator("existing_eccn", mode="before")
    @classmethod
    def _upper_eccn(cls, value):
        cleaned = ProductInformation._clean(value)
        return cleaned.upper() if cleaned else None

    @field_validator("product_value", mode="before")
    @classmethod
    def _blank_value(cls, value):
        if value in ("", None):
            return None
        return value


PRODUCT_CATEGORIES = [
    "Electronics",
    "Telecommunications",
    "Semiconductor / Microelectronics",
    "Software",
    "Aerospace & Defense",
    "Industrial Machinery",
    "Chemicals / Materials",
    "Sensors / Lasers",
    "Vehicles / Engines",
    "Other",
]

EAR_STATUS_OPTIONS = [
    "Not determined",
    "Controlled (ECCN)",
    "EAR99",
    "Not believed to be U.S.-origin",
    "Unknown",
]

