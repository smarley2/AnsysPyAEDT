"""Read persisted FEMM material B-H points.

The parser follows the FEMM file format documented at
https://www.femm.info/Archives/contrib/FEMM_file_format.docx.
"""

from __future__ import annotations

import re
from pathlib import Path

_BLOCK = re.compile(r"<BeginBlock>(.*?)<EndBlock>", re.DOTALL)


def read_material_bh_points(
    path: Path,
    material_name: str,
) -> tuple[tuple[float, float], ...]:
    text = path.read_text(encoding="utf-8", errors="strict")
    block = next(
        (
            body
            for body in _BLOCK.findall(text)
            if re.search(
                rf'<BlockName>\s*=\s*"{re.escape(material_name)}"',
                body,
            )
        ),
        None,
    )
    if block is None:
        raise ValueError(f"FEMM material not found: {material_name}")
    count_match = re.search(r"<BHPoints>\s*=\s*(\d+)", block)
    if count_match is None:
        raise ValueError(f"FEMM material has no BHPoints field: {material_name}")
    count = int(count_match.group(1))
    rows: list[tuple[float, float]] = []
    for line in block[count_match.end() :].splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("<"):
            break
        values = stripped.split()
        if len(values) != 2:
            raise ValueError(f"Malformed FEMM B-H row for {material_name}")
        rows.append((float(values[0]), float(values[1])))
    if len(rows) != count:
        raise ValueError(
            f"FEMM material {material_name} declares {count} B-H points "
            f"but stores {len(rows)}."
        )
    return tuple(rows)
