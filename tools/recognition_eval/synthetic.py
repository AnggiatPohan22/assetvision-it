"""Generated patterns exercise the harness, never represent physical device accuracy."""

import hashlib
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw

from .manifest import fingerprints


def generate(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=False)
    rows = []
    seen: list[int] = []
    for model_index in range(6):
        unknown = model_index >= 4
        counts = (
            {"unknown_calibration": 3, "unknown_test": 3}
            if unknown
            else {"reference": 5, "calibration": 2, "test": 3}
        )
        for split, count in counts.items():
            for number in range(count):
                sample_id = f"pattern-{model_index}-{split}-{number}"
                rng = random.Random(sample_id)
                # Distinct coarse backgrounds avoid exact/perceptual copies across splits.
                for _ in range(100):
                    image = Image.new("RGB", (256, 256))
                    draw = ImageDraw.Draw(image)
                    for y in range(8):
                        for x in range(8):
                            shade = rng.randrange(40, 220)
                            draw.rectangle(
                                (x * 32, y * 32, x * 32 + 31, y * 32 + 31),
                                fill=(shade, shade, shade),
                            )
                    color = [
                        (230, 40, 40),
                        (20, 180, 30),
                        (30, 60, 230),
                        (230, 200, 30),
                        (170, 40, 170),
                        (20, 190, 200),
                    ][model_index]
                    offset = rng.randrange(-10, 11)
                    draw.rounded_rectangle(
                        (65 + offset, 60, 190 + offset, 195), radius=8 + model_index * 5, fill=color
                    )
                    for bar in range(model_index + 1):
                        draw.line(
                            (80 + bar * 16 + offset, 85, 80 + bar * 16 + offset, 165),
                            fill="black",
                            width=4,
                        )
                    _, dhash = fingerprints(image)
                    if all((dhash ^ old).bit_count() > 4 for old in seen):
                        seen.append(dhash)
                        break
                else:
                    raise RuntimeError("Could not create distinct synthetic fixture")
                name = sample_id + ".png"
                image.save(root / name)
                rows.append(
                    {
                        "id": sample_id,
                        "path": name,
                        "sha256": hashlib.sha256((root / name).read_bytes()).hexdigest(),
                        "model_id": None if unknown else f"synthetic-model-{model_index}",
                        "split": split,
                        "capture_group": sample_id,
                        "source": "generated-geometric-pattern-v1; not a device photo",
                        "license": "project-generated test fixture",
                        "captured_at": "2026-10-19T00:00:00+00:00",
                    }
                )
    manifest = root / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "dataset_id": "synthetic-patterns-v1",
                "synthetic": True,
                "samples": rows,
            },
            indent=2,
        )
        + "\n"
    )
    return manifest
