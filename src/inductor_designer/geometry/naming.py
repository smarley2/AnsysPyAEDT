from __future__ import annotations

import re
from collections.abc import Sequence

from inductor_designer.geometry.packing import PackedWinding

_INVALID = re.compile(r"[^A-Za-z0-9_]")


def sanitize_identifier(raw: str) -> str:
    cleaned = _INVALID.sub("_", raw)
    if not cleaned:
        raise ValueError("Identifier is empty after sanitizing")
    if cleaned[0].isdigit():
        cleaned = f"W{cleaned}"
    return cleaned


def core_name() -> str:
    return "Core"


def turn_name(winding_id: str, layer: int, turn: int) -> str:
    return f"{sanitize_identifier(winding_id)}_L{layer:02d}_T{turn:03d}"


def lead_names(winding_id: str) -> tuple[str, str]:
    base = sanitize_identifier(winding_id)
    return (f"{base}_LeadIn", f"{base}_LeadOut")


def terminal_names(winding_id: str) -> tuple[str, str]:
    base = sanitize_identifier(winding_id)
    return (f"{base}_TermIn", f"{base}_TermOut")


def winding_names(packing: PackedWinding) -> tuple[str, ...]:
    names: list[str] = []
    counter = 1
    for layer in packing.layers:
        for _ in layer.station_deg:
            names.append(turn_name(packing.winding_id, layer.index, counter))
            counter += 1
    return tuple(names)


def unique_identifiers(raw_ids: Sequence[str]) -> dict[str, str]:
    """Deterministic collision-free sanitized identifiers, keyed by raw id.

    Later collisions get an ``_2``, ``_3``, ... suffix in input order.
    """
    result: dict[str, str] = {}
    taken: set[str] = set()
    for raw in raw_ids:
        if raw in result:
            raise ValueError(f"Duplicate raw identifier: {raw!r}")
        candidate = sanitize_identifier(raw)
        if candidate in taken:
            suffix = 2
            while f"{candidate}_{suffix}" in taken:
                suffix += 1
            candidate = f"{candidate}_{suffix}"
        taken.add(candidate)
        result[raw] = candidate
    return result
