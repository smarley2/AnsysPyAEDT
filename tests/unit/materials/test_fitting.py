from __future__ import annotations

import math

import pytest

from inductor_designer.materials.fitting import (
    LossSample,
    MaterialFitError,
    fit_steinmetz,
    mean_relative_permeability,
)


def test_fit_steinmetz_recovers_exact_synthetic_coefficients() -> None:
    samples = tuple(
        LossSample(frequency, flux_density, 2.5 * frequency**1.4 * flux_density**2.3)
        for frequency in (10_000.0, 50_000.0, 100_000.0)
        for flux_density in (0.05, 0.1, 0.2)
    )

    fit = fit_steinmetz(samples)

    assert fit.k == pytest.approx(2.5, abs=1e-6)
    assert fit.alpha == pytest.approx(1.4, abs=1e-6)
    assert fit.beta == pytest.approx(2.3, abs=1e-6)
    assert fit.rms_relative_residual == pytest.approx(0.0, abs=1e-9)
    assert fit.max_relative_residual == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize(
    "samples",
    [
        (
            LossSample(10_000.0, 0.05, 1.0),
            LossSample(10_000.0, 0.1, 2.0),
            LossSample(10_000.0, 0.2, 3.0),
        ),
        (
            LossSample(10_000.0, 0.1, 1.0),
            LossSample(20_000.0, 0.1, 2.0),
            LossSample(30_000.0, 0.1, 3.0),
        ),
        (
            LossSample(10_000.0, 0.1, 1.0),
            LossSample(20_000.0, 0.2, 2.0),
        ),
    ],
    ids=("single-frequency", "single-flux-density", "fewer-than-three"),
)
def test_fit_steinmetz_rejects_degenerate_samples(samples: tuple[LossSample, ...]) -> None:
    with pytest.raises(MaterialFitError):
        fit_steinmetz(samples)


@pytest.mark.parametrize("value_index", range(3))
def test_loss_sample_requires_positive_values(value_index: int) -> None:
    values = [10_000.0, 0.1, 1.0]
    values[value_index] = 0.0

    with pytest.raises(MaterialFitError):
        LossSample(*values)


def test_mean_relative_permeability_averages_linear_bh_points() -> None:
    mu0 = 4e-7 * math.pi
    bh_points = ((0.0, 0.0), (100.0, mu0 * 60.0 * 100.0), (250.0, mu0 * 60.0 * 250.0))

    assert mean_relative_permeability(bh_points) == 60.0
