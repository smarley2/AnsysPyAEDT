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
import tempfile
from pathlib import Path
from typing import Any

from inductor_designer.adapters.pyaedt.convergence_file import parse_convergence
from inductor_designer.adapters.pyaedt.field_reader import SURFACE

# Degrees of tolerance when deciding a disc normal is the machine axis.
_AXIS_TOLERANCE = 1e-9

# AEDT reports each traced quantity in the report's own display unit, not in SI:
# a 2D matrix inductance comes back in nH while its resistance comes back in
# ohm. Everything above this file is SI, so the unit AEDT states is applied
# here. An unrecognised unit yields no value at all rather than a number in an
# unknown scale -- reporting 10445.18 H for 10.445 uH is exactly the failure
# this guards.
_SI_PREFIXES = {
    "f": 1e-15,
    "p": 1e-12,
    "n": 1e-9,
    "u": 1e-6,
    "µ": 1e-6,
    "m": 1e-3,
    "k": 1e3,
    "K": 1e3,
    "M": 1e6,
    "G": 1e9,
}
_BASE_UNITS = frozenset({"H", "ohm", "Ohm", "W", "J", "A", "V", "T", "F", "S", "Hz"})


def si_scale(unit: str | None) -> float | None:
    """Factor turning a value in `unit` into SI, or None when unit is unknown."""
    if unit is None:
        return None
    stripped = unit.strip()
    if not stripped or stripped in _BASE_UNITS:
        return 1.0
    prefix, base = stripped[0], stripped[1:]
    if base in _BASE_UNITS and prefix in _SI_PREFIXES:
        return _SI_PREFIXES[prefix]
    return None


