"""Patch the public E016 trainer for explicit deterministic clean training."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    text = args.source.read_text(encoding="utf-8")

    seed_import = "import random\nimport os\n"
    if seed_import not in text:
        anchor = "import json\n"
        if anchor not in text:
            raise RuntimeError("Could not find stable import anchor")
        text = text.replace(anchor, anchor + seed_import, 1)

    train_anchor = "    if unet_layers is None:\n        unet_layers = [32, 64, 128]\n"
    seed_block = (
        train_anchor
        + "    if seed is not None:\n"
        + "        random.seed(seed)\n"
        + "        np.random.seed(seed)\n"
        + "        torch.manual_seed(seed)\n"
        + "        if torch.cuda.is_available():\n"
        + "            torch.cuda.manual_seed_all(seed)\n"
    )
    if "BIOHUB_WEIGHTS_DIR" not in text:
        weights_anchor = "from dataspec import WEIGHTS_PATH\n"
        if weights_anchor not in text:
            raise RuntimeError("Could not find weights-path anchor")
        text = text.replace(
            weights_anchor,
            weights_anchor
            + "WEIGHTS_PATH = Path(os.environ.get(\"BIOHUB_WEIGHTS_DIR\", \"/kaggle/working/weights\"))\n",
            1,
        )
    if "random.seed(seed)" not in text:
        if train_anchor not in text:
            raise RuntimeError("Could not find train seed anchor")
        text = text.replace(train_anchor, seed_block, 1)

    cli_anchor = '    parser.add_argument("--single-gpu", dest="data_parallel", action="store_false",\n'
    cli_block = (
        '    parser.add_argument("--seed", type=int, default=314159,\n'
        '                        help="Explicit reproducibility seed.")\n'
        + cli_anchor
    )
    if 'parser.add_argument("--seed"' not in text:
        if cli_anchor not in text:
            raise RuntimeError("Could not find CLI anchor")
        text = text.replace(cli_anchor, cli_block, 1)

    call_anchor = "            data_parallel=args.data_parallel,\n"
    call_block = call_anchor + "            seed=args.seed,\n"
    if "            seed=args.seed,\n" not in text:
        if text.count(call_anchor) != 1:
            raise RuntimeError("Could not find unique train call anchor")
        text = text.replace(call_anchor, call_block, 1)

    args.output.write_text(text, encoding="utf-8")
    print(f"Wrote deterministic trainer: {args.output}")


if __name__ == "__main__":
    main()
