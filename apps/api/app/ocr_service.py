"""Read-only OCR orchestration; no DB writes, identity matching or automatic fallback claims."""

import hashlib
from datetime import UTC, datetime
from typing import Protocol

from PIL import Image
from pydantic import ValidationError

from app.ocr_parser import parse_lines
from app.ocr_schemas import ManualCorrection, OCRLine, OCRReading, OCRResult
from app.recognition_encoder import decode_image


class OCRUnavailable(RuntimeError):
    pass


class OCRTimeout(OCRUnavailable):
    pass


class OCREngine(Protocol):
    def recognize(self, image: Image.Image) -> OCRReading: ...


def read_label(
    data: bytes | None,
    mime_type: str | None,
    engine: OCREngine | None,
    correction: ManualCorrection | None = None,
) -> OCRResult:
    reading = None
    reason = "ENGINE_NOT_CONFIGURED"
    digest = None
    if data is not None:
        # Always validate the supplied image, even when the OCR engine is unavailable/manual.
        with decode_image(data, mime_type or "", max_bytes=8 * 1024 * 1024) as image:
            digest = hashlib.sha256(data).hexdigest()
            if engine is not None:
                try:
                    reading = OCRReading.model_validate(engine.recognize(image))
                    if len("\n".join(line.text for line in reading.lines)) > 16384:
                        raise OCRUnavailable("OCR output exceeds evidence limit")
                except OCRTimeout:
                    reason = "OCR_TIMEOUT"
                except (OCRUnavailable, ValidationError):
                    reading = None
                    reason = "OCR_UNAVAILABLE"
    elif correction is None:
        raise ValueError("Provide an image or manual correction")
    elif engine is not None:
        raise ValueError("OCR requires an image")
    lines = reading.lines if reading is not None else ()
    raw_text = "\n".join(line.text for line in lines)
    candidates = parse_lines(lines)
    warnings = []
    if reading is not None:
        reason = "OCR_REQUIRES_REVIEW" if candidates else "NO_READABLE_IDENTIFIERS"
        if any(line.score < 0.85 for line in lines):
            warnings.append("LOW_OCR_SCORE")
    if not candidates:
        warnings.append("MANUAL_ENTRY_NEEDED")
    manual_candidates = ()
    if correction is not None:
        manual_lines = tuple(
            OCRLine(text=line, score=1.0) for line in correction.corrected_text.split("\n")
        )
        manual_candidates = parse_lines(manual_lines, manual=True)
        reason = "MANUAL_CORRECTION_REQUIRES_REVIEW"
        if manual_candidates:
            warnings = [warning for warning in warnings if warning != "MANUAL_ENTRY_NEEDED"]
    return OCRResult(
        status="REVIEW_REQUIRED" if candidates or manual_candidates else "MANUAL_REQUIRED",
        reason=reason,
        source_image_sha256=digest,
        observed_at=datetime.now(UTC),
        engine_version=reading.engine_version if reading else None,
        model_fingerprint=reading.model_fingerprint if reading else None,
        raw_text=raw_text,
        lines=lines,
        ocr_candidates=candidates,
        corrected_text=correction.corrected_text if correction is not None else None,
        manual_candidates=manual_candidates,
        warnings=tuple(warnings),
    )
