"""The toroid family: one wound annular core.

Design: ``docs/superpowers/specs/2026-09-04-m11a-gapped-e-core-design.md``.

These modules were the whole of ``geometry/`` until the E-core family arrived,
and they moved here unchanged. Nothing in this package knows what a leg is,
and nothing in ``geometry/ecore/`` knows what an azimuth is; the two meet only
at ``GeometryModel``. That separation is the milestone's own rule -- later
families arrive "without changing the toroid implementation into a universal
monolith" -- and the acceptance criterion for the move was that every
existing toroid test passed with nothing but its import lines touched.
"""
