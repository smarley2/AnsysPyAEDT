"""Advice must reach the manifest, next to the raw diagnostic, never instead of it."""

from __future__ import annotations

from inductor_designer.application.services.maxwell_export import _with_advice
from inductor_designer.simulation.failure_advice import AdviceCode


def test_advice_is_appended_after_each_diagnostic() -> None:
    advised = _with_advice(("License checkout failed: no license available",))
    assert advised[0] == "License checkout failed: no license available"
    assert advised[1].startswith(f"{AdviceCode.LICENSE_UNAVAILABLE}: ")


def test_no_diagnostics_stay_no_diagnostics() -> None:
    assert _with_advice(()) == ()
