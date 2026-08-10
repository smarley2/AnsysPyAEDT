"""Implements the result-extraction protocol over a real PyAEDT application.

A `Maxwell3d`/`Maxwell2d` object has no `solution_values`, `field_value` or
section-sheet methods; this wrapper adds exactly those and delegates everything
else untouched. The adapters therefore talk to one protocol, whether they hold
this wrapper or a test fake.

Every PyAEDT call in here is assumed until a live run proves it. That is the
deliberate seam: nothing above this file knows how AEDT names a quantity.
"""

from __future__ import annotations

import math
from typing import Any

from inductor_designer.adapters.pyaedt.field_reader import SURFACE

# Degrees of tolerance when deciding a disc normal is the machine axis.
_AXIS_TOLERANCE = 1e-9


class LiveAppExtraction:
    """Mixin-style wrapper: `__getattr__` forwards to the wrapped application."""

    def __init__(self, app: Any) -> None:  # noqa: ANN401 - a PyAEDT application
        self._app = app

    def __getattr__(self, name: str) -> Any:  # noqa: ANN401 - forwarded verbatim
        return getattr(self._app, name)

    # -- scalar results -------------------------------------------------

    def solution_values(self, expressions: tuple[str, ...]) -> dict[str, complex]:
        data = self._app.post.get_solution_data(expressions=list(expressions))
        if not data:
            raise RuntimeError("Maxwell returned no solution data for the request.")
        values: dict[str, complex] = {}
        for expression in expressions:
            try:
                _, real = data.get_expression_data(expression, "real")
                _, imaginary = data.get_expression_data(expression, "imag")
            except Exception:  # noqa: BLE001 - an absent quantity is not a failure
                continue
            if len(real) == 0:
                continue
            imag_value = float(imaginary[-1]) if len(imaginary) else 0.0
            values[expression] = complex(float(real[-1]), imag_value)
        return values

    def convergence_rows(self, name: str) -> tuple[tuple[int, float], ...]:
        setup = next(
            (item for item in self._app.setups if item.name == name), None
        )
        if setup is None:
            raise RuntimeError(f"Setup {name!r} is not present in the design.")
        profile = setup.get_profile()
        if not profile:
            raise RuntimeError(f"Setup {name!r} exposes no convergence profile.")
        rows: list[tuple[int, float]] = []
        for index, (_pass, entry) in enumerate(sorted(profile.items()), start=1):
            error = getattr(entry, "error", None)
            if error is None:
                continue
            rows.append((index, float(error)))
        return tuple(rows)

    # -- field results --------------------------------------------------

    def field_value(
        self,
        quantity: str,
        scalar_function: str,
        object_name: str,
        object_type: str = SURFACE,
    ) -> float:
        return float(
            self._app.post.get_scalar_field_value(
                quantity,
                scalar_function=scalar_function,
                object_name=object_name,
                object_type=object_type,
            )
        )

    def create_section_rectangle(
        self,
        name: str,
        azimuth_deg: float,
        r_inner_m: float,
        r_outer_m: float,
        half_height_m: float,
    ) -> str:
        """A core cut plane: an XZ rectangle rotated to the section azimuth."""
        sheet = self._app.modeler.create_rectangle(
            orientation="XZ",
            origin=[r_inner_m, 0.0, -half_height_m],
            sizes=[r_outer_m - r_inner_m, 2.0 * half_height_m],
            name=name,
            non_model=True,
        )
        created = getattr(sheet, "name", name)
        if azimuth_deg:
            self._app.modeler.rotate(created, axis="Z", angle=azimuth_deg)
        return str(created)

    def create_section_disc(
        self,
        name: str,
        center_m: tuple[float, float, float],
        normal: tuple[float, float, float],
        radius_m: float,
    ) -> str:
        """A conductor cut disc, perpendicular to the local wire direction.

        Selection only ever produces two normal families: axial, where the wire
        runs up the bore or down the outer wall, and radial, where it crosses a
        face. Both are one rotation away from an axis-aligned circle, so no
        arbitrary orientation is needed.
        """
        axial = abs(normal[0]) < _AXIS_TOLERANCE and abs(normal[1]) < _AXIS_TOLERANCE
        disc = self._app.modeler.create_circle(
            orientation="XY" if axial else "YZ",
            origin=list(center_m),
            radius=radius_m,
            name=name,
            non_model=True,
        )
        created = getattr(disc, "name", name)
        if not axial:
            angle = math.degrees(math.atan2(normal[1], normal[0]))
            if angle:
                self._app.modeler.rotate(created, axis="Z", angle=angle)
        return str(created)
