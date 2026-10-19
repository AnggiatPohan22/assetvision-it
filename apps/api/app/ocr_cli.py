"""Local transient OCR/manual CLI; no database credentials, authentication or persistence."""

import argparse
import sys
from pathlib import Path

from fastapi import HTTPException
from pydantic import ValidationError

from app.ocr_adapter import PaddleCPUEngine
from app.ocr_schemas import ManualCorrection
from app.ocr_service import OCRUnavailable, read_label


def main() -> int:
    parser = argparse.ArgumentParser(description="Read one label; all output requires human review")
    parser.add_argument("--image", type=Path)
    parser.add_argument("--mime-type", choices=["image/jpeg", "image/png", "image/webp"])
    parser.add_argument("--engine", choices=["paddle", "manual"], required=True)
    parser.add_argument("--models-root", type=Path, default=Path("/opt/ocr-models"))
    parser.add_argument("--timeout-seconds", type=float, default=30)
    parser.add_argument(
        "--correction-file", type=Path, help="UTF-8 label text; separate from raw OCR"
    )
    args = parser.parse_args()
    try:
        data = None
        if args.image is not None:
            with args.image.open("rb") as stream:
                data = stream.read(8 * 1024 * 1024 + 1)
            if not args.mime_type:
                raise ValueError()
        elif args.engine == "paddle":
            raise ValueError()
        correction = None
        if args.correction_file is not None:
            with args.correction_file.open("rb") as stream:
                raw = stream.read(65537)
            if len(raw) > 65536:
                raise ValueError()
            correction = ManualCorrection(corrected_text=raw.decode("utf-8"))
        engine = (
            PaddleCPUEngine(args.models_root, timeout_seconds=args.timeout_seconds)
            if args.engine == "paddle"
            else None
        )
        result = read_label(data, args.mime_type, engine, correction)
        print(result.model_dump_json())
        return 0
    except (ValueError, OSError, ValidationError, HTTPException, OCRUnavailable):
        print(
            "OCR input or processing unavailable; inspect image/settings and use manual entry",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
