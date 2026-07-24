from pathlib import Path

import pytest

from tools.femm_material_evidence import read_material_bh_points


def test_reads_exact_bh_points_for_named_material(tmp_path: Path) -> None:
    fem = tmp_path / "material.fem"
    fem.write_text(
        """\
[BlockProps] = 2
<BeginBlock>
<BlockName> = "Air"
<BHPoints> = 0
<EndBlock>
<BeginBlock>
<BlockName> = "Magnetics_High_Flux_60_rabc123"
<BHPoints> = 3
0 0
0.05 100
0.10 250
<d_lam> = 0
<EndBlock>
""",
        encoding="utf-8",
    )

    assert read_material_bh_points(
        fem,
        "Magnetics_High_Flux_60_rabc123",
    ) == ((0.0, 0.0), (0.05, 100.0), (0.10, 250.0))


def test_missing_material_is_rejected(tmp_path: Path) -> None:
    fem = tmp_path / "material.fem"
    fem.write_text("<BeginBlock>\n<BlockName> = \"Air\"\n<EndBlock>\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Magnetics_High_Flux_60_rabc123"):
        read_material_bh_points(fem, "Magnetics_High_Flux_60_rabc123")


def test_malformed_bh_point_count_is_rejected(tmp_path: Path) -> None:
    fem = tmp_path / "material.fem"
    fem.write_text(
        """\
<BeginBlock>
<BlockName> = "Magnetics_High_Flux_60_rabc123"
<BHPoints> = 2
0 0
<d_lam> = 0
<EndBlock>
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Magnetics_High_Flux_60_rabc123"):
        read_material_bh_points(fem, "Magnetics_High_Flux_60_rabc123")
