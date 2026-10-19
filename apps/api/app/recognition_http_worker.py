"""Child process for optional pinned encoder, bounded stdin/output, no DB access."""

import io
import json
import sys
from pathlib import Path

from PIL import Image

from app.recognition_encoder import TorchCPUEncoder


def main() -> None:
    encoder = TorchCPUEncoder(sys.argv[1], Path(sys.argv[2]))
    if sys.argv[3] == "spec":
        result = encoder.spec.model_dump(mode="json")
    else:
        raw = sys.stdin.buffer.read(64 * 1024 * 1024 + 1)
        if len(raw) > 64 * 1024 * 1024:
            raise ValueError("Bounded child input required")
        with Image.open(io.BytesIO(raw)) as image:
            result = {
                "spec": encoder.spec.model_dump(mode="json"),
                "vector": list(encoder.encode(image.convert("RGB"))),
            }
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
