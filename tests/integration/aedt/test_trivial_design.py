import os
from pathlib import Path

import pytest

from inductor_designer.adapters.pyaedt.gateway import PyaedtGateway
from inductor_designer.application.ports.aedt_gateway import AedtProbeRequest
from inductor_designer.simulation.capabilities import AedtEdition, AedtRelease


@pytest.mark.aedt
def test_real_aedt_creates_and_saves_both_dimensions(tmp_path: Path) -> None:
    release = os.environ.get("INDUCTOR_AEDT_RELEASE")
    edition = os.environ.get("INDUCTOR_AEDT_EDITION")
    if release is None or edition is None:
        pytest.skip("Set INDUCTOR_AEDT_RELEASE and INDUCTOR_AEDT_EDITION")

    result = PyaedtGateway().run_probe(
        AedtProbeRequest(
            release=AedtRelease.parse(release),
            edition=AedtEdition(edition),
            non_graphical=False,
            output_directory=tmp_path,
        )
    )

    assert [artifact.created for artifact in result.artifacts] == [True, True]
    assert [artifact.saved for artifact in result.artifacts] == [True, True]
