"""Label evidence remains transient and never turns OCR guesses into verified identities."""

import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from PIL import Image, ImageDraw, ImageFilter
from pydantic import ValidationError

from app.ocr_adapter import ENGINE_VERSION, PaddleCPUEngine
from app.ocr_parser import parse_lines
from app.ocr_schemas import ManualCorrection, OCRLine, OCRReading
from app.ocr_service import OCRTimeout, OCRUnavailable, read_label


def image_bytes(blur=False):
    image = Image.new("RGB", (600, 140), "white")
    ImageDraw.Draw(image).text((12, 20), "SN: SAMPLE-123\nMAC: 00:11:22:33:44:55", fill="black")
    if blur:
        image = image.filter(ImageFilter.GaussianBlur(12))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def lines(*texts, score=0.99):
    return tuple(OCRLine(text=text, score=score) for text in texts)


class Engine:
    def __init__(self, *texts, score=0.99):
        self.reading = OCRReading(
            engine_version="test-only", model_fingerprint="a" * 64, lines=lines(*texts, score=score)
        )

    def recognize(self, image):
        assert image.mode == "RGB"
        return self.reading


@pytest.mark.parametrize("label", ["SN", "S/N", "S / N", "Serial", "Serial Number", "Serial No."])
def test_serial_labels_preserve_case_and_punctuation(label):
    result = parse_lines(lines(f"{label}: Ab-01.x/9"))
    assert len(result) == 1
    assert result[0].kind == "SERIAL_NUMBER"
    assert result[0].normalized_value == "Ab-01.x/9"
    assert result[0].requires_review
    assert "CHECK_AMBIGUOUS_CHARACTERS" in result[0].issues


@pytest.mark.parametrize(
    "value", ["aabbccddeeff", "aa:bb:cc:dd:ee:ff", "AA-BB-CC-DD-EE-FF", "aabb.ccdd.eeff"]
)
def test_mac_formats_normalized_consistently_with_existing_assets(value):
    (candidate,) = parse_lines(lines(f"MAC: {value}"))
    assert candidate.normalized_value == "AA:BB:CC:DD:EE:FF"
    assert candidate.kind == "MAC"
    assert candidate.issues == ("MAC_TYPE_UNSPECIFIED",)


@pytest.mark.parametrize(
    "label,kind",
    [
        ("LAN MAC", "MAC_LAN"),
        ("WLAN MAC Address", "MAC_WLAN"),
        ("Wi-Fi MAC", "MAC_WLAN"),
        ("BSSID", "BSSID"),
    ],
)
def test_mac_type_never_inferred_from_value(label, kind):
    (candidate,) = parse_lines(lines(f"{label}: 00:11:22:33:44:55"))
    assert candidate.kind == kind
    assert "MAC_TYPE_UNSPECIFIED" not in candidate.issues


@pytest.mark.parametrize(
    "text",
    [
        "SN: UNKNOWN",
        "SN: N/A",
        "SN: -",
        "SN: ABC???",
        "SN: AB CD",
        "SN: AB*CD",
        "SN: АB123",
        "MAC: OO:11:22:33:44:55",
        "MAC: 00:11:22:33:44",
        "MAC: 00:11:22:33:44:55:66",
        "serializable: ABC123",
        "SNAKE: ABC123",
        "MACaroni: abc",
        "AB123456789",
        "00:11:22:33:44:55",
    ],
)
def test_damage_unlabelled_and_fuzzy_text_does_not_manufacture_identifier(text):
    assert parse_lines(lines(text)) == ()


def test_multiple_fields_split_label_and_conflict_are_preserved():
    candidates = parse_lines(
        lines("SN: Ab-9 MAC: 00:11:22:33:44:55", "SN:", "Cd-8", "Model: WP810")
    )
    assert [c.kind for c in candidates] == ["SERIAL_NUMBER", "MAC", "SERIAL_NUMBER", "MODEL"]
    assert candidates[2].line_indices == (1, 2)
    assert candidates[0].normalized_value != candidates[2].normalized_value
    assert parse_lines(lines("SN:", "MAC: 00:11:22:33:44:55"))[0].kind == "MAC"


