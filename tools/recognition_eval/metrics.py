"""Deterministic model retrieval metrics. Rejection is positive for unknown metrics."""

import math
from collections import Counter
from typing import Any

import numpy as np

from .manifest import Dataset


def normalized(vector: Any) -> np.ndarray:
    array = np.asarray(vector, dtype=np.float64)
    if array.ndim != 1 or not array.size or not np.isfinite(array).all():
        raise ValueError("Embedding must be a finite nonempty vector")
    norm = float(np.linalg.norm(array))
    if not math.isfinite(norm) or norm <= 1e-12:
        raise ValueError("Embedding norm must be finite and nonzero")
    return array / norm


def rank_models(query: Any, references: list[tuple[str, Any]]) -> list[tuple[str, float]]:
    if not references:
        raise ValueError("Reference set cannot be empty")
    vector = normalized(query)
    best: dict[str, float] = {}
    for model, reference in references:
        other = normalized(reference)
        if other.shape != vector.shape:
            raise ValueError("Embedding dimensions differ")
        score = min(1.0, max(-1.0, float(np.dot(vector, other))))
        best[model] = max(best.get(model, -1.0), score)
    return sorted(best.items(), key=lambda item: (-item[1], item[0]))


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def threshold_from_calibration(known: list[float], unknown: list[float]) -> float:
    if (
        not known
        or not unknown
        or not all(math.isfinite(x) and -1 <= x <= 1 for x in known + unknown)
    ):
        raise ValueError("Calibration requires finite known and unknown cosine scores")
    candidates = [-1.0] + [math.nextafter(x, math.inf) for x in sorted(set(known + unknown))]
    # Max balanced known acceptance / unknown rejection. Ties choose conservative rejection.
    return max(
        candidates,
        key=lambda threshold: (
            (
                sum(x >= threshold for x in known) / len(known)
                + sum(x < threshold for x in unknown) / len(unknown)
            )
            / 2,
            threshold,
        ),
    )


def summarize(
    known: list[tuple[str, list[tuple[str, float]]]],
    unknown: list[list[tuple[str, float]]],
    threshold: float,
) -> dict[str, Any]:
    if not known or not unknown or not math.isfinite(threshold):
        raise ValueError("Held-out known/unknown samples and a frozen threshold are required")
    tp = sum(ranking[0][1] < threshold for ranking in unknown)
    fp = sum(ranking[0][1] < threshold for _, ranking in known)
    fn = len(unknown) - tp
    wrong_accepted = sum(
        ranking[0][1] >= threshold and ranking[0][0] != truth for truth, ranking in known
    )
    precision = ratio(tp, tp + fp)
    recall = ratio(tp, tp + fn)
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else 0.0
        if precision is not None and recall is not None
        else None
    )
    confusion = Counter(
        f"{truth}->{ranking[0][0] if ranking[0][1] >= threshold else 'UNKNOWN'}"
        for truth, ranking in known
    )
    return {
        "known_count": len(known),
        "unknown_count": len(unknown),
        "top1_accuracy": sum(ranking[0][0] == truth for truth, ranking in known) / len(known),
        "top3_accuracy": sum(truth in [m for m, _ in ranking[:3]] for truth, ranking in known)
        / len(known),
        "accepted_correct_known_rate": sum(
            r[0][1] >= threshold and r[0][0] == truth for truth, r in known
        )
        / len(known),
        "unknown_precision": precision,
        "unknown_recall": recall,
        "unknown_f1": f1,
        "unknown_false_accept_rate": fn / len(unknown),
        "known_false_reject_rate": fp / len(known),
        "known_wrong_accept_rate": wrong_accepted / len(known),
        "unknown_confusion": {
            "tp_rejected_unknown": tp,
            "fp_rejected_known": fp,
            "fn_accepted_unknown": fn,
            "tn_accepted_known": len(known) - fp,
        },
        "known_confusion": dict(sorted(confusion.items())),
    }


def evaluate(dataset: Dataset, embeddings: dict[str, Any]) -> dict[str, Any]:
    if set(embeddings) != {s.id for s in dataset.samples}:
        raise ValueError("Exactly one embedding per manifest sample is required")
    references = [
        (s.model_id, embeddings[s.id])
        for s in dataset.samples
        if s.split == "reference" and s.model_id is not None
    ]
    scores = {
        s.id: rank_models(embeddings[s.id], references)
        for s in dataset.samples
        if s.split != "reference"
    }
    threshold = threshold_from_calibration(
        [scores[s.id][0][1] for s in dataset.samples if s.split == "calibration"],
        [scores[s.id][0][1] for s in dataset.samples if s.split == "unknown_calibration"],
    )
    known = [
        (s.model_id, scores[s.id])
        for s in dataset.samples
        if s.split == "test" and s.model_id is not None
    ]
    unknown = [scores[s.id] for s in dataset.samples if s.split == "unknown_test"]
    metrics = summarize(known, unknown, threshold)
    per_model = {
        model: summarize([item for item in known if item[0] == model], unknown, threshold)
        for model in sorted({m for m, _ in known})
    }
    counts = Counter(s.split for s in dataset.samples)
    model_counts = {
        model: dict(Counter(s.split for s in dataset.samples if s.model_id == model))
        for model in sorted({m for m, _ in references})
    }
    ready = (
        not dataset.synthetic
        and len(model_counts) >= 4
        and all(
            v.get("reference", 0) >= 5 and v.get("test", 0) >= 3 and v.get("calibration", 0) >= 2
            for v in model_counts.values()
        )
        and counts["unknown_calibration"] >= 3
        and counts["unknown_test"] >= 3
    )
    return {
        "dataset_id": dataset.id,
        "synthetic": dataset.synthetic,
        "manifest_sha256": dataset.manifest_sha256,
        "counts": dict(sorted(counts.items())),
        "per_model_counts": model_counts,
        "threshold": threshold,
        "threshold_policy": "calibration-only balanced acceptance/rejection; tie=higher threshold",
        "score_label": "cosine similarity, not probability or calibrated confidence",
        "metrics": metrics,
        "per_model_metrics": per_model,
        "predictions": [
            {
                "sample_id": s.id,
                "split": s.split,
                "true_model_id": s.model_id,
                "top3": [{"model_id": m, "similarity": v} for m, v in scores[s.id][:3]],
                "rejected_unknown": scores[s.id][0][1] < threshold,
            }
            for s in dataset.samples
            if s.split != "reference"
        ],
        "dataset_selection_eligible": ready,
        "top3_go_no_go": "GO" if ready and metrics["top3_accuracy"] >= 0.9 else "NO_GO",
        "encoder_selection": "DEFERRED_REQUIRES_REAL_VALIDATION_AND_COMPARATIVE_REVIEW",
    }
