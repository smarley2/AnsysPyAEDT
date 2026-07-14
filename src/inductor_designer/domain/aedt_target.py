from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True, order=True, slots=True)
class AedtRelease:
    year: int
    release: int

    def __post_init__(self) -> None:
        if (
            type(self.year) is not int
            or type(self.release) is not int
            or not 2000 <= self.year <= 2099
            or self.release not in (1, 2)
            or (self.year, self.release) < (2024, 2)
        ):
            raise ValueError(f"Invalid AEDT release: {self.year}.{self.release}")

    @classmethod
    def parse(cls, value: str) -> AedtRelease:
        parts = value.split(".")
        if (
            len(parts) != 2
            or len(parts[0]) != 4
            or not parts[0].startswith("20")
            or len(parts[1]) != 1
            or not all(part.isdigit() for part in parts)
        ):
            raise ValueError(f"Invalid AEDT release: {value}")
        return cls(int(parts[0]), int(parts[1]))

    def __str__(self) -> str:
        return f"{self.year}.{self.release}"


class AedtEdition(str, Enum):
    COMMERCIAL = "commercial"
    STUDENT = "student"


class ModelDimension(str, Enum):
    TWO_D = "2d"
    THREE_D = "3d"
