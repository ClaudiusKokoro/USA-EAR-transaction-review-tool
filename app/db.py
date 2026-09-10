"""SQLite persistence layer for local review history."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from app.paths import default_database_path


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_connection(db_path=None) -> sqlite3.Connection:
    path = db_path or default_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            transaction_name TEXT NOT NULL,
            exporter_name TEXT NOT NULL DEFAULT '',
            buyer_name TEXT NOT NULL DEFAULT '',
            buyer_country TEXT NOT NULL DEFAULT '',
            risk_level TEXT NOT NULL DEFAULT 'NOT_RUN',
            total_risk REAL,
            review_json TEXT NOT NULL
        )
        """
    )
    connection.commit()
    return connection


def save_review(payload: dict[str, Any], db_path=None) -> int:
    """Persist a complete review payload (raw form data + computed results)."""

    now = _utcnow()
    transaction = payload.get("transaction") or {}
    summary = payload.get("summary") or {}
    connection = get_connection(db_path)
    cursor = connection.execute(
        """
        INSERT INTO reviews (
            created_at, updated_at, transaction_name, exporter_name, buyer_name,
            buyer_country, risk_level, total_risk, review_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now,
            now,
            str(transaction.get("transaction_name") or "Untitled transaction"),
            str(transaction.get("exporter_name") or ""),
            str(transaction.get("buyer_name") or ""),
            str(transaction.get("buyer_country") or ""),
            str(summary.get("risk_level") or "NOT_RUN"),
            summary.get("total_risk"),
            json.dumps(payload, default=str),
        ),
    )
    connection.commit()
    review_id = int(cursor.lastrowid)
    connection.close()
    return review_id


def list_reviews(db_path=None) -> list[dict[str, Any]]:
    connection = get_connection(db_path)
    rows = connection.execute(
        """
        SELECT id, created_at, updated_at, transaction_name, exporter_name, buyer_name,
               buyer_country, risk_level, total_risk
        FROM reviews
        ORDER BY id DESC
        """
    ).fetchall()
    connection.close()
    return [dict(row) for row in rows]


def load_review(review_id: int, db_path=None) -> dict[str, Any]:
    connection = get_connection(db_path)
    row = connection.execute("SELECT review_json FROM reviews WHERE id = ?", (review_id,)).fetchone()
    connection.close()
    if row is None:
        raise KeyError(f"No review with id {review_id}")
    return json.loads(row["review_json"])


def delete_review(review_id: int, db_path=None) -> None:
    connection = get_connection(db_path)
    connection.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
    connection.commit()
    connection.close()

