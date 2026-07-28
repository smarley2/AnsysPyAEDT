"""Corrections applied to material properties PyAEDT writes incorrectly."""

from __future__ import annotations

from typing import Any, Protocol

from inductor_designer.materials.records import SteinmetzFit


class AedtMaterial(Protocol):
    """The slice of a PyAEDT ``Material`` this correction needs."""

    _props: dict[str, Any]

    def update(self) -> bool: ...


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
