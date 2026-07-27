# V22 E016 Semantic Feature Availability Addendum

Date: 2026-07-27
Status: preregistered feature scope; training not yet run

The E016 peak export contains no intensity or component-volume measurements.
Across 211,328 action rows, `volume_conservation_error` and
`intensity_conservation_error` are 0% complete. They are therefore excluded,
not imputed.

The decision-eligible metadata head is limited to:

- mean and minimum detector confidence;
- parent local density within 10 um;
- daughter local densities within 10 um.

Ownership margins, distances, angles, velocities, prediction errors, ranks,
and ground-truth-derived fields are prohibited model inputs. Unknown actions
remain unknown and are retained in held-out ranking pools.

Machine-readable contract: `tests/fixtures/v22_e016_available_metadata_semantic_ranker.json`

This is a bounded E016 metadata-ranking experiment. It is not appearance
semantic evidence, and it does not authorize assignment or graph mutation.
