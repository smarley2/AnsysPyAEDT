from __future__ import annotations

import pytest

from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.naming import (
    core_name,
    lead_names,
    sanitize_identifier,
    terminal_names,
    turn_name,
    winding_names,
)
from inductor_designer.geometry.packing import WindingSpec, pack_winding


def test_sanitize() -> None:
    assert sanitize_identifier("w1") == "w1"
    assert sanitize_identifier("primary winding-a") == "primary_winding_a"
    assert sanitize_identifier("1w") == "W1w"
    with pytest.raises(ValueError):
        sanitize_identifier("")


def test_names() -> None:
    assert core_name() == "Core"
    assert turn_name("w1", 1, 7) == "w1_L01_T007"
    assert lead_names("w-1") == ("w_1_LeadIn", "w_1_LeadOut")
    assert terminal_names("w1") == ("w1_TermIn", "w1_TermOut")


def test_winding_names_cover_all_turns_in_order() -> None:
    core = FinishedCore(0.00973, 0.01683, 0.005715, 0.0)
    packing = pack_winding(core, WindingSpec("w1", 30, 0.001118, 0.0, 300.0, 0.0001, 0.001))
    names = winding_names(packing)
    assert len(names) == 30
    assert names[0] == "w1_L01_T001"
    assert len(set(names)) == 30
    assert names == tuple(sorted(names))
