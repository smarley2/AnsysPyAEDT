from __future__ import annotations

from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.primitives import Vec3
from inductor_designer.geometry.terminals import build_terminal_disk

CORE = FinishedCore(r_inner_m=0.01, r_outer_m=0.02, half_height_m=0.005, corner_radius_m=0.0)


def test_disk_sits_at_bottom_run_midpoint() -> None:
    disk = build_terminal_disk(
        CORE, layer=1, insulated_diameter_m=0.001, bare_diameter_m=0.0008, station_deg=0.0
    )
    # layer 1 radial build = 0.0005; bottom run at z = -(0.005 + 0.0005)
    assert disk.center == Vec3(0.015, 0.0, -0.0055)
    assert disk.radius_m == 0.0004
    assert disk.normal == Vec3(1.0, 0.0, 0.0)


def test_disk_rotates_with_station() -> None:
    disk = build_terminal_disk(
        CORE, layer=1, insulated_diameter_m=0.001, bare_diameter_m=0.0008, station_deg=90.0
    )
    assert disk.center == Vec3(0.0, 0.015, -0.0055)
    assert disk.normal == Vec3(0.0, 1.0, 0.0)
