"""Filesystem helpers that make the app independent of the launch directory."""

from __future__ import annotations

import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent

RULES_DIR = APP_DIR / "rules"
DATA_DIR = APP_DIR / "data"
TEMPLATES_DIR = APP_DIR / "templates"


def rule_path(filename: str) -> Path:
    return RULES_DIR / filename


def data_path(filename: str) -> Path:
    return DATA_DIR / filename


def template_path(filename: str) -> Path:
    return TEMPLATES_DIR / filename


def default_database_path() -> Path:
    override = os.environ.get("EAR_REVIEW_DB")
    return Path(override) if override else PROJECT_ROOT / "ear_reviews.db"
