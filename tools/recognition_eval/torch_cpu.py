"""Benchmark-only feature extraction; no API adapter or persistent search index."""

import hashlib
import platform
import resource
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import numpy as np
import torch
import torchvision
from torchvision.models import (
    MobileNet_V3_Small_Weights,
    ShuffleNet_V2_X0_5_Weights,
    mobilenet_v3_small,
    shufflenet_v2_x0_5,
)

from .manifest import DatasetError, image_rgb, load_dataset
from .metrics import evaluate, normalized, rank_models

CANDIDATES = {
    "mobilenet_v3_small": (mobilenet_v3_small, MobileNet_V3_Small_Weights.IMAGENET1K_V1),
    "shufflenet_v2_x0_5": (shufflenet_v2_x0_5, ShuffleNet_V2_X0_5_Weights.IMAGENET1K_V1),
}


def weight_path(weights: Any) -> Path:
    return Path(torch.hub.get_dir()) / "checkpoints" / Path(urlsplit(weights.url).path).name


def prepare_weights() -> None:
    for _, weights in CANDIDATES.values():
        path = weight_path(weights)
        path.parent.mkdir(parents=True, exist_ok=True)
        prefix = path.stem.rsplit("-", 1)[1]
        if not path.exists():
            torch.hub.download_url_to_file(weights.url, str(path), hash_prefix=prefix)
        if not hashlib.sha256(path.read_bytes()).hexdigest().startswith(prefix):
            raise DatasetError("Public pretrained weights checksum mismatch")


def benchmark(
    manifest: Path,
    root: Path,
    encoder: str,
    threads: int = 2,
    repeats: int = 3,
    warmup: int = 5,
    profile_only: bool = False,
) -> dict[str, Any]:
    if encoder not in CANDIDATES or not 1 <= threads <= 8 or not 1 <= repeats <= 20:
        raise ValueError("Invalid candidate/threads/repeats")
    if not 1 <= warmup <= 50:
        raise ValueError("Warmup must be 1..50")
    dataset = load_dataset(manifest, root, require_splits=not profile_only)
    torch.set_num_threads(threads)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    builder, weights = CANDIDATES[encoder]
    path = weight_path(weights)
    if not path.is_file():
        raise DatasetError(
            "Weights not cached; explicitly prepare-weights before offline benchmark"
        )
    weight_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    if not weight_hash.startswith(path.stem.rsplit("-", 1)[1]):
        raise DatasetError("Cached weights checksum mismatch")
    started = time.perf_counter()
    torch.manual_seed(0)
    model = builder(weights=None)
    model.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
    if encoder == "mobilenet_v3_small":
        model.classifier = torch.nn.Identity()
    else:
        model.fc = torch.nn.Identity()
    model.eval().to("cpu")
    transform = weights.transforms()
    cold_ms = (time.perf_counter() - started) * 1000
    preprocess_spec = "exif-transpose-rgb-v1;" + repr(transform)
    timings: dict[str, list[float]] = {
        "decode_preprocess_ms": [],
        "encoder_ms": [],
        "search_ms": [],
        "end_to_end_ms": [],
    }
    embeddings: dict[str, np.ndarray] = {}
    with torch.inference_mode():
        warm = transform(image_rgb(dataset.samples[0].path)).unsqueeze(0)
        for _ in range(warmup):
            model(warm)
        for sample in dataset.samples:
            tensor = transform(image_rgb(sample.path)).unsqueeze(0)
            embeddings[sample.id] = normalized(model(tensor).flatten().numpy())
        references = [
            (s.model_id, embeddings[s.id])
            for s in dataset.samples
            if s.split == "reference" and s.model_id is not None
        ]
        # Deterministic round-robin order; all samples, including unknowns, are timed.
        for _ in range(repeats):
            for sample in dataset.samples:
                start = time.perf_counter()
                tensor = transform(image_rgb(sample.path)).unsqueeze(0)
                preprocessed = time.perf_counter()
                vector = normalized(model(tensor).flatten().numpy())
                encoded = time.perf_counter()
                if references:
                    rank_models(vector, references)
                end = time.perf_counter()
                timings["decode_preprocess_ms"].append((preprocessed - start) * 1000)
                timings["encoder_ms"].append((encoded - preprocessed) * 1000)
                timings["search_ms"].append((end - encoded) * 1000)
                timings["end_to_end_ms"].append((end - start) * 1000)
    # Detect external dataset changes even if the container bind mount is read-only.
    checked = load_dataset(manifest, root, require_splits=not profile_only)
    if checked != dataset:
        raise DatasetError("Dataset changed during benchmark")
    result = (
        {
            "dataset_id": dataset.id,
            "synthetic": dataset.synthetic,
            "manifest_sha256": dataset.manifest_sha256,
            "counts": {"profile": len(dataset.samples)},
            "metrics": None,
            "threshold": None,
            "dataset_selection_eligible": False,
            "top3_go_no_go": "NO_GO",
            "encoder_selection": "DEFERRED_INCOMPLETE_REAL_DATASET",
            "scope": "CPU latency only; no independent reference/calibration/test/unknown sets",
        }
        if profile_only
        else evaluate(dataset, embeddings)
    )
    cpu = next(
        (
            line.split(":", 1)[1].strip()
            for line in Path("/proc/cpuinfo").read_text().splitlines()
            if line.startswith("model name")
        ),
        "unavailable",
    )
    if profile_only:
        timings.pop("search_ms")
    result.update(
        {
            "encoder": encoder,
            "encoder_version": f"torchvision-{torchvision.__version__}:IMAGENET1K_V1",
            "weights_sha256": weight_hash,
            "weights_bytes": path.stat().st_size,
            "preprocess_version": hashlib.sha256(preprocess_spec.encode()).hexdigest(),
            "preprocess_spec": preprocess_spec,
            "embedding_dimensions": len(next(iter(embeddings.values()))),
            "environment": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "cpu": cpu,
                "torch": torch.__version__,
                "torchvision": torchvision.__version__,
                "numpy": np.__version__,
                "device": "cpu",
                "threads": threads,
                "cuda_used": False,
                "cgroup_cpu_max": Path("/sys/fs/cgroup/cpu.max").read_text().strip(),
                "cgroup_memory_max": Path("/sys/fs/cgroup/memory.max").read_text().strip(),
                "pid_peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
            },
            "benchmark": {
                "cold_model_load_ms": cold_ms,
                "warmup": warmup,
                "repeats": repeats,
                "batch_size": 1,
                "timed_samples": len(dataset.samples) * repeats,
                "latency": {
                    name: {
                        "p50": float(np.percentile(values, 50)),
                        "p95": float(np.percentile(values, 95)),
                    }
                    for name, values in timings.items()
                },
                "search_reference_count": len(references),
                "excludes": [
                    "manifest validation",
                    "weight download",
                    "API/network/upload",
                    "database",
                ],
            },
        }
    )
    return result
