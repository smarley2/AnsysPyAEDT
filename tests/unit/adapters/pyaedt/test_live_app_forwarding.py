from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

from inductor_designer.adapters.pyaedt.live_app import LiveAppExtraction


class _App:
    """Stands in for a PyAEDT application with one property and one plain field."""

    def __init__(self) -> None:
        self.model_depth_writes: list[Any] = []
        self.model_units = "meter"

    @property
    def model_depth(self) -> str:
        return self.model_depth_writes[-1] if self.model_depth_writes else "1meter"

    @model_depth.setter
    def model_depth(self, value: Any) -> None:
        self.model_depth_writes.append(value)


def test_attribute_writes_reach_the_wrapped_application() -> None:
    """`__getattr__` forwards reads; a write has to reach the real setter too.

    Without `__setattr__`, `app.model_depth = ...` shadowed the property on the
    wrapper, the PyAEDT setter never ran, and the saved 2D design kept AEDT's
    default 1 m model depth -- scaling every 2D result by 1 m / core height.
    """
    app = _App()
    wrapper = LiveAppExtraction(app)

    wrapper.model_depth = "0.01537meter"  # type: ignore[attr-defined]
    wrapper.model_units = "mm"  # type: ignore[attr-defined]

    assert app.model_depth_writes == ["0.01537meter"]
    assert app.model_units == "mm"
    assert wrapper.model_depth == "0.01537meter"


class _SolutionData:
    def __init__(self, expression: str, real: float, unit: str) -> None:
        self._expression = expression
        self._real = real
        self.units_data = {expression: unit}

    def __bool__(self) -> bool:
        return True

    def get_expression_data(self, expression: str, part: str) -> tuple[list, list]:
        if expression != self._expression:
            raise KeyError(expression)
        return ([1e-4], [self._real] if part == "real" else [0.0])


class _Post:
    """Answers one expression at a time, and refuses a batch, as AEDT does."""

    def __init__(self, known: dict[str, tuple[float, str]]) -> None:
        self.known = known
        self.requests: list[list[str]] = []

    def get_solution_data(self, expressions: list[str]) -> Any:
        self.requests.append(list(expressions))
        if len(expressions) != 1:
            return None
        expression = expressions[0]
        if expression not in self.known:
            return None
        real, unit = self.known[expression]
        return _SolutionData(expression, real, unit)


def test_solution_values_converts_the_reported_unit_to_si() -> None:
    """AEDT reports a 2D matrix inductance in nH and its resistance in ohm.

    Taking the raw number as henries reported 10445.18 H for 10.445 uH.
    """
    app = _App()
    app.post = _Post(  # type: ignore[attr-defined]
        {
            "Matrix1.L(w1,w1)": (10445.17882338, "nH"),
            "Matrix1.R(w1,w1)": (0.01177671, "ohm"),
        }
    )

    values = LiveAppExtraction(app).solution_values(
        ("Matrix1.L(w1,w1)", "Matrix1.R(w1,w1)")
    )

    assert values["Matrix1.L(w1,w1)"].real == pytest.approx(1.044517882338e-05)
    assert values["Matrix1.R(w1,w1)"].real == pytest.approx(0.01177671)


def test_one_unknown_expression_does_not_cost_the_others() -> None:
    """A batched request returns nothing at all when one name is unknown, so
    every expression is asked for on its own."""
    app = _App()
    post = _Post({"CoreLoss": (1.25, "W")})
    app.post = post  # type: ignore[attr-defined]

    values = LiveAppExtraction(app).solution_values(("Total_Energy", "CoreLoss"))

    assert values == {"CoreLoss": pytest.approx(1.25 + 0j)}
    assert post.requests == [["Total_Energy"], ["CoreLoss"]]


def test_an_unrecognised_unit_yields_no_value_rather_than_a_wrong_one() -> None:
    app = _App()
    app.post = _Post({"CoreLoss": (1.25, "furlongs")})  # type: ignore[attr-defined]

    with pytest.raises(RuntimeError, match="no solution data"):
        LiveAppExtraction(app).solution_values(("CoreLoss",))


class _Setup:
    def __init__(self, name: str, profile: dict[int, object] | None) -> None:
        self.name = name
        self._profile = profile

    def get_profile(self) -> dict[int, object] | None:
        return self._profile


TABLE = (
    "Setup : Setup1\n"
    "Pass|Triangles|Total Energy (J)|Energy Error (%)|Delta Energy (%)|\n"
    "1|1832|1.204e-04|12.5|100|\n"
    "2|2417|1.288e-04|0.83|6.98|\n"
)


