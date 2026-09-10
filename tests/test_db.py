"""Tests for SQLite review persistence."""

from __future__ import annotations

from app.db import delete_review, list_reviews, load_review, save_review


def test_save_and_load_round_trip(tmp_path):
    db_path = tmp_path / "reviews.db"
    review_id = save_review(
        {
            "transaction": {"transaction_name": "DB Test"},
            "summary": {"risk_level": "LOW", "total_risk": 3},
            "step_data": {"1": {"transaction_name": "DB Test"}},
        },
        db_path=db_path,
    )
    loaded = load_review(review_id, db_path=db_path)
    assert loaded["transaction"]["transaction_name"] == "DB Test"
    reviews = list_reviews(db_path=db_path)
    assert len(reviews) == 1
    assert reviews[0]["transaction_name"] == "DB Test"
    delete_review(review_id, db_path=db_path)
    assert list_reviews(db_path=db_path) == []

