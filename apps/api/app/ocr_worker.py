"""Private CPU child process. Parent owns timeout; models are local and validated twice."""

import io
import sys
from importlib.metadata import version
from pathlib import Path

from PIL import Image

from app.ocr_adapter import ENGINE_VERSION, MODEL_NAMES, model_fingerprint
from app.ocr_schemas import OCRLine, OCRReading


def main() -> None:
    root, output = map(Path, sys.argv[1:])
    fingerprint = model_fingerprint(root)
    for package, expected in (
        ("paddleocr", "3.2.0"),
        ("paddlepaddle", "3.2.0"),
        ("paddlex", "3.2.1"),
    ):
        if version(package) != expected:
            raise ValueError("OCR dependency mismatch")
    import numpy as np
    from paddleocr import PaddleOCR

    data = sys.stdin.buffer.read(64 * 1024 * 1024 + 1)
    if len(data) > 64 * 1024 * 1024:
        raise ValueError("Worker input too large")
    with Image.open(io.BytesIO(data)) as image:
        image = image.convert("RGB")
        # Paddle expects BGR, not PIL RGB. No orientation/unwarping models auto-created.
        pixels = np.asarray(image)[:, :, ::-1].copy()
    engine = PaddleOCR(
        text_detection_model_name=MODEL_NAMES[0],
        text_detection_model_dir=str(root / MODEL_NAMES[0]),
        text_recognition_model_name=MODEL_NAMES[1],
        text_recognition_model_dir=str(root / MODEL_NAMES[1]),
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        device="cpu",
        cpu_threads=2,
        enable_mkldnn=False,
        text_det_limit_side_len=960,
        text_det_limit_type="max",
        text_rec_score_thresh=0.0,
    )
    results = list(engine.predict(pixels))
    if len(results) != 1:
        raise ValueError("Single image result required")
    texts, scores = results[0]["rec_texts"], results[0]["rec_scores"]
    if len(texts) != len(scores) or len(texts) > 128:
        raise ValueError("Invalid OCR line counts")
    reading = OCRReading(
        engine_version=ENGINE_VERSION,
        model_fingerprint=fingerprint,
        lines=tuple(
            OCRLine(text=text, score=float(score))
            for text, score in zip(texts, scores, strict=True)
        ),
    )
    if sum(len(line.text) + 1 for line in reading.lines) > 16384:
        raise ValueError("OCR text exceeds limit")
    output.write_text(reading.model_dump_json())


if __name__ == "__main__":
    main()
