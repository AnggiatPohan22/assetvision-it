"""Strict index/version contracts; model candidates never identify an asset unit."""

import hashlib
import json
import math
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
VectorSize = Annotated[StrictInt, Field(ge=1, le=4096)]
GenerationVersion = Annotated[StrictInt, Field(ge=1, le=2147483646)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class EncoderSpec(Contract):
    name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=150)
    weights_sha256: Digest
    preprocess_version: Digest
    dimensions: VectorSize

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class CalibrationPolicy(Contract):
    encoder_fingerprint: Digest
    reference_fingerprint: Digest
    dataset_sha256: Digest
    evaluation_sha256: Digest
    threshold: float = Field(strict=True, ge=-1, le=1.000000000000001, allow_inf_nan=False)
    provenance: Literal["ADMIN_REVIEWED_REAL_EVALUATION"]


class RebuildRequest(Contract):
    expected_version: GenerationVersion
    reason: str = Field(min_length=1, max_length=2000)
    calibration_reference_fingerprint: Digest | None = None

    @field_validator("reason")
    @classmethod
    def canonical_reason(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Readable rebuild reason required")
        return value


class SearchRequest(Contract):
    top_k: Annotated[StrictInt, Field(ge=1, le=10)] = 3


class ModelCandidate(Contract):
    device_model_id: uuid.UUID
    rank: int
    similarity: float
    reference_image_snapshot_id: uuid.UUID


class SearchResult(Contract):
    status: Literal["KNOWN_MODEL_CANDIDATE", "UNKNOWN_MODEL", "UNCERTAIN"]
    reason: str
    index_id: uuid.UUID | None
    generation_version: int
    encoder: EncoderSpec | None
    calibrated: bool = False
    threshold: float | None = None
    candidates: tuple[ModelCandidate, ...] = ()
    score_label: Literal["cosine similarity; not confidence or asset identity"] = (
        "cosine similarity; not confidence or asset identity"
    )


def reviewed_calibration(
    report: dict, spec: EncoderSpec, reference_fingerprint: str
) -> CalibrationPolicy:
    """ADMIN explicitly binds a reviewed real evaluation to the catalog reference snapshot.

    This validates reported evidence, not the provenance/labels of unseen image files.
    The caller must ensure dataset reference images actually match this catalog snapshot.
    """
    if (
        report.get("synthetic") is not False
        or report.get("dataset_selection_eligible") is not True
        or report.get("top3_go_no_go") != "GO"
    ):
        raise ValueError("Real eligible evaluation required; synthetic/profile/NO_GO rejected")
    if any(
        report.get(key) != expected
        for key, expected in {
            "encoder": spec.name,
            "encoder_version": spec.version,
            "weights_sha256": spec.weights_sha256,
            "preprocess_version": spec.preprocess_version,
            "embedding_dimensions": spec.dimensions,
        }.items()
    ):
        raise ValueError("Evaluation encoder/preprocessing mismatch")
    models = report.get("per_model_counts", {})
    if not isinstance(models, dict) or len(models) < 4:
        raise ValueError("At least four independently evaluated models required")
    for counts in models.values():
        if not isinstance(counts, dict) or any(
            type(counts.get(k)) is not int or counts[k] < n
            for k, n in {"reference": 5, "calibration": 2, "test": 3}.items()
        ):
            raise ValueError("Insufficient independent evaluation splits")
    counts = report.get("counts", {})
    if not isinstance(counts, dict) or any(
        type(counts.get(k)) is not int or counts[k] < 3
        for k in ("unknown_calibration", "unknown_test")
    ):
        raise ValueError("Unknown calibration/test required")
    metrics = report.get("metrics", {})
    if not isinstance(metrics, dict):
        raise ValueError("Evaluation metrics required")
    for key in (
        "top1_accuracy",
        "top3_accuracy",
        "unknown_precision",
        "unknown_recall",
        "unknown_false_accept_rate",
        "known_false_reject_rate",
    ):
        value = metrics.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("Finite measured metrics required")
    if metrics["top3_accuracy"] < 0.9:
        raise ValueError("Top-3 target not met")
    raw = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return CalibrationPolicy(
        encoder_fingerprint=spec.fingerprint,
        reference_fingerprint=reference_fingerprint,
        dataset_sha256=report.get("manifest_sha256"),
        evaluation_sha256=hashlib.sha256(raw).hexdigest(),
        threshold=report.get("threshold"),
        provenance="ADMIN_REVIEWED_REAL_EVALUATION",
    )
