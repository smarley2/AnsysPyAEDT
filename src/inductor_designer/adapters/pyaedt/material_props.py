"""Material handling shared by the Maxwell 2D and Maxwell 3D adapters."""

from __future__ import annotations

from typing import Any, Protocol

from inductor_designer.materials.records import SteinmetzFit
from inductor_designer.simulation.maxwell_plan import SOLUTION_TYPE, MaterialSpec


class AedtMaterial(Protocol):
    """The slice of a PyAEDT ``Material`` this correction needs."""

    _props: dict[str, Any]

    def update(self) -> bool: ...


class AedtCoreLossApp(Protocol):
    """The slice of a PyAEDT Maxwell application `enable_core_loss` needs."""

    def set_core_losses(
        self, assignment: Any, core_loss_on_field: bool = ...
    ) -> Any: ...


def enable_core_loss(
    app: AedtCoreLossApp,
    object_name: str,
    material: MaterialSpec,
    solution_type: str,
) -> str:
    """Switch AEDT's per-object core loss on, and say what was done.

    A core-loss definition in the material library is inert on its own: AEDT
    keeps a separate per-object flag (Excitations > Set Core Loss, whose dialog
    shows "Defined in Material" ticked while "Core Loss Setting" stays clear),
    and a solve with that flag off reports 0 W of core loss. Nothing enabled it
    until 2026-08-14.

    `core_loss_on_field` stays False: the loss is reported, but it is not fed
    back into the field solution, which is the AEDT default and what the
    reported quantities assume.
    """
    if material.steinmetz is None:
        return ""
    if solution_type != SOLUTION_TYPE:
        # PyAEDT raises for anything but AC Magnetic / Transient, and AEDT
        # itself offers no core-loss switch under AC Magnetic with DC.
        return (
            f" Core loss not enabled: solution type {solution_type} does not "
            "expose the per-object core-loss switch."
        )
    app.set_core_losses(assignment=[object_name], core_loss_on_field=False)
    return f" Core loss enabled on {object_name}."


def apply_steinmetz_unit_fix(material: AedtMaterial, fit: SteinmetzFit) -> None:
    """Rewrite the Power Ferrite coefficients PyAEDT tags with bogus units.

    ``Material.set_power_ferrite_coreloss`` hardcodes ``f"{cm}A_per_meter"`` and
    ``f"{x}tesla"`` (PyAEDT 1.2.0, ``modules/material.py`` lines 2937-2938), so a
    saved project holds ``core_loss_cm='28.766524299A_per_meter'`` and
    ``core_loss_x='1.311tesla'``. Steinmetz ``cm`` and ``x`` are not a field
    strength and not a flux density; Ansys' own shipped libraries write plain
    numbers, and PyAEDT's other core-loss setter does too.

    AEDT parses the magnitudes correctly, so results are unaffected, but the
    stored project misstates its own inputs. Overwrite both with plain numbers.

    Reaches into ``_props`` deliberately: PyAEDT exposes no public setter for
    these, and the alternative is shipping wrong units.
    """
    properties = material._props  # noqa: SLF001 - no public accessor exists
    properties["core_loss_cm"] = str(fit.k)
    properties["core_loss_x"] = str(fit.alpha)
    material.update()
