"""Transient OCR evidence: immutable raw reading and separate manual correction."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Text = Annotated[str, StringConstraints(max_length=16384)]


class Evidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class OCRLine(Evidence):
    text: Annotated[str, StringConstraints(max_length=512)]
    score: Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]

    @field_validator("text")
    @classmethod
    def safe_line(cls, value: str) -> str:
        if any(not c.isprintable() for c in value):
            raise ValueError("OCR lines must be printable")
        return value


class OCRReading(Evidence):
    engine_version: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    model_fingerprint: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    lines: tuple[OCRLine, ...] = Field(max_length=128)


class ManualCorrection(Evidence):
    corrected_text: Text

    @field_validator("corrected_text")
    @classmethod
    def safe_text(cls, value: str) -> str:
        if any(not c.isprintable() and c != "\n" for c in value):
            raise ValueError("Text may only contain printable characters and newlines")
        if any(len(line) > 512 for line in value.split("\n")) or len(value.split("\n")) > 128:
            raise ValueError("Too many or oversized label lines")
        return value


class IdentifierCandidate(Evidence):
    kind: Literal["SERIAL_NUMBER", "MAC", "MAC_LAN", "MAC_WLAN", "BSSID", "MODEL"]
    raw_value: Annotated[str, StringConstraints(min_length=1, max_length=255)]
    normalized_value: Annotated[str, StringConstraints(min_length=1, max_length=255)]
    source: Literal["OCR", "MANUAL"]
    line_indices: tuple[int, ...]
    issues: tuple[str, ...] = ()
    requires_review: Literal[True] = True


class OCRResult(Evidence):
    status: Literal["REVIEW_REQUIRED", "MANUAL_REQUIRED"]
    reason: str
    source_image_sha256: str | None
    observed_at: datetime
    engine_version: str | None = None
    model_fingerprint: str | None = None
    raw_text: Text = ""
    lines: tuple[OCRLine, ...] = ()
    ocr_candidates: tuple[IdentifierCandidate, ...] = ()
    corrected_text: Text | None = None
    manual_candidates: tuple[IdentifierCandidate, ...] = ()
    warnings: tuple[str, ...] = ()
    parser_version: Literal["label-parser-v1"] = "label-parser-v1"
    requires_review: Literal[True] = True
