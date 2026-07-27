"""Add validation-based early stopping to the prepared E016 trainer."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    text = args.source.read_text(encoding="utf-8")

    signature_anchor = "    data_parallel: bool = True,\n) -> UNetNodeTransformer:\n"
    signature_replacement = (
        "    data_parallel: bool = True,\n"
        "    patience: int | None = None,\n"
        "    min_delta: float = 0.0,\n"
        ") -> UNetNodeTransformer:\n"
    )
    if "    patience: int | None = None," not in text:
        if signature_anchor not in text:
            raise RuntimeError("Could not find train signature anchor")
        text = text.replace(signature_anchor, signature_replacement, 1)

    best_anchor = "    best_score = 0.0\n    save_path = output_dir / \"edge_predictor_best.pth\"\n"
    best_replacement = (
        "    best_score = 0.0\n"
        "    stale_epochs = 0\n"
        "    save_path = output_dir / \"edge_predictor_best.pth\"\n"
    )
    if "    stale_epochs = 0" not in text:
        if best_anchor not in text:
            raise RuntimeError("Could not find best-score anchor")
        text = text.replace(best_anchor, best_replacement, 1)

    score_anchor = "        is_best = score >= best_score\n\n        if is_best:\n"
    score_replacement = (
        "        is_best = score >= best_score + min_delta\n\n"
        "        if is_best:\n"
        "            stale_epochs = 0\n"
        "        else:\n"
        "            stale_epochs += 1\n"
    )
    if "score >= best_score + min_delta" not in text:
        if score_anchor not in text:
            raise RuntimeError("Could not find score anchor")
        text = text.replace(score_anchor, score_replacement, 1)

    loop_tail = "            flush=True,\n        )\n\n    print(f\"\\nBest score"
    early_tail = (
        "            flush=True,\n"
        "        )\n"
        "        if patience is not None and stale_epochs >= patience:\n"
        "            print(\n"
        "                f\"Early stopping at epoch {epoch}: no validation improvement \"\n"
        "                f\"for {patience} epochs (min_delta={min_delta}).\",\n"
        "                flush=True,\n"
        "            )\n"
        "            break\n\n"
        "    print(f\"\\nBest score"
    )
    if "Early stopping at epoch" not in text:
        if loop_tail not in text:
            raise RuntimeError("Could not find training-loop tail")
        text = text.replace(loop_tail, early_tail, 1)

    cli_anchor = '    parser.add_argument("--epochs", type=int, default=50)\n'
    cli_replacement = (
        cli_anchor
        + '    parser.add_argument("--patience", type=int, default=None,\n'
        + '                        help="Stop after this many non-improving validation epochs.")\n'
        + '    parser.add_argument("--min-delta", type=float, default=0.0,\n'
        + '                        help="Minimum validation-score improvement to reset patience.")\n'
    )
    if 'parser.add_argument("--patience"' not in text:
        if cli_anchor not in text:
            raise RuntimeError("Could not find epochs CLI anchor")
        text = text.replace(cli_anchor, cli_replacement, 1)

    call_anchor = "            data_parallel=args.data_parallel,\n"
    call_replacement = (
        call_anchor
        + "            patience=args.patience,\n"
        + "            min_delta=args.min_delta,\n"
    )
    if "            patience=args.patience," not in text:
        if call_anchor not in text:
            raise RuntimeError("Could not find train call anchor")
        text = text.replace(call_anchor, call_replacement, 1)

    args.output.write_text(text, encoding="utf-8")
    print(f"Wrote early-stop trainer: {args.output}")


if __name__ == "__main__":
    main()
