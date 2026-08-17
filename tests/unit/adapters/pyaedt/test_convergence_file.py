from __future__ import annotations

from pathlib import Path

from inductor_designer.adapters.pyaedt.convergence_file import parse_convergence

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"


def read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_every_adaptive_pass_and_its_energy_error_are_read() -> None:
    """The unsolved-project header was captured live from AEDT 2025.2 on
    2026-08-17; the solved rows follow that same header.
    """
    rows = parse_convergence(read("aedt_convergence_solved.prop"))

    assert rows == (
        (1, 12.5),
        (2, 4.31),
        (3, 1.22),
        (4, 0.421),
    )


def test_a_header_without_data_rows_reads_as_no_convergence_data() -> None:
    """AEDT writes the header for an unsolved setup too, so a header alone must
    not read as a converged solve or as a failure."""
    assert parse_convergence(read("aedt_convergence_unsolved.prop")) == ()


def test_the_error_column_is_found_by_name_not_by_position() -> None:
    """Column layout differs by solver and solution type."""
    text = (
        "Setup : Setup1\n"
        "Pass|Tetrahedra|Max Mag. Delta S|Total Energy (J)|Energy Error (%)|\n"
        "1|900|0.31|1.0e-4|9.75|\n"
        "2|1400|0.04|1.1e-4|0.88|\n"
    )

    assert parse_convergence(text) == ((1, 9.75), (2, 0.88))


def test_a_delta_column_is_used_only_when_no_error_column_exists() -> None:
    text = (
        "Pass|Tetrahedra|Delta S|\n"
        "1|900|0.31|\n"
        "2|1400|0.04|\n"
    )

    assert parse_convergence(text) == ((1, 0.31), (2, 0.04))


def test_a_table_with_no_recognised_error_column_reports_nothing() -> None:
    """Reporting the pass count alone would look like convergence data."""
    text = "Pass|Tetrahedra|Total Energy (J)|\n1|900|1.0e-4|\n"

    assert parse_convergence(text) == ()


def test_a_pass_whose_error_is_not_a_number_is_skipped() -> None:
    text = (
        "Pass|Triangles|Energy Error (%)|\n"
        "1|1832|N/A|\n"
        "2|2417|4.31|\n"
    )

    assert parse_convergence(text) == ((2, 4.31),)


def test_text_without_a_table_is_not_an_error() -> None:
    assert parse_convergence("Setup : Setup1\nNo convergence available\n") == ()
