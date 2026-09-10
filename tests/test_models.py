"""Tests for core Pydantic models and input validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.transaction import TransactionIntake


def test_country_codes_normalized():
    transaction = TransactionIntake(
        transaction_name="T1",
        exporter_name="Exporter A",
        exporter_country="cn",
        buyer_name="Buyer B",
        buyer_country="sg",
        ultimate_destination="sg",
    )
    assert transaction.exporter_country == "CN"
    assert transaction.buyer_country == "SG"
    assert transaction.ultimate_destination == "SG"


def test_empty_optional_fields_become_none():
    transaction = TransactionIntake(
        transaction_name="T1",
        exporter_name="Exporter A",
        exporter_country="CN",
        buyer_name="Buyer B",
        buyer_country="SG",
        consignee="   ",
        ultimate_end_user="",
        notes="",
    )
    assert transaction.consignee is None
    assert transaction.ultimate_end_user is None
    assert transaction.notes == ""


def test_required_fields_enforced():
    with pytest.raises(ValidationError):
        TransactionIntake(
            exporter_name="Exporter",
            exporter_country="CN",
            buyer_name="Buyer",
            buyer_country="SG",
        )


def test_negative_value_rejected():
    with pytest.raises(ValidationError):
        TransactionIntake(
            transaction_name="T1",
            exporter_name="Exporter",
            exporter_country="CN",
            buyer_name="Buyer",
            buyer_country="SG",
            transaction_value="-5",
        )

