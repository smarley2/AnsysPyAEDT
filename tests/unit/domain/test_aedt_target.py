from __future__ import annotations

from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease, ModelDimension


def test_release_parse_round_trip() -> None:
    release = AedtRelease.parse("2025.2")
    assert release == AedtRelease(2025, 2)
    assert str(release) == "2025.2"


def test_domain_and_simulation_expose_the_same_types() -> None:
    from inductor_designer.simulation import capabilities

    assert capabilities.AedtRelease is AedtRelease
    assert capabilities.AedtEdition is AedtEdition
    assert capabilities.ModelDimension is ModelDimension
