from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from inductor_designer.materials.records import SteinmetzFit

MU0 = 4e-7 * math.pi


class MaterialFitError(ValueError):
    """Raised when material data cannot produce the requested fit."""


@dataclass(frozen=True, slots=True)
class LossSample:
    frequency_hz: float
    flux_density_t: float
    loss_w_per_m3: float

    def __post_init__(self) -> None:
        if self.frequency_hz <= 0 or self.flux_density_t <= 0 or self.loss_w_per_m3 <= 0:
            raise MaterialFitError("loss sample values must be positive")


def _determinant(matrix: tuple[tuple[float, float, float], ...]) -> float:
    a, b, c = matrix
    return (
        a[0] * (b[1] * c[2] - b[2] * c[1])
        - a[1] * (b[0] * c[2] - b[2] * c[0])
        + a[2] * (b[0] * c[1] - b[1] * c[0])
    )


def fit_steinmetz(samples: Sequence[LossSample]) -> SteinmetzFit:
    """Fit Steinmetz coefficients by least squares in log10 space."""
    if len(samples) < 3:
        raise MaterialFitError("at least three loss samples are required")
    if len({sample.frequency_hz for sample in samples}) < 2:
        raise MaterialFitError("at least two distinct frequencies are required")
    if len({sample.flux_density_t for sample in samples}) < 2:
        raise MaterialFitError("at least two distinct flux densities are required")

    rows = tuple(
        (
            math.log10(sample.frequency_hz),
            math.log10(sample.flux_density_t),
            math.log10(sample.loss_w_per_m3),
        )
        for sample in samples
    )
    count = float(len(rows))
    sum_f = sum(frequency for frequency, _, _ in rows)
    sum_b = sum(flux_density for _, flux_density, _ in rows)
    matrix = (
        (count, sum_f, sum_b),
        (sum_f, sum(frequency**2 for frequency, _, _ in rows), sum(f * b for f, b, _ in rows)),
        (sum_b, sum(f * b for f, b, _ in rows), sum(b**2 for _, b, _ in rows)),
    )
    right_hand_side = (
        sum(loss for _, _, loss in rows),
        sum(frequency * loss for frequency, _, loss in rows),
        sum(flux_density * loss for _, flux_density, loss in rows),
    )
    denominator = _determinant(matrix)
    if denominator == 0.0:
        raise MaterialFitError("loss samples do not define an independent fit")

    log_k = _determinant(
        (
            (right_hand_side[0], matrix[0][1], matrix[0][2]),
            (right_hand_side[1], matrix[1][1], matrix[1][2]),
            (right_hand_side[2], matrix[2][1], matrix[2][2]),
        )
    ) / denominator
    alpha = _determinant(
        (
            (matrix[0][0], right_hand_side[0], matrix[0][2]),
            (matrix[1][0], right_hand_side[1], matrix[1][2]),
            (matrix[2][0], right_hand_side[2], matrix[2][2]),
        )
    ) / denominator
    beta = _determinant(
        (
            (matrix[0][0], matrix[0][1], right_hand_side[0]),
            (matrix[1][0], matrix[1][1], right_hand_side[1]),
            (matrix[2][0], matrix[2][1], right_hand_side[2]),
        )
    ) / denominator
    k = 10.0**log_k
    relative_residuals = tuple(
        (k * sample.frequency_hz**alpha * sample.flux_density_t**beta - sample.loss_w_per_m3)
        / sample.loss_w_per_m3
        for sample in samples
    )
    rms_residual = math.sqrt(sum(residual**2 for residual in relative_residuals) / len(samples))

    return SteinmetzFit(
        k=round(k, 9),
        alpha=round(alpha, 9),
        beta=round(beta, 9),
        rms_relative_residual=round(rms_residual, 9),
        max_relative_residual=round(max(abs(value) for value in relative_residuals), 9),
    )


def mean_relative_permeability(bh_points: Sequence[tuple[float, float]]) -> float:
    """Return average relative permeability for B-H points where H is positive."""
    values = tuple(
        flux_density / (MU0 * field_strength)
        for field_strength, flux_density in bh_points
        if field_strength > 0
    )
    if not values:
        raise MaterialFitError("at least one B-H point with positive H is required")
    return round(sum(values) / len(values), 9)
