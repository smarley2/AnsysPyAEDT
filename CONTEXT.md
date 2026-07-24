# Inductor Designer

This context describes a toroidal-inductor design, the operating conditions
applied to it, and the solver runs derived from it. The editable design remains
independent from any generated solver project.

## Language

**Design**:
The backend-independent description of one inductor, including its core,
windings, conductors, materials, and geometry choices.
_Avoid_: Solver project, AEDT design

**Project document**:
A shareable `*.inductor.json` document containing one Design, its Operating
Point, and its Simulation Recipe.
_Avoid_: AEDT project, run file

**Catalog core**:
A core selected from a traceable manufacturer catalog record and its immutable
snapshot.
_Avoid_: Standard core

**Manual core**:
A toroidal core whose dimensions are entered by the user rather than selected
from a catalog. It may represent a custom design.
_Avoid_: Generic core

**Operating Point**:
One global frequency together with each winding's AC RMS current, phase, and
optional DC current. One solver run evaluates exactly one Operating Point.
_Avoid_: Sweep, excitation file

**Simulation Recipe**:
Backend-independent mesh, convergence, and requested-result intent associated
with a Project document.
_Avoid_: AEDT setup, FEMM problem

**Run Request**:
The choice to generate or solve a Design with Maxwell 3D, Maxwell 2D, or FEMM
at its Operating Point.
_Avoid_: Design mode, project dimension

**Run Manifest**:
The immutable record of the effective inputs, backend, versions, assumptions,
approximations, stages, and artifacts produced by one Run Request.
_Avoid_: Project document, log

**Normalized Result Set**:
Backend-labeled simulation results expressed with shared quantity names,
conventions, availability states, and warnings.
_Avoid_: Solver report

**Generate Only**:
A Run Request that creates a solver artifact without starting its analysis.

**Generate and Solve**:
A Run Request that creates the solver artifact, runs the analysis, and extracts
a Normalized Result Set.

**Geometry-Only AEDT Project**:
A deliberately incomplete Maxwell 3D artifact containing the core and winding
geometry but no setup or excitation because the core material is unresolved.
_Avoid_: Ready-to-solve project

**Area-Weighted Mean**:
The integral of a field magnitude over an evaluated cross-sectional area,
divided by that area.
_Avoid_: Average, volume average

**Representative Cross Section**:
A deterministic surface used to evaluate three-dimensional field maxima and
Area-Weighted Means. Every selected section is recorded in the Run Manifest.

**Symmetry Suggestion**:
An informational observation that a Design may be periodic. It never changes
the generated full model.
_Avoid_: Symmetry mode, automatic symmetry

## Flagged ambiguities

- **Project** without a qualifier is ambiguous. Use **Project document** for
  `*.inductor.json` and **AEDT project** for generated `*.aedt` output.
- **Current** without a qualifier is ambiguous for AC. Use **AC RMS current**,
  **AC peak current**, or **DC current**.
- **2D/3D mode** is not a Design property. Use the backend named by a
  **Run Request**.

## Example dialogue

> **Engineer:** Does this Design belong to Maxwell 3D?
>
> **Domain expert:** No. The Project document is backend-independent. Choose
> Maxwell 3D in a Run Request.
>
> **Engineer:** The Manual core has no material. Can I still generate it?
>
> **Domain expert:** Yes, as a confirmed Geometry-Only AEDT Project. You cannot
> Generate and Solve until the material is resolved.
>
> **Engineer:** Should I send the stored winding current directly to Maxwell?
>
> **Domain expert:** No. The Operating Point stores AC RMS current. The
> solver-independent plan converts it to AC peak current, and the Run Manifest
> records both values.
