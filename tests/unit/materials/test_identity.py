from __future__ import annotations

import pytest

from inductor_designer.materials.identity import MaterialRef


def test_material_ref_holds_identity() -> None:
    ref = MaterialRef(manufacturer="Magnetics", name="Kool Mu", grade="60")
    assert ref.grade == "60"


@pytest.mark.parametrize("field", ["manufacturer", "name", "grade"])
def test_material_ref_rejects_blank_fields(field: str) -> None:
    values = {"manufacturer": "Magnetics", "name": "Kool Mu", "grade": "60"}
    values[field] = "  "
    with pytest.raises(ValueError, match=field):
        MaterialRef(**values)
