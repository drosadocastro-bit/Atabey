import sys
from pathlib import Path

from atabey.evaluation.official_association_forensics import (
    OfficialAssociationCorrespondence,
    OfficialEdgeCorrespondence,
    OfficialNodeCorrespondence,
)
from atabey.tracking.association_forensics import (
    AssociationCandidate,
    AssociationFrameAudit,
    AssociationGraphAudit,
)


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from run_v25_upstream_association_forensics import (
    _atomic_gzip_json,
    _read_gzip_json,
    classify_v19_credited_losses,
)


def _correspondence(*, matched: bool) -> OfficialAssociationCorrespondence:
    return OfficialAssociationCorrespondence(
        nodes=(
            OfficialNodeCorrespondence("source", 10),
            OfficialNodeCorrespondence("target", 11),
        ),
        edges=(
            OfficialEdgeCorrespondence(
                "source", "target", 10, 11, matched
            ),
        ),
    )


def test_classifies_v19_credited_candidate_that_entered_and_lost() -> None:
    candidate = AssociationCandidate(
        "source", "target", 0, 1, 2, 2.0, 2.0, "source", True, False, False
    )
    audit = AssociationGraphAudit(
        "sample", (AssociationFrameAudit(0, (candidate,), ()),), True
    )

    records = classify_v19_credited_losses(
        audit,
        _correspondence(matched=False),
        _correspondence(matched=True),
        _correspondence(matched=False),
        adjustment_only_effect=False,
    )

    assert len(records) == 1
    assert records[0]["correct_candidate_present"] is True
    assert records[0]["correct_candidate_accepted"] is False
    assert records[0]["failure_class"] == "candidate_selection_ranking_failure"


def test_ignores_edges_not_credited_by_v19() -> None:
    audit = AssociationGraphAudit("sample", (), True)

    assert classify_v19_credited_losses(
        audit,
        _correspondence(matched=False),
        _correspondence(matched=False),
        _correspondence(matched=False),
        adjustment_only_effect=False,
    ) == []


def test_gzip_artifacts_are_byte_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first.json.gz"
    second = tmp_path / "second.json.gz"
    payload = {"sample_id": "sample", "values": [2, 1]}

    _atomic_gzip_json(first, payload)
    _atomic_gzip_json(second, payload)

    assert first.read_bytes() == second.read_bytes()
    assert _read_gzip_json(first) == payload