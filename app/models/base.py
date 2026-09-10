"""Shared Pydantic configuration."""

from pydantic import BaseModel, ConfigDict


class ToolModel(BaseModel):
    """Base model used across the application."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=False,
        extra="forbid",
    )