@pytest.mark.parametrize("value", ["FF:FF:FF:FF:FF:FF", "00:00:00:00:00:00", "01:11:22:33:44:55"])
def test_special_mac_not_treated_as_device_claim(value):
    assert "NON_DEVICE_MAC_ADDRESS" in parse_lines(lines(f"MAC: {value}"))[0].issues


def test_blurred_low_score_raw_evidence_preserved_with_separate_manual_correction():
    data = image_bytes(blur=True)
    raw = "SN: AO1?\nMAC: OO:11:22:33:44:55"
    result = read_label(
        data,
        "image/png",
        Engine(*raw.split("\n"), score=0.2),
        ManualCorrection(corrected_text="SN: A019\nLAN MAC: 00:11:22:33:44:55"),
    )
    assert result.raw_text == raw
    assert result.ocr_candidates == ()
    assert result.source_image_sha256 == hashlib.sha256(data).hexdigest()
    assert result.corrected_text == "SN: A019\nLAN MAC: 00:11:22:33:44:55"
    assert len(result.manual_candidates) == 2
    assert all(c.source == "MANUAL" and c.requires_review for c in result.manual_candidates)
    assert "LOW_OCR_SCORE" in result.warnings
    assert "asset_id" not in result.model_dump_json()
    assert result.status == "REVIEW_REQUIRED"


def test_low_score_valid_syntax_is_evidence_requiring_review():
    result = read_label(image_bytes(), "image/png", Engine("SN: ABC789", score=0.1))
    assert result.ocr_candidates[0].issues == ("LOW_OCR_SCORE",)
    assert result.requires_review


@pytest.mark.parametrize(
    "exception,reason",
    [(OCRUnavailable("secret"), "OCR_UNAVAILABLE"), (OCRTimeout("secret"), "OCR_TIMEOUT")],
)
def test_engine_failure_requires_manual_without_leaking_error(exception, reason):
    class Failure:
        def recognize(self, image):
            raise exception

    result = read_label(image_bytes(), "image/png", Failure())
    assert result.status == "MANUAL_REQUIRED" and result.reason == reason
    assert result.raw_text == ""
    assert "secret" not in result.model_dump_json()


def test_empty_engine_and_empty_label_require_manual():
    assert read_label(image_bytes(), "image/png", None).reason == "ENGINE_NOT_CONFIGURED"
    assert read_label(image_bytes(), "image/png", Engine()).reason == "NO_READABLE_IDENTIFIERS"
    assert (
        read_label(image_bytes(), "image/png", Engine("Manufacturer Example")).status
        == "MANUAL_REQUIRED"
    )
    assert (
        read_label(None, None, None, ManualCorrection(corrected_text="SN: abc789"))
        .manual_candidates[0]
        .normalized_value
        == "abc789"
    )
    assert (
        read_label(None, None, None, ManualCorrection(corrected_text="")).status
        == "MANUAL_REQUIRED"
    )
    with pytest.raises(ValueError):
        read_label(None, None, None)


@pytest.mark.parametrize(
    "text", ["SN: AB\x00CD", "SN: AB\tCD", "SN: AB\rCD", "SN: \ud800", "x" * 513, "x\n" * 129]
)
def test_manual_text_limits(text):
    with pytest.raises(ValidationError):
        ManualCorrection(corrected_text=text)


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -0.1, 1.1, True])
def test_invalid_engine_scores(score):
    with pytest.raises(ValidationError):
        OCRLine(text="SN: AB", score=score)


def test_ocr_raw_total_bound():
    engine = Engine(*(["x" * 512] * 128))
    result = read_label(image_bytes(), "image/png", engine)
    assert result.status == "MANUAL_REQUIRED" and result.raw_text == ""


@pytest.mark.parametrize("data,mime,status", [(b"bad", "image/png", 415), (b"", "image/png", 413)])
def test_invalid_image_rejected_even_when_manual(data, mime, status):
    with pytest.raises(HTTPException) as error:
        read_label(data, mime, None, ManualCorrection(corrected_text="SN: X"))
    assert error.value.status_code == status


def test_image_mismatch_and_dimensions():
    with pytest.raises(HTTPException) as error:
        read_label(image_bytes(), "image/jpeg", None)
    assert error.value.status_code == 415
    image = Image.new("RGB", (4097, 1))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    with pytest.raises(HTTPException) as error:
        read_label(buffer.getvalue(), "image/png", None)
    assert error.value.status_code == 422


