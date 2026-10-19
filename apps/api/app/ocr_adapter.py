"""Paddle CPU subprocess boundary: local checksummed weights, bounded output, hard timeout."""

import hashlib
import io
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image
from pydantic import ValidationError

from app.ocr_schemas import OCRReading
from app.ocr_service import OCRTimeout, OCRUnavailable

MODEL_NAMES = ("PP-OCRv4_mobile_det", "en_PP-OCRv4_mobile_rec")
ENGINE_VERSION = "paddleocr-3.2.0:paddle-3.2.0:paddlex-3.2.1:cpu:label-v1"


def model_fingerprint(root: Path) -> str:
    """Trusted shipped manifest, all three required inference files per model, no symlinks."""
    manifest_path = Path(__file__).with_name("ocr_weights.json")
    try:
        manifest = json.loads(manifest_path.read_text())
        if set(manifest) != set(MODEL_NAMES):
            raise ValueError()
        for name, entries in manifest.items():
            directory = root / name
            if root.is_symlink() or directory.is_symlink() or not directory.is_dir():
                raise ValueError()
            if set(entries) != {"inference.json", "inference.pdiparams", "inference.yml"}:
                raise ValueError()
            if {p.name for p in directory.iterdir()} != set(entries):
                raise ValueError()
            for filename, digest in entries.items():
                path = directory / filename
                if (
                    path.is_symlink()
                    or not path.is_file()
                    or path.stat().st_size > 32 * 1024 * 1024
                ):
                    raise ValueError()
                if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                    raise ValueError()
        return hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    except (OSError, ValueError, TypeError):
        raise OCRUnavailable("Pinned OCR models unavailable or checksum mismatch") from None


class PaddleCPUEngine:
    def __init__(self, models_root: Path, *, timeout_seconds: float = 30) -> None:
        if (
            type(timeout_seconds) not in (int, float)
            or not math.isfinite(timeout_seconds)
            or not 1 <= timeout_seconds <= 120
        ):
            raise ValueError("OCR timeout must be 1-120 seconds")
        self.models_root = models_root.absolute()
        self.timeout_seconds = timeout_seconds

    def recognize(self, image: Image.Image) -> OCRReading:
        fingerprint = model_fingerprint(self.models_root)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        # Child stdout/stderr never expose raw labels. Only bounded validated JSON is returned.
        with tempfile.TemporaryDirectory(prefix="av-ocr-") as directory:
            output = Path(directory) / "result.json"
            try:
                completed = subprocess.run(
                    [sys.executable, "-m", "app.ocr_worker", str(self.models_root), str(output)],
                    input=buffer.getvalue(),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=self.timeout_seconds,
                    check=False,
                )
                if (
                    completed.returncode != 0
                    or not output.is_file()
                    or output.stat().st_size > 131072
                ):
                    raise OCRUnavailable("OCR worker unavailable or invalid output")
                reading = OCRReading.model_validate_json(output.read_bytes())
                if (
                    reading.model_fingerprint != fingerprint
                    or reading.engine_version != ENGINE_VERSION
                ):
                    raise OCRUnavailable("OCR worker version mismatch")
                return reading
            except subprocess.TimeoutExpired:
                # subprocess.run kills and waits for the child; no runaway inference thread.
                raise OCRTimeout("OCR deadline exceeded") from None
            except (OSError, ValidationError):
                raise OCRUnavailable("OCR worker output unavailable") from None
