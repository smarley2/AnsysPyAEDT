# DC Operating-Point Compatibility

`select_dc_bias_strategy` remains the single current decision point until M6
replaces the historical compatibility model. Only observed AEDT 2025 R2
Commercial capability may unlock native DC bias.

| Situation | Behavior |
| --- | --- |
| Maxwell 3D, reviewed AEDT 2025 R2 Commercial capability | Native `AC Magnetic with DC` |
| Maxwell 2D | Blocked until a supported policy is live-validated |
| FEMM | Blocked until a supported policy is live-validated |
| Missing, unreviewed, or different AEDT target | Blocked |

There is no AEDT 2024 R2 magnetostatic-incremental fallback in the product
scope. Unsupported DC operating points are recorded and blocked rather than
approximated.

## Verified AEDT 2025 R2 behavior

Live verification on 2026-07-17 established that native DC bias uses the design
solution type `AC Magnetic with DC` (mapped by PyAEDT to
`DCBiasedEddyCurrent`). It is not an `IncludeDcFields` setup property.

Per-winding DC is set through:

```text
winding.props["DC Current"] = "<value>A"
winding.update()
```

AEDT persisted only the exact `DC Current` property name. Historical
`DCCurrent` and `DCValue` guesses were silently ignored and must not return.

Every run with DC bias records the strategy, applied DC current per winding,
backend, exact AEDT/PyAEDT versions, and whether the requested result separates
DC and AC components. A backend that cannot provide a defensible combined field
maximum marks that quantity unavailable.
