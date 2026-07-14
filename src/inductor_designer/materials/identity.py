from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MaterialRef:
    """Identity-only reference to a magnetic material; property data arrives in Milestone 5."""

    manufacturer: str
    name: str
    grade: str

    def __post_init__(self) -> None:
        for field_name in ("manufacturer", "name", "grade"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"MaterialRef {field_name} cannot be blank")
