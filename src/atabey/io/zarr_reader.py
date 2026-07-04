from __future__ import annotations

from pathlib import Path
from typing import Any


def open_zarr_array(path: str | Path) -> Any:
    """Open a Zarr array or group without loading the full video."""

    try:
        import zarr
    except ImportError as exc:  # pragma: no cover - exercised when zarr is absent.
        raise RuntimeError("zarr is required to read competition samples") from exc

    return zarr.open(str(path), mode="r")


def open_competition_array(sample_path: str | Path) -> Any:
    """Open the image array inside a competition `.zarr` sample directory."""

    root = Path(sample_path)
    array_path = root / "0"
    if not array_path.exists():
        raise FileNotFoundError(f"Expected competition array at {array_path}")
    return open_zarr_array(array_path)


def read_timepoint(array: Any, t: int) -> Any:
    """Read a single timepoint from an array expected to be indexed by time first."""

    return array[t]


def sample_id_from_zarr_path(path: str | Path) -> str:
    """Return the Kaggle dataset name without the `.zarr` suffix."""

    return Path(path).name.removesuffix(".zarr")
