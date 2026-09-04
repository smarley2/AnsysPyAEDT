# M11a: the gapped E core, solver-independent

- Status: Approved 2026-09-04 by Fabio Posser
- Milestone: 11a (the first of Milestone 11's families)
- Scope boundary: everything verifiable without AEDT. The Maxwell/FEMM
  mapping and live evidence are 11b.

Milestone 11 as written ("E, PQ, EQ, EER, and other approved commercial
geometries") is four families, each of which its own exit criterion says
needs "its own approved design, catalog/schema needs, geometry invariants,
preview, solver mapping, fixtures, and live evidence". It decomposes. This is
the first family, split again along the line of what this machine can verify:

- **11a (this spec):** the family seam, the E-core body, the gaps, winding
  placement on a leg, packing, the preview, the schema change, and the
  preliminary estimate. All of it testable with no AEDT session.
- **11b:** Maxwell 3D/2D and FEMM export, plus live evidence.
- **11c and later:** PQ, EQ, EER against the proven seam, and E-core catalog
  records.

## What 11a can ship, and why it is the manual core

There are no E-core records in `catalog/` and no E-core datasheet
transcription exists. Transcribing datasheets is human work, so 11a ships the
**manual gapped E core** -- you enter the dimensions and the gaps -- exactly
as the toroid path already lets someone work without a catalog part
(`ManualCoreSelection`). E-core catalog records and their template columns are
11c, with the transcription.

## The seam

`CoreSelection` is already a union (`CatalogCoreSelection |
ManualCoreSelection`), so the family joins it rather than mutating anything:
`ManualECoreSelection` now, `CatalogECoreSelection` in 11c.

Underneath, one component per family: `geometry/toroid/` and
`geometry/ecore/`, each owning its body type, packer, turn path, mesh and
profile. The existing toroid modules **move unchanged**; no toroid function
learns what a leg is. `FinishedCore` stays what its docstring says it is --
`r_inner_m`, `r_outer_m`, `half_height_m`, `corner_radius_m`, a toroid -- and
the E core gets `FinishedECore`. `GeometryModel` holds whichever body the
family produced.

The design spec's rule is the constraint here: later families arrive "without
changing the toroid implementation into a universal monolith". The seam's
acceptance criterion is therefore that every existing toroid geometry and
preview test passes unchanged after the move.

## The domain, and the schema

`WindingDefinition.start_angle_deg` / `.sector_deg` are toroid coordinates.
They become a `placement` union:

- `ToroidPlacement(start_angle_deg, sector_deg)` -- the same two fields,
  unchanged.
- `LegPlacement(leg, window_start_m, window_span_m)` -- which leg, and the
  span of the winding window it occupies, the one-for-one analogue of the
  toroid's start and sector. `leg` is `CENTRE` only in 11a; the field exists
  because outer-leg winding is a later family's problem, not because anything
  reads another value today.

That is project schema **v6, replace-and-refuse**: a v5 document does not
open, and `SchemaRepository.validate_project` reports it the way it already
reports any other version. Ruled by Fabio Posser on 2026-09-04, consistent
with every previous bump (v3, v4, v5 each replaced their predecessor and no
migration has ever been written).

Why that is safe *now*, recorded because it will not stay true: before 0.2.0
the installed application could neither open nor create a project, so
essentially no v5 documents exist outside this repository's fixtures. Once
other people have saved designs, the next bump is a different decision and
this precedent should not be cited for it.

## The E-core body

Six independent dimensions describe an E+E pair (both halves identical,
mirrored). Overall width and height are derived, never entered twice -- the
same rule the toroid's four dimensions follow:

| Symbol | Field | Meaning |
| --- | --- | --- |
| F | `centre_leg_width_m` | centre leg width |
| C | `depth_m` | stack depth |
| E | `window_width_m` | centre-leg face to outer-leg inner face |
| D | `window_height_m` | window height per half |
| G | `outer_leg_width_m` | outer leg width |
| H | `yoke_thickness_m` | back plate thickness |

Derived: `A = F + 2E + 2G` (overall width), `B = 2(D + H)` (overall height).

Refused, as `CoreGeometryError`, the way `FinishedCore` already refuses its
own out-of-range dimensions: any non-finite or non-positive dimension.

## The gaps

On the centre leg: a tuple of gap lengths, and the lengths of the core
segments separating them. Zero gaps is legal and means an ungapped pair. A
flag, `outer_legs_gapped`, selects between the two builds:

- **False** -- the ground-centre-leg build: outer legs stay mated.
- **True** -- the shim build: a spacer gaps all three legs, so each outer leg
  carries the same gap stack.

Refused: a non-finite or negative length; a total gap plus spacing exceeding
the centre leg length `2D`.

Distributed gaps exist to keep fringing flux away from the winding, which is
why the user specifies several small gaps rather than one large one. Note the
consequence for this milestone, stated rather than buried: with fringing
ignored (below), N gaps totalling `L` are indistinguishable from one gap of
`L`. That is not a bug in the estimate; it is the estimate's honest limit,
and 11b's solve is what shows the difference.

## The magnetic model: a reluctance network

An E core's sections have genuinely different areas, so collapsing them into
one `l_e / A_e` would bury the assumption. Sections, for the pair:

| Section | Area | Centreline length |
| --- | --- | --- |
| Centre leg (iron) | `A_c = F·C` | `2D - g_total` |
| Centre gaps | `A_c` | each `g_i` |
| Each yoke (2 in series) | `A_y = H·C` | `E + F/2 + G/2` |
| Each outer leg (2 in parallel) | `A_o = G·C` | `2D - g_outer_total` |
| Outer gaps, when `outer_legs_gapped` | `A_o` | each `g_i` |

Series along the loop, the two outer legs in parallel:

```
R_iron  = (2D - g_total)/(mu_r*mu_0*A_c)
        + 2*(E + F/2 + G/2)/(mu_r*mu_0*A_y)
        + (2D - g_outer_total)/(2*mu_r*mu_0*A_o)

R_gap   = sum_i g_i/(mu_0*A_c)
        + sum_i g_outer_i/(2*mu_0*A_o)

L = N^2 / (R_iron + R_gap)
```

### Why this needs only one new number downstream

Every iron term carries `1/mu_r` and every gap term does not, and the
parallel branch is a linear factor of one half, so the network separates
**exactly** -- not approximately -- into two lengths referred to the
centre-leg area:

```
path_length_m (iron, referred to A_c) = A_c * sum_iron (l_i / A_i)
gap_length_m  (gap,  referred to A_c) = A_c * sum_gap  (g_j / A_j)

R_total = path_length_m/(mu_r*mu_0*A_c) + gap_length_m/(mu_0*A_c)
```

So `CoreMagneticProperties` gains one field, `gap_length_m`, defaulting to
`0.0`. Every existing toroid and catalog-core result is unchanged by
construction, and that is asserted rather than assumed.

This matters because `magnetic_estimate.field_strengths` computes `H = NI/l_e`
today, which is right for an ungapped core and badly wrong for a gapped one:
most of the ampere-turns drop across the gap, so `NI/l_e` would report an iron
field strength several times too high. With `gap_length_m` present, flux comes
from the network -- `phi = NI/R_total`, `B = phi/A_c` -- and the iron field
strength follows from `B`, rather than from the ampere-turns directly.

Reported alongside: `effective_area_m2 = A_c` (the standard convention,
flux density quoted against the centre leg), `volume_m3` = the iron volume
`A_c*(2D - g_total) + 2*A*H*C + 2*G*C*(2D - g_outer_total)`, and
`al_value_nh = None` -- a manual core has no published inductance factor, so
the A_L cross-check reports itself unavailable exactly as it does for a
manual toroid.

### Fringing is ignored, and says so

`inductance_estimate.INDUCTANCE_EXCLUSION_NOTE` already states that the
estimate "excludes air-gap fringing, leakage inductance, and winding
self-capacitance". This keeps one honest story instead of adding a fringing
correction no datasheet publishes.

The consequence, stated because it is not small: ignoring fringing
**understates** reluctance and therefore **overstates** inductance, and the
error grows with gap length. A new provenance note says so wherever a gapped
estimate is reported, and 11b's solve is the answer.

## Winding placement and packing

`ecore/packing.py` is the direct analogue of the toroid's angular packer:
layers outward from the centre leg face, turns per layer
`floor(window_span_m / (d + spacing))`, layer count limited by
`floor(window_width_m / (d + spacing))`, and a refusal in the same shape the
toroid already produces ("Winding does not fit the window at layer 1"). Two
windings share the window by taking different spans, so the existing
clearance check keeps working on the idea it already implements.

Turn length per layer is the rounded rectangle around the centre leg at that
layer, expressed with the `LineSegment` and `ArcSegment` primitives that
already exist -- no new primitive.

## The preview

Almost nothing new is needed, which is worth stating so the change stays
small: `PreviewEntry` wraps a triangle mesh and a colour and is already
family-agnostic (a mesh builder is all the 3D view needs), and
`CutPlaneCircle` is already Cartesian (`x_mm`, `y_mm`).

The one real change: `CutPlaneDrawing` carries `r_inner_mm` / `r_outer_mm`
and the QML draws the core as two arcs. That becomes
`outline: tuple[CutPlaneShape, ...]`, where a shape is a circle or a
rectangle, so one renderer draws both families -- the toroid emitting its two
circles, the E core its legs and yokes, with each gap drawn as a break in the
centre leg. Keeping the radii *and* adding rectangles would leave every
drawing half-populated, which is the monolith this milestone exists to avoid.

## Tests

Red first, each at the level its rule lives at.

1. The reluctance network against a hand-computed value for one fully
   specified geometry, so the formulas above are pinned to a number.
2. A gapped pair has lower inductance than the same pair ungapped, and
   inductance falls as total gap grows.
3. N distributed gaps totalling `L` give the same reluctance as one gap of
   `L`. This pins the fringing assumption: adding a fringing correction later
   fails this test loudly, which is the point.
4. `outer_legs_gapped` changes the result in the direction the network says,
   and by the amount it says.
5. Gap plus spacing longer than the centre leg is refused; non-finite and
   negative dimensions and gaps are refused.
6. Window packing capacity, and its refusal when the wire does not fit.
7. `gap_length_m` defaults to `0.0`, and every existing toroid estimate is
   numerically unchanged -- the separation above is exact, so this must hold
   to the last digit.
8. A v5 project document is refused by version, naming v6.
9. Every existing toroid geometry and preview test passes unchanged after the
   move. This is the seam's real acceptance criterion.
10. The cut plane emits a rectangle outline for an E core and two circles for
    a toroid, and the rendered QML draws both -- asserted on the drawing the
    QML receives, not only on the Python side.

## Out of scope

- **E-core catalog records and template columns.** Datasheet transcription is
  human work, and the flat import template would need family-specific
  columns. That is 11c, with the records.
- **Outer-leg windings.** The `leg` field exists; only `CENTRE` is read.
- **Fringing corrections**, per the decision above.
- **Maxwell and FEMM export, and any live evidence.** That is 11b, and it
  needs an AEDT session.
- **PQ, EQ, EER.** They reuse this seam once it exists.
