# ADR 0006: RMS Project Current and Peak Solver Excitation

- Status: Accepted
- Date: 2026-07-24

## Context

The existing `acMagnitudeA` name does not state whether it is RMS or peak.
Maxwell Eddy Current and FEMM AC inputs use peak amplitudes, while users
normally specify AC winding current in RMS. Leaving the convention implicit can
create a factor-of-`sqrt(2)` excitation and loss error.

## Decision

The UI, Project document, and Operating Point use explicit AC RMS current. The
solver-independent run planner converts it once with
`I_peak = I_rms * sqrt(2)`. Maxwell and FEMM adapters receive peak amplitudes
and perform no conversion. Run Manifests record both values, and normalized
field results identify peak and RMS conventions separately from DC components.

## Consequences

- User-facing current matches the intended engineering convention.
- Solver adapters keep the native peak-amplitude contract.
- Tests must detect missing or duplicate conversion.
- The new schema deliberately replaces ambiguous `acMagnitudeA`; no legacy
  project migration is required because no user Project documents are in use.

## References

- [Ansys Maxwell Eddy Current excitations](https://ansyshelp.ansys.com/public/Views/Secured/Electronics/v251/en/Subsystems/Maxwell/Content/Maxwell/EddyCurrentExcitations.htm)
- [FEMM FAQ: AC quantities use peak values](https://www.femm.info/doku/doku.php?id=faq)
