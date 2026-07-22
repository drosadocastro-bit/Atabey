# Atabey Adversarial Battery

Date: 2026-07-20
Branch: `mitosis_hough_audit`
Status: fixed, append-only bounded regression battery

## Purpose

This battery protects the known failure modes discovered during V20 and V21 before any expensive 199-sample run. It is intentionally cheap: the executable checks use compact stored evidence and unit-scale synthetic behavior, while the documented cases preserve the exact real sample IDs and measurements needed for bounded reruns.

The battery is a gate, not a claim of biological completeness. Passing it means a change did not regress the failures already known. It does not establish full-cohort generalization.

## NIC Pattern Verified

The NIC source was inspected at commit `14649f157554d119106b1c60d8c42bf17893a532`.

NIC keeps a version-controlled adversarial corpus in `nic_adversarial_test.py`: 90 cases across eight categories are run together, evaluated with TP/TN/FP/FN accounting, and reported as a full-suite result. The checked-in report records 89/90, or 98.9%, with zero false negatives. NIC also has separate checked-in governance test suites.

The real repository supports the fixed full-suite regression pattern. An explicit machine-enforced "tests may never be removed" invariant was not found in the inspected NIC source. Atabey makes that policy explicit: the manifest is append-only, and the test suite contains a required baseline ID set so adding cases passes while silently removing any original case fails.

## Files

- Machine-readable registry: `tests/fixtures/atabey_adversarial_battery.json`
- Fast executable checks: `tests/test_atabey_adversarial_battery.py`
- Track B confidence routing checks: `tests/test_division_recovery_shadow.py`

Run before any bounded data rebuild or full-cohort run:

```powershell
python -m pytest tests/test_atabey_adversarial_battery.py tests/test_division_recovery_shadow.py tests/test_division_firewall.py -q
```

## Fixed Cases

| Case ID | Type | Evidence | Required outcome |
| --- | --- | --- | --- |
| `COLLISION-DRIFT-090` | collision noise | lower edge of known 90-110 degree drift band | rejected |
| `COLLISION-DRIFT-100` | collision noise | center of known drift band | rejected |
| `COLLISION-DRIFT-110` | collision noise | upper edge of known drift band | rejected |
| `V19-TP-05DB` | known true division | `6bba_05db0fb1`, GT parent `25000381`, angle 135.896, ratio 1.109 | retained as extractive evidence unless a calibrated confidence exists |
| `V19-TP-B329` | known true division | `6bba_b329af44`, GT parent `83001755`, drift 11.213, growth 1.495 | retained as extractive evidence unless a calibrated confidence exists |
| `V19-TP-EBDF` | known true division | `6bba_ebdf3b34`, GT parent `85001151`, angle 154.597, ratio 2.015 | retained as extractive evidence unless a calibrated confidence exists |
| `V21-FN-EBDF-PAIRING` | upstream pairing loss | parent `t13:cf520`; correct daughters `t14:cf601` and `t14:cf555`; wrong primary `t14:cf31` | remain diagnosed as candidate-formation loss, not ranking failure |
| `LINK-GATE-14-REGRESSION-05DB` | formation-gate regression | 9 um retained the known TP; 14 um replaced the correct orphan and lost it | keep global formation gate at 9 um |

## Confidence-Gate Expectations

The confidence threshold starts at 0.60 only as an architectural hypothesis inspired by NIC. The failed Track B ranking score is not a probability and must never be passed into the confidence gate as if it were calibrated.

Current policy:

- geometrically rejected candidates remain `rejected`;
- accepted candidates with calibrated confidence at or above 0.60 become `division_proposal`;
- accepted candidates below 0.60, or without a calibrated confidence, become `extractive_flagged`;
- extractive candidates retain node IDs, mechanism, geometry, density, volume, intensity, and score evidence;
- no confidence disposition mutates Track A or the lineage graph.

The current three-sample evidence is insufficient to fit a credible confidence calibrator. Until more positive labels exist, the correct default is therefore `extractive_flagged`, not a fabricated confidence.

## Accumulation Rule

When a new failure is found:

1. Add a new unique case to the JSON manifest.
2. Add or extend a cheap executable assertion that captures the failure.
3. Keep every existing case ID.
4. Run the full battery before bounded sample work.
5. Run a bounded real-data reproduction only after the cheap battery passes.
6. Start a 199-sample run only after both stages pass.

Changing Track A, Track B, confidence routing, or candidate formation without running this battery is a validation failure.
