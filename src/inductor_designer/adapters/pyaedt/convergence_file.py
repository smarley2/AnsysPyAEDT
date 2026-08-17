"""Parser for the convergence table AEDT's ExportConvergence writes.

`oDesign.ExportConvergence` (PyAEDT's `export_convergence`) writes a small text
report whose last section is a pipe-delimited table, one row per adaptive pass.
The header names the columns and differs by solver and solution type, so the
error column is located by name rather than by position:

    Setup : Setup1

    ==================
    Number of Passes
    Completed : 4
    Maximum   : 10
    Minimum   : 3
    ==================
    Criterion : Energy Error/Delta Energy (%)
    Target    : (1, 1)
    Current   : 0.42
    ==================
    Pass|Triangles|Total Energy (J)|Energy Error (%)|Delta Energy (%)|...
    1|1234|1.20e-04|12.5|100|...

Header captured from AEDT 2025.2, Maxwell 2D AC Magnetic, 2026-08-17. Nothing
here reaches AEDT: the file is read as text, so the format is pinned by a
fixture rather than by a live session.
"""

from __future__ import annotations

# Column names that carry the adaptive error, in the order they are preferred.
# "Energy Error" is what Maxwell reports; the delta columns describe the change
# between passes, which is a different criterion and only used if the solver
# reported no error column at all.
_ERROR_COLUMNS = (
    "energy error",
    "error",
    "delta energy",
    "delta s",
)


def _normalise(column: str) -> str:
    """Column name without its unit suffix, lowercased."""
    return column.split("(")[0].strip().casefold()


def _error_index(columns: list[str]) -> int | None:
    normalised = [_normalise(column) for column in columns]
    for candidate in _ERROR_COLUMNS:
        for index, column in enumerate(normalised):
            if column == candidate:
                return index
    return None


def parse_convergence(text: str) -> tuple[tuple[int, float], ...]:
    """Return `(pass number, error percent)` per adaptive pass.

    An empty tuple means the file carries no data rows, which is what AEDT
    writes for a setup it has not solved -- the header is always present, so a
    header alone is not evidence of a convergence failure.
    """
    rows: tuple[tuple[int, float], ...] = ()
    columns: list[str] | None = None
    error_index: int | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if "|" not in stripped:
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if columns is None:
            # The first pipe-delimited line is the header. A solver that names
            # no error column leaves nothing to report, and reporting the pass
            # count alone would look like convergence data.
            columns = cells
            error_index = _error_index(columns)
            if error_index is None:
                return ()
            continue
        if error_index is None or len(cells) <= max(1, error_index):
            continue
        try:
            pass_number = int(cells[0])
            error_percent = float(cells[error_index])
        except ValueError:
            # A pass whose error AEDT left as "N/A" is skipped rather than
            # reported as zero error.
            continue
        rows = (*rows, (pass_number, error_percent))
    return rows