class _ExportingApp(_App):
    """Writes the convergence table AEDT's ExportConvergence produces."""

    def __init__(self, table: str | None = TABLE) -> None:
        super().__init__()
        self.setups = [_Setup("Setup1", None)]
        self.table = table
        self.exports: list[str] = []

    def export_convergence(self, setup: str, output_file: str) -> str:
        self.exports.append(setup)
        if self.table is None:
            raise RuntimeError("ExportConvergence failed")
        Path(output_file).write_text(self.table, encoding="utf-8")
        return output_file


def test_convergence_rows_come_from_the_exported_table() -> None:
    """`get_profile()` describes timing steps, not adaptive error, so walking it
    for an `error` attribute always came back empty and manifests carried no
    convergence data at all."""
    app = _ExportingApp()

    rows = LiveAppExtraction(app).convergence_rows("Setup1")

    assert rows == ((1, 12.5), (2, 0.83))
    assert app.exports == ["Setup1"]


def test_setup_convergence_summarises_the_last_pass() -> None:
    """Nothing implemented this, so every live solve raised at the analyze
    stage -- after the solve had already finished."""
    assert (
        LiveAppExtraction(_ExportingApp()).setup_convergence("Setup1")
        == "2 passes, 0.83% error"
    )


def test_setup_convergence_reports_a_failed_export_without_raising() -> None:
    summary = LiveAppExtraction(_ExportingApp(table=None)).setup_convergence("Setup1")

    assert "convergence not exposed" in summary
    assert "convergence export failed" in summary


def test_an_unsolved_setup_reads_as_an_empty_profile_not_a_failure() -> None:
    """AEDT writes the header for an unsolved setup, with no data rows."""
    header = TABLE.splitlines()[1] + "\n"

    summary = LiveAppExtraction(_ExportingApp(table=header)).setup_convergence("Setup1")

    assert summary == "convergence profile empty"


def test_an_unknown_setup_name_is_refused() -> None:
    app = _ExportingApp()

    with pytest.raises(RuntimeError, match="is not present"):
        LiveAppExtraction(app).convergence_rows("Setup2")
    assert app.exports == []


def test_private_attributes_stay_on_the_wrapper() -> None:
    app = _App()
    wrapper = LiveAppExtraction(app)

    assert wrapper._app is app  # noqa: SLF001 - the wrapper's own handle
    with pytest.raises(AttributeError):
        _ = app._app  # noqa: SLF001 - must not have been forwarded


class _Modeler:
    """Records the circle it was asked for and any rotation applied to it."""

    def __init__(self) -> None:
        self.circles: list[dict[str, Any]] = []
        self.rotations: list[dict[str, Any]] = []

    def create_circle(self, **kwargs: Any) -> str:
        self.circles.append(kwargs)
        return str(kwargs["name"])

    def rotate(self, assignment: str, axis: str, angle: float) -> None:
        self.rotations.append({"assignment": assignment, "axis": axis, "angle": angle})


def _placed_centre(modeler: _Modeler) -> tuple[float, float, float]:
    """Where the disc ends up, applying AEDT's rotate-about-the-global-axis."""
    x, y, z = modeler.circles[0]["origin"]
    for rotation in modeler.rotations:
        assert rotation["axis"] == "Z"
        theta = math.radians(rotation["angle"])
        x, y = x * math.cos(theta) - y * math.sin(theta), x * math.sin(theta) + y * math.cos(theta)
    return (x, y, z)


def test_a_radial_disc_lands_on_the_centre_it_was_asked_for() -> None:
    """AEDT rotates about the global axis through the origin, so a disc created
    at its true off-axis centre and then rotated is swung off the conductor. Two
    of four conductor sections read 2.5e-11 and 3.7e-10 A/m^2 that way, integrals
    of Mag_J over sheets sitting in air.
    """
    app = _App()
    modeler = _Modeler()
    app.modeler = modeler  # type: ignore[attr-defined]
    centre = (0.008, 0.011, 0.004)
    normal = (0.008 / math.hypot(0.008, 0.011), 0.011 / math.hypot(0.008, 0.011), 0.0)

    LiveAppExtraction(app).create_section_disc("Sec_face", centre, normal, 0.0005)

    assert modeler.circles[0]["orientation"] == "YZ"
    placed = _placed_centre(modeler)
    assert placed == pytest.approx(centre, abs=1e-12)


def test_an_axial_disc_is_placed_directly_and_never_rotated() -> None:
    app = _App()
    modeler = _Modeler()
    app.modeler = modeler  # type: ignore[attr-defined]
    centre = (0.008, 0.011, 0.004)

    LiveAppExtraction(app).create_section_disc("Sec_bore", centre, (0.0, 0.0, 1.0), 0.0005)

    assert modeler.circles[0]["orientation"] == "XY"
    assert modeler.circles[0]["origin"] == [0.008, 0.011, 0.004]
    assert modeler.rotations == []
