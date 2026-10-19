"""Optional real Paddle tests, network disabled; synthetic labels prove plumbing, not accuracy."""

import importlib.util
import io
import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.ocr_adapter import PaddleCPUEngine, model_fingerprint
from app.ocr_schemas import ManualCorrection
from app.ocr_service import OCRUnavailable, read_label

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("paddleocr") is None, reason="Optional CPU OCR image required"
)
ROOT = Path("/opt/ocr-models")


def label(blurred=False):
    image = Image.new("RGB", (900, 220), "white")
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 38)
    draw = ImageDraw.Draw(image)
    draw.text((25, 35), "SN: ABC789XYZ", font=font, fill="black")
    draw.text((25, 110), "MAC: 00:11:22:33:44:55", font=font, fill="black")
    if blurred:
        image = image.filter(ImageFilter.GaussianBlur(18))
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def test_real_paddle_cpu_clean_label_and_versioned_evidence():
    start = time.monotonic()
    result = read_label(label(), "image/png", PaddleCPUEngine(ROOT, timeout_seconds=60))
    elapsed = time.monotonic() - start
    assert result.engine_version.startswith("paddleocr-3.2.0")
    assert result.model_fingerprint == model_fingerprint(ROOT)
    assert result.raw_text and result.lines
    assert any(
        c.kind == "SERIAL_NUMBER" and c.normalized_value == "ABC789XYZ"
        for c in result.ocr_candidates
    )
    assert any(
        c.kind == "MAC" and c.normalized_value == "00:11:22:33:44:55" for c in result.ocr_candidates
    )
    assert result.status == "REVIEW_REQUIRED"
    assert result.requires_review and result.corrected_text is None
    rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    print(f"CPU synthetic label: elapsed_seconds={elapsed:.3f}, child_maxrss_kib={rss}")


def test_real_paddle_blurred_label_preserves_raw_and_manual_fallback():
    result = read_label(
        label(blurred=True),
        "image/png",
        PaddleCPUEngine(ROOT, timeout_seconds=60),
        ManualCorrection(corrected_text="SN: ABC789XYZ\nMAC: 00:11:22:33:44:55"),
    )
    assert result.engine_version is not None
    assert result.raw_text == "\n".join(line.text for line in result.lines)
    assert [c.normalized_value for c in result.manual_candidates] == [
        "ABC789XYZ",
        "00:11:22:33:44:55",
    ]
    assert all(c.requires_review for c in result.ocr_candidates + result.manual_candidates)
    assert result.reason == "MANUAL_CORRECTION_REQUIRES_REVIEW"


def test_real_models_missing_corrupt_and_symlink_rejected_without_download(tmp_path):
    with pytest.raises(OCRUnavailable):
        PaddleCPUEngine(tmp_path).recognize(Image.new("RGB", (50, 50)))
    manifest = json.loads(Path("app/ocr_weights.json").read_text())
    for name, entries in manifest.items():
        directory = tmp_path / name
        directory.mkdir()
        for filename in entries:
            (directory / filename).write_bytes(b"corrupt")
    with pytest.raises(OCRUnavailable):
        model_fingerprint(tmp_path)
    file = tmp_path / next(iter(manifest)) / "inference.json"
    file.unlink()
    file.symlink_to(ROOT / next(iter(manifest)) / "inference.json")
    with pytest.raises(OCRUnavailable):
        model_fingerprint(tmp_path)


def test_cli_actual_cpu_and_manual_errors_are_private(tmp_path):
    correction = tmp_path / "label.txt"
    correction.write_text("SN: ABC789XYZ")
    clean_env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("POSTGRES_", "JWT_", "DATABASE_", "TEST_DATABASE_"))
    }
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.ocr_cli",
            "--engine",
            "manual",
            "--correction-file",
            str(correction),
        ],
        capture_output=True,
        env=clean_env,
        text=True,
        check=True,
    )
    result = json.loads(completed.stdout)
    assert (
        result["raw_text"] == ""
        and result["manual_candidates"][0]["normalized_value"] == "ABC789XYZ"
    )
    bad = tmp_path / "bad.png"
    bad.write_text("private-label-secret")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.ocr_cli",
            "--engine",
            "paddle",
            "--image",
            str(bad),
            "--mime-type",
            "image/png",
        ],
        capture_output=True,
        env=clean_env,
        text=True,
    )
    assert completed.returncode == 2
    assert "private-label-secret" not in completed.stderr and completed.stdout == ""
