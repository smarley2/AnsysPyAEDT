"""The E-core family: an E+E pair, optionally gapped on its legs.

Design: ``docs/superpowers/specs/2026-09-04-m11a-gapped-e-core-design.md``.

A family component, not an extension of the toroid. Nothing in
``geometry/toroid/`` knows what a leg is, and nothing here knows what an
azimuth is; the two meet only at ``GeometryModel``.
"""
