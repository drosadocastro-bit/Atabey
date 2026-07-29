"""Run the preregistered V23 detector-native positive-unlabeled ranker."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_v22_positive_unlabeled_semantic_ranker import main


if __name__ == "__main__":
    main()