class LiveAppExtraction:
    """Mixin-style wrapper: `__getattr__` forwards to the wrapped application."""

    def __init__(self, app: Any) -> None:  # noqa: ANN401 - a PyAEDT application
        self._app = app

    def __getattr__(self, name: str) -> Any:  # noqa: ANN401 - forwarded verbatim
        return getattr(self._app, name)

    def __setattr__(self, name: str, value: Any) -> None:  # noqa: ANN401 - forwarded
        """Forward attribute writes to the wrapped application.

        `__getattr__` covers reads only. Without this, an adapter writing a
        PyAEDT *property* through the wrapper -- `app.model_depth = "0.015meter"`
        is the one that matters -- created a new attribute on the wrapper and
        the setter never ran, so the design silently kept AEDT's 1 m default
        depth and every 2D result came out scaled by 1 m / core height. Live 2D
        projects saved between 2026-08-10 and 2026-08-14 hold
        `ModelDepth='1meter'`; the runs before that wrapper hold the real depth.
        """
        if name.startswith("_"):
            super().__setattr__(name, value)
            return
        setattr(self._app, name, value)

    # -- scalar results -------------------------------------------------

    def solution_values(self, expressions: tuple[str, ...]) -> dict[str, complex]:
        """One request per expression, because AEDT answers a batch all-or-nothing.

        Asking for several expressions at once returns no data at all when any
        one of them is unknown to the design -- `Total_Energy` is not a 2D AC
        Magnetic quantity, and its presence in the list silently cost the run
        its winding inductance, resistance and core loss too ("The backend
        reported no per-winding results"). Verified live on AEDT 2025.2,
        2026-08-14. Per-expression requests cost one round trip each and let a
        missing quantity be exactly that.

        Values come back in SI, converted from the display unit AEDT states per
        trace in `units_data`.
        """
        values: dict[str, complex] = {}
        for expression in expressions:
            try:
                data = self._app.post.get_solution_data(expressions=[expression])
            except Exception:  # noqa: BLE001 - an absent quantity is not a failure
                continue
            if not data:
                continue
            try:
                _, real = data.get_expression_data(expression, "real")
                _, imaginary = data.get_expression_data(expression, "imag")
            except Exception:  # noqa: BLE001 - an absent quantity is not a failure
                continue
            if len(real) == 0:
                continue
            scale = si_scale(getattr(data, "units_data", {}).get(expression))
            if scale is None:
                continue
            imag_value = float(imaginary[-1]) if len(imaginary) else 0.0
            values[expression] = complex(float(real[-1]), imag_value) * scale
        if not values:
            raise RuntimeError("Maxwell returned no solution data for the request.")
        return values

    def setup_convergence(self, name: str) -> str:
        """One-line convergence summary for the analyze stage's message.

        PyAEDT has no such method, and nothing implemented it here, so every
        live solve raised `'Maxwell2d' object has no attribute
        'setup_convergence'` at the analyze stage -- after the solve itself had
        finished. Built from `convergence_rows`, so the message and the manifest
        rows can never disagree.
        """
        try:
            rows = self.convergence_rows(name)
        except RuntimeError as error:
            return f"convergence not exposed ({error})"
        if not rows:
            return "convergence profile empty"
        passes, error_percent = rows[-1]
        return f"{passes} passes, {error_percent:.4g}% error"

    def solve_status(self, name: str) -> str:
        """AEDT's own verdict on the finished solve, or "" when it states none.

        `Normal Completion` or `Engine Detected Error`, read from the setup
        profile. `Setup.is_solved` is True in both cases -- it was True for the
        run that lost its solver after one pass -- so it cannot be used for this.
        """
        setup = next((item for item in self._app.setups if item.name == name), None)
        if setup is None:
            return ""
        try:
            profile = setup.get_profile()
        except Exception:  # noqa: BLE001 - a missing profile states no verdict
            return ""
        entry = (profile or {}).get(name)
        status = getattr(entry, "status", None)
        return str(status) if status else ""

    def convergence_rows(self, name: str) -> tuple[tuple[int, float], ...]:
        """`(pass number, error percent)` per adaptive pass, via AEDT's export.

        `setup.get_profile()` returns a `Profiles` mapping keyed by setup name
        whose entries describe timing steps, not adaptive error, so walking it
        for an `error` attribute -- as this did until 2026-08-17 -- always came
        back empty and every manifest went out without convergence data.
        `ExportConvergence` writes the pass table instead, and
        `convergence_file` parses it.
        """
        setup = next((item for item in self._app.setups if item.name == name), None)
        if setup is None:
            raise RuntimeError(f"Setup {name!r} is not present in the design.")
        with tempfile.TemporaryDirectory(prefix="inductor-convergence-") as folder:
            target = Path(folder) / "convergence.prop"
            try:
                written = self._app.export_convergence(name, output_file=str(target))
            except Exception as error:  # noqa: BLE001 - reported, never raised on
                raise RuntimeError(f"convergence export failed: {error}") from error
            path = Path(str(written)) if written else target
            if not path.is_file():
                raise RuntimeError(
                    f"Setup {name!r} produced no convergence export at {path}."
                )
            return parse_convergence(path.read_text(encoding="utf-8", errors="replace"))

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

        A radial disc is built at azimuth zero and rotated onto its azimuth,
        because AEDT rotates about the global axis through the origin: a disc
        created at its true off-axis centre and then rotated is swung away from
        the conductor entirely. That is what happened until 2026-08-17 -- the
        two axial sections read 3.48 and 3.43 MA/m^2 while the two rotated ones
        read 2.5e-11 and 3.7e-10, integrals of `Mag_J` over sheets sitting in
        air. Starting on the +X axis makes the same rotation carry the centre to
        exactly where it belongs, since rotating (r, 0, z) about Z by the
        azimuth gives (r cos, r sin, z).
        """
        axial = abs(normal[0]) < _AXIS_TOLERANCE and abs(normal[1]) < _AXIS_TOLERANCE
        if axial:
            disc = self._app.modeler.create_circle(
                orientation="XY",
                origin=list(center_m),
                radius=radius_m,
                name=name,
                non_model=True,
            )
            return str(getattr(disc, "name", name))
        radius_from_axis = math.hypot(center_m[0], center_m[1])
        disc = self._app.modeler.create_circle(
            orientation="YZ",
            origin=[radius_from_axis, 0.0, center_m[2]],
            radius=radius_m,
            name=name,
            non_model=True,
        )
        created = getattr(disc, "name", name)
        # The centre's azimuth, not the normal's: it is the one the rotation has
        # to reproduce, and for these sections the radial normal shares it.
        angle = math.degrees(math.atan2(center_m[1], center_m[0]))
        if angle:
            self._app.modeler.rotate(created, axis="Z", angle=angle)
        return str(created)

    def desktop_messages(self) -> tuple[str, ...]:
        """AEDT's own message channel for this design, oldest first.

        The only place a solver's reason for dying is stated: on 2026-08-18 a
        run was recorded `succeeded` while this channel held "Unable to
        create child process: 3dedy". Session-scoped, so it must be read
        before the desktop is released.
        """
        try:
            messages = self._app.odesktop.GetMessages(
                self._app.project_name, self._app.design_name, 0
            )
        except Exception:  # noqa: BLE001 - a silent channel is not a failure
            return ()
        return tuple(str(line) for line in messages or ())
