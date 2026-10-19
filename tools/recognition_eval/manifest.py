"""Bounded local dataset validation, provenance and cross-split leakage checks."""

import hashlib
import io
import json
import re
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from PIL import Image, ImageOps

SPLITS = {"reference", "calibration", "test", "unknown_calibration", "unknown_test", "profile"}
TOKEN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}$")
MAX_BYTES = 10 * 1024 * 1024
MAX_SAMPLES = 2000


@dataclass(frozen=True)
class Sample:
    id: str
    path: Path
    sha256: str
    model_id: str | None
    split: str
    capture_group: str
    source: str
    license: str
    captured_at: str | None


@dataclass(frozen=True)
class Dataset:
    id: str
    synthetic: bool
    samples: tuple[Sample, ...]
    manifest_sha256: str


class DatasetError(ValueError):
    """Do not include image bytes, private paths or EXIF in diagnostics."""


def image_rgb(path: Path) -> Image.Image:
    with path.open("rb") as stream:
        content = stream.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise DatasetError("Image exceeds 10 MiB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                if image.format not in {"JPEG", "PNG"}:
                    raise DatasetError("Only decoded JPEG/PNG images are supported")
                width, height = image.size
                if min(width, height) < 64 or max(width, height) > 4096:
                    raise DatasetError("Image dimensions must be 64..4096")
                if width * height > 16_000_000 or getattr(image, "n_frames", 1) != 1:
                    raise DatasetError("Image pixel/frame limit exceeded")
                image.verify()
            with Image.open(io.BytesIO(content)) as image:
                return ImageOps.exif_transpose(image).convert("RGB")
    except (OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise DatasetError("Invalid or unsafe image") from None


def fingerprints(image: Image.Image) -> tuple[str, int]:
    decoded = hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()
    pixels = list(image.convert("L").resize((9, 8), Image.Resampling.LANCZOS).tobytes())
    dhash = 0
    for y in range(8):
        for x in range(8):
            dhash = (dhash << 1) | (pixels[y * 9 + x] > pixels[y * 9 + x + 1])
    return decoded, dhash


def _keys(value: Any, expected: set[str]) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise DatasetError("Unexpected or missing manifest fields")


def _text(value: Any, *, token: bool = False) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value) <= 500
        and (not token or TOKEN.fullmatch(value) is not None)
    )


def load_dataset(manifest: Path, root: Path, *, require_splits: bool = True) -> Dataset:
    with manifest.open("rb") as stream:
        raw = stream.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise DatasetError("Manifest exceeds 2 MiB")
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError):
        raise DatasetError("Manifest must be UTF-8 JSON") from None
    _keys(data, {"schema_version", "dataset_id", "synthetic", "samples"})
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise DatasetError("Unsupported manifest version")
    if not _text(data["dataset_id"], token=True) or type(data["synthetic"]) is not bool:
        raise DatasetError("Invalid dataset identity")
    rows = data["samples"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_SAMPLES:
        raise DatasetError("Dataset must have 1..2000 samples")
    root = root.resolve(strict=True)
    samples: list[Sample] = []
    ids: set[str] = set()
    hashes: set[str] = set()
    paths: set[Path] = set()
    groups: dict[str, str] = {}
    visuals: list[tuple[str, str, int]] = []
    for row in rows:
        _keys(
            row,
            {
                "id",
                "path",
                "sha256",
                "model_id",
                "split",
                "capture_group",
                "source",
                "license",
                "captured_at",
            },
        )
        for name in ("id", "capture_group", "source", "license"):
            if not _text(row[name], token=name in {"id", "capture_group"}):
                raise DatasetError("Invalid sample provenance")
        if row["id"] in ids or not isinstance(row["split"], str) or row["split"] not in SPLITS:
            raise DatasetError("Duplicate sample id or invalid split")
        if row["model_id"] is not None and not _text(row["model_id"], token=True):
            raise DatasetError("Invalid model identity")
        if (row["model_id"] is None) != row["split"].startswith("unknown_"):
            raise DatasetError("Unknown split requires null model_id; known split requires a model")
        if row["captured_at"] is None and row["split"] == "profile":
            pass  # Real capture time unknown; never substitute file mtime as evidence.
        else:
            if not isinstance(row["captured_at"], str):
                raise DatasetError("captured_at requires an explicit timezone")
            try:
                stamp = datetime.fromisoformat(row["captured_at"].replace("Z", "+00:00"))
                if stamp.utcoffset() is None:
                    raise ValueError()
            except ValueError:
                raise DatasetError("captured_at requires ISO 8601 with timezone") from None
        relative = row["path"]
        if not isinstance(relative, str) or not relative or "\\" in relative:
            raise DatasetError("Image path must be relative POSIX")
        posix = PurePosixPath(relative)
        if posix.is_absolute() or ".." in posix.parts or ":" in relative:
            raise DatasetError("Image path escapes dataset")
        try:
            path = (root / relative).resolve(strict=True)
        except (OSError, RuntimeError):
            raise DatasetError("Missing dataset image") from None
        if not path.is_relative_to(root) or not path.is_file() or path in paths:
            raise DatasetError("Unsafe or repeated image path")
        if not isinstance(row["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]):
            raise DatasetError("Invalid SHA-256")
        if path.stat().st_size > MAX_BYTES:
            raise DatasetError("Image exceeds 10 MiB")
        with path.open("rb") as stream:
            content = stream.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise DatasetError("Image exceeds 10 MiB")
        digest = hashlib.sha256(content).hexdigest()
        if digest != row["sha256"] or digest in hashes:
            raise DatasetError("Image hash mismatch or duplicate bytes")
        prior = groups.setdefault(row["capture_group"], row["split"])
        if prior != row["split"]:
            raise DatasetError("Capture group leaks across splits")
        decoded, dhash = fingerprints(image_rgb(path))
        for split, other_decoded, other_dhash in visuals:
            if row["split"] != split and (
                decoded == other_decoded or (dhash ^ other_dhash).bit_count() <= 4
            ):
                raise DatasetError(
                    "Decoded/perceptual near-duplicate across splits; review grouping"
                )
        visuals.append((row["split"], decoded, dhash))
        ids.add(row["id"])
        hashes.add(digest)
        paths.add(path)
        samples.append(Sample(**{**row, "path": path}))
    if require_splits:
        references = {s.model_id for s in samples if s.split == "reference"}
        if not references or any(
            s.model_id not in references for s in samples if s.split in {"calibration", "test"}
        ):
            raise DatasetError("Every known model requires reference images")
        if {s.split for s in samples} != SPLITS - {"profile"}:
            raise DatasetError("All five evaluation splits are required; profile is latency-only")
        for model in references:
            if any(
                not any(s.model_id == model and s.split == split for s in samples)
                for split in ("calibration", "test")
            ):
                raise DatasetError(
                    "Each reference model needs calibration and held-out test images"
                )
    elif any(s.split != "profile" for s in samples):
        raise DatasetError("Latency-only profiling requires profile split exclusively")
    return Dataset(
        data["dataset_id"], data["synthetic"], tuple(samples), hashlib.sha256(raw).hexdigest()
    )
