# V26A gate-order descriptive audit protocol

Date: 2026-09-24

This additive audit examines an implementation/description discrepancy in the
closed V26A experiment. It does not amend the frozen experiment or its NO-GO.
The user authorized the descriptive audit after code review reproduced the
discrepancy on a synthetic example.

## Question and fixed scope

The baseline queries the globally nearest motion-predicted target, then applies
the 9 um prediction and physical-step gates. It abstains if that target fails.
V26A filters all targets through both gates before ranking by physical step.
How often can this order difference matter in the frozen V25 histories?

- Use exactly the 16 archived V25 samples, validated against the existing V26A
  contract's archive identities and canonical source hashes.
- Reconstruct the baseline and verify all relink, V24.2 and V24.3 signatures
  before accepting any sample into the result.
- For each source before the final timepoint, retain its baseline predecessor.
  Inspect the original SciPy nearest target and all targets satisfying both
  inclusive 9 um gates. Count sources whose original target fails a gate while
  a feasible alternative exists. Keep their node IDs and distances.
- Evaluate the existing V26A *frame-local* decision on those same histories,
  keeping reverse mutuality fixed. Never feed these decisions into subsequent
  histories. Check analytical decisions against both existing linker functions.
- Record exact distance ties separately. A different selected target is not
  automatically a gate-order effect.
- Overlay archived V25 loss identities and archived V26A recovered identities
  only as descriptive intersections. Distinguish source exposure from choosing
  a mapped target. Do not recompute official matches or assign new correctness.
- Verify the V26A result archive identity and baseline signature for each sample.
- Confirm observer input graph signatures remain unchanged. Record dependency
  versions and audit/source hashes, raw denominators and per-sample results.

## Interpretation boundary

These are baseline-history local decisions, not a recursively applied new
tracker. Intersections with V26A recoveries cannot attribute recursive recoveries,
displacements, pruning changes or the +791 unmatched-edge ledger delta to this
mechanism. No independent validation, tuning, promotion, submission or biological
truth claim follows. Existing V25/V26A evidence and contracts remain immutable.

Run the audit with:

```powershell
.\.venv\Scripts\python.exe scripts/run_v26_a_gate_order_audit.py
```

The command writes only a new audit JSON, refuses to replace an existing result,
and does not require images, model inference, new labels or metric execution.