@pytest.mark.parametrize("value", [0, -1, 121, float("nan"), True, "30"])
def test_timeout_configuration_bounded(tmp_path, value):
    with pytest.raises(ValueError):
        PaddleCPUEngine(tmp_path, timeout_seconds=value)


def test_missing_models_fail_closed_without_spawning(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("must not spawn/download"))
    with pytest.raises(OCRUnavailable):
        PaddleCPUEngine(tmp_path).recognize(Image.new("RGB", (10, 10)))


def test_child_timeout_really_terminates_process(tmp_path, monkeypatch):
    from app import ocr_adapter

    monkeypatch.setattr(ocr_adapter, "model_fingerprint", lambda root: "a" * 64)
    original = subprocess.run
    pidfile = tmp_path / "pid"

    def run(args, **kwargs):
        script = (
            "import os,time;open("
            + repr(str(pidfile))
            + ",'w').write(str(os.getpid()));time.sleep(20)"
        )
        return original([sys.executable, "-c", script], **kwargs)

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(OCRTimeout):
        PaddleCPUEngine(tmp_path, timeout_seconds=1).recognize(Image.new("RGB", (10, 10)))
    with pytest.raises(ProcessLookupError):
        os.kill(int(pidfile.read_text()), 0)


@pytest.mark.parametrize(
    "output",
    [
        "invalid",
        "{}",
        json.dumps({"engine_version": "wrong", "model_fingerprint": "a" * 64, "lines": []}),
        "x" * 131073,
    ],
)
def test_corrupt_or_mismatched_child_result_rejected(tmp_path, monkeypatch, output):
    from app import ocr_adapter

    monkeypatch.setattr(ocr_adapter, "model_fingerprint", lambda root: "a" * 64)

    def run(args, **kwargs):
        Path(args[-1]).write_text(output)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(OCRUnavailable):
        PaddleCPUEngine(tmp_path).recognize(Image.new("RGB", (10, 10)))


def test_valid_worker_contract(tmp_path, monkeypatch):
    from app import ocr_adapter

    monkeypatch.setattr(ocr_adapter, "model_fingerprint", lambda root: "a" * 64)
    reading = OCRReading(
        engine_version=ENGINE_VERSION, model_fingerprint="a" * 64, lines=lines("SN: ABC789")
    )

    def run(args, **kwargs):
        Path(args[-1]).write_text(reading.model_dump_json())
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", run)
    assert PaddleCPUEngine(tmp_path).recognize(Image.new("RGB", (10, 10))) == reading


def test_manual_and_decode_do_not_need_database_or_jwt_settings(monkeypatch):
    from app import recognition_encoder

    monkeypatch.setattr(
        recognition_encoder, "get_settings", lambda: pytest.fail("OCR must not read DB/JWT config")
    )
    assert read_label(image_bytes(), "image/png", None).status == "MANUAL_REQUIRED"


@pytest.mark.parametrize("limit", [0, 1023, 8388609, True])
def test_shared_decoder_explicit_byte_limit_cannot_bypass_bounds(limit):
    from app.recognition_encoder import decode_image

    with pytest.raises(ValueError):
        decode_image(image_bytes(), "image/png", max_bytes=limit)


def test_invalid_engine_contract_uses_manual_fallback():
    class Invalid:
        def recognize(self, image):
            return {"lines": [{"text": "private", "score": float("nan")}]}

    result = read_label(image_bytes(), "image/png", Invalid())
    assert result.status == "MANUAL_REQUIRED" and result.reason == "OCR_UNAVAILABLE"
    assert "private" not in result.model_dump_json()


def test_cli_standalone_has_no_database_or_jwt_import_side_effect(tmp_path):
    import os
    import subprocess
    import sys

    correction = tmp_path / "label.txt"
    correction.write_text("SN: Standalone789")
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
        text=True,
        env=clean_env,
    )
    assert completed.returncode == 0, completed.stderr
    assert (
        json.loads(completed.stdout)["manual_candidates"][0]["normalized_value"] == "Standalone789"
    )
