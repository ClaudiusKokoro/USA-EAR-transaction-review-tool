"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest


@pytest.fixture
def sample_transaction_data() -> dict:
    return {
        "transaction_name": "SN-2026-0715 Singapore Distribution",
        "exporter_name": "Shenzhen Horizon Electronics Co., Ltd.",
        "exporter_country": "CN",
        "buyer_name": "Meridian Pacific Electronics Pte. Ltd.",
        "buyer_country": "SG",
        "consignee": "Meridian Pacific Logistics Hub",
        "ultimate_end_user": None,
        "ultimate_destination": "SG",
        "transaction_value": 850000.0,
        "currency": "USD",
        "shipment_date": "2026-07-15",
        "notes": "",
    }


@pytest.fixture
def sample_product_data() -> dict:
    return {
        "product_name": "VX-990 Smart Network Switch",
        "model": "VX-990-48T",
        "product_description": "Commercial 48-port Ethernet switch assembled in China.",
        "category": "Electronics",
        "manufacturer": "Shenzhen Horizon Electronics Co., Ltd.",
        "country_of_manufacture": "CN",
        "existing_eccn": None,
        "existing_ear_status": "Not determined",
        "product_value": 850000.0,
    }

