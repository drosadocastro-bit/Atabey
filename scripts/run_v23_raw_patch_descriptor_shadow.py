"""Run the V23 detector-native raw patch descriptor shadow audit.

This entry point only bootstraps the repository import paths and delegates to
the frozen V22 evidence-audit implementation. It does not mutate tracking
graphs or alter candidate formation.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_v22_official_positive_semantic_evidence_audit import main


if __name__ == "__main__":
    main()
