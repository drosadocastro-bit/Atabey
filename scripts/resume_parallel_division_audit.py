from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
from pathlib import Path


RESULT_RE = re.compile(r"^--- Results for (?P<sample>\S+) ---$", re.MULTILINE)


def completed_samples(log_path: Path) -> set[str]:
    if not log_path.exists():
        return set()
    return set(RESULT_RE.findall(log_path.read_text(errors="replace")))


def all_train_samples(train_dir: Path) -> list[str]:
    return sorted(path.stem for path in train_dir.glob("*.zarr"))


def chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def run_chunk(
    project_root: Path,
    sample_ids: list[str],
    log_path: Path,
    workers: int,
    cfar_link_strategy: str,
    max_timepoints: int,
) -> int:
    cmd = [
        sys.executable,
        "-u",
        str(project_root / "scripts" / "run_parallel_division_audit.py"),
        "--workers",
        str(workers),
        "--sample-ids",
        *sample_ids,
        "--cfar-link-strategy",
        cfar_link_strategy,
        "--max-timepoints",
        str(max_timepoints),
    ]
    print(f"\n=== Resume chunk: {len(sample_ids)} samples, workers={workers} ===", flush=True)
    print("Samples:", " ".join(sample_ids), flush=True)
    with log_path.open("a", encoding="utf-8", errors="replace") as log_file:
        log_file.write(f"\n=== Resume chunk: {len(sample_ids)} samples, workers={workers} ===\n")
        log_file.write("Samples: " + " ".join(sample_ids) + "\n")
        proc = subprocess.Popen(
            cmd,
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="")
            log_file.write(line)
        return proc.wait()


def main() -> None:
    parser = argparse.ArgumentParser(description="Resume a partially completed parallel division audit log.")
    parser.add_argument("--log", type=Path, default=Path("v20_bipartite_firewall_199.log"))
    parser.add_argument("--train-dir", type=Path, default=Path("train"))
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--fallback-workers", type=int, default=1)
    parser.add_argument("--chunk-size", type=int, default=25)
    parser.add_argument("--cfar-link-strategy", default="bipartite")
    parser.add_argument("--max-timepoints", type=int, default=100)
    parser.add_argument("--max-passes", type=int, default=3)
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    log_path = args.log if args.log.is_absolute() else project_root / args.log
    train_dir = args.train_dir if args.train_dir.is_absolute() else project_root / args.train_dir

    all_samples = all_train_samples(train_dir)
    if not all_samples:
        raise SystemExit(f"No .zarr samples found in {train_dir}")

    for pass_idx in range(args.max_passes):
        done = completed_samples(log_path)
        missing = [sample for sample in all_samples if sample not in done]
        print(f"Pass {pass_idx + 1}: completed={len(done)} missing={len(missing)} total={len(all_samples)}", flush=True)
        if not missing:
            print("All samples have result blocks in the log.", flush=True)
            return

        workers = args.workers if pass_idx == 0 else args.fallback_workers
        chunk_size = args.chunk_size if workers > 1 else 1
        for chunk in chunks(missing, chunk_size):
            before = completed_samples(log_path)
            rc = run_chunk(
                project_root=project_root,
                sample_ids=chunk,
                log_path=log_path,
                workers=workers,
                cfar_link_strategy=args.cfar_link_strategy,
                max_timepoints=args.max_timepoints,
            )
            after = completed_samples(log_path)
            gained = len(after - before)
            print(f"Chunk exit={rc}; new completed samples={gained}", flush=True)
            if rc != 0 and workers == args.fallback_workers and gained == 0:
                remaining = [sample for sample in chunk if sample not in after]
                raise SystemExit(
                    "Fallback worker run failed without completing any new samples. "
                    f"Remaining chunk: {' '.join(remaining)}"
                )

    done = completed_samples(log_path)
    missing = [sample for sample in all_samples if sample not in done]
    raise SystemExit(f"Stopped after {args.max_passes} passes with {len(missing)} missing samples: {' '.join(missing)}")


if __name__ == "__main__":
    main()
