"""Inspect the Kaggle support predictor before adding decoder hooks.

This is source-only and read-only. It does not load data, weights, or mutate a
model. The output identifies likely model classes and forward paths so a later
Kaggle cell can attach a correctly scoped feature hook.
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--support-repo", type=Path, required=True)
    args = parser.parse_args()
    source = args.support_repo / "scripts" / "predict_unet_transformer.py"
    if not source.exists():
        raise FileNotFoundError(source)
    tree = ast.parse(source.read_text(encoding="utf-8"))
    classes = []
    functions = []
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = [ast.unparse(base) for base in node.bases]
            classes.append({"name": node.name, "bases": bases, "line": node.lineno})
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append({"name": node.name, "line": node.lineno})
        elif isinstance(node, ast.Call):
            try:
                target = ast.unparse(node.func)
            except Exception:
                target = type(node.func).__name__
            if any(token in target.lower() for token in ("model", "unet", "transform", "load")):
                calls.append({"target": target, "line": node.lineno})
    print("predictor:", source)
    print("classes:")
    for item in classes:
        print(" ", item)
    print("functions:")
    for item in functions:
        print(" ", item)
    print("model-related calls:")
    for item in sorted(calls, key=lambda value: value["line"]):
        print(" ", item)


if __name__ == "__main__":
    main()
