"""Small CPU encoder boundary. API startup never imports torch or downloads weights."""

import hashlib
import io
import math
import threading
import warnings
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from fastapi import HTTPException
from PIL import Image, ImageOps

from app.config import get_settings
from app.image_validation import FORMATS, decode_lock
from app.recognition_schemas import EncoderSpec


class EncoderUnavailable(RuntimeError):
    pass


class ImageEncoder(Protocol):
    @property
    def spec(self) -> EncoderSpec: ...
    def encode(self, image: Image.Image) -> Sequence[float]: ...


def normalized(vector: Sequence[float], dimensions: int) -> list[float]:
    if not isinstance(vector, (list, tuple)):
        raise ValueError("Embedding must be a numeric sequence")
    if len(vector) != dimensions or any(
        type(x) not in (int, float) or not math.isfinite(x) for x in vector
    ):
        raise ValueError("Invalid embedding dimensions or values")
    norm = math.sqrt(math.fsum(float(x) * float(x) for x in vector))
    if not math.isfinite(norm) or norm <= 1e-12:
        raise ValueError("Invalid embedding norm")
    return [float(x) / norm for x in vector]


def decode_image(data: bytes, mime_type: str) -> Image.Image:
    """Decode bounded original pixels, preserving the evaluation preprocessing semantics.

    No file writes, re-encoding, EXIF output or metadata logging. EXIF is consumed for orientation.
    """
    if not data or len(data) > get_settings().image_max_bytes:
        raise HTTPException(413, "Recognition image exceeds byte limit")
    expected = (
        "JPEG"
        if data.startswith(b"\xff\xd8\xff")
        else "PNG"
        if data.startswith(b"\x89PNG\r\n\x1a\n")
        else "WEBP"
        if data.startswith(b"RIFF") and data[8:12] == b"WEBP"
        else None
    )
    if expected is None or FORMATS[expected][0] != mime_type:
        raise HTTPException(415, "Recognition image type mismatch")
    try:
        with decode_lock, warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=[expected]) as image:
                if (
                    min(image.size) < 1
                    or max(image.size) > 4096
                    or image.width * image.height > 16000000
                ):
                    raise HTTPException(422, "Recognition dimensions exceed limit")
                if getattr(image, "n_frames", 1) != 1:
                    raise HTTPException(422, "Single-frame recognition images required")
                image.verify()
            with Image.open(io.BytesIO(data), formats=[expected]) as image:
                return ImageOps.exif_transpose(image).convert("RGB")
    except (
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise HTTPException(422, "Recognition image cannot be decoded") from None


# Exact candidates measured by Task3-01; constructor always requires an explicit name.
WEIGHTS = {
    "mobilenet_v3_small": (
        "mobilenet_v3_small-047dcff4.pth",
        "047dcff4addef86ea5bc2eff13c9614dc11f47ab1160d0a71a25e7db994f4e1f",
        576,
    ),
    "shufflenet_v2_x0_5": (
        "shufflenetv2_x0.5-f707e7126e.pth",
        "f707e7126e8601ea5fa0e272e0f35c52807773d603bcb11e611fa04a0b0880fd",
        1024,
    ),
}


class TorchCPUEncoder:
    def __init__(self, name: str, weights_root: Path) -> None:
        if name not in WEIGHTS:
            raise EncoderUnavailable("Explicit supported encoder required")
        try:
            import torch
            import torchvision
            from torchvision import models
        except ImportError:
            raise EncoderUnavailable(
                "Optional CPU encoder dependencies are not installed"
            ) from None
        if str(torch.__version__) != "2.10.0+cpu" or str(torchvision.__version__) != "0.25.0+cpu":
            raise EncoderUnavailable("Encoder dependency version mismatch")
        filename, digest, dimensions = WEIGHTS[name]
        path = weights_root / filename
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
                raise OSError()
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            raise EncoderUnavailable("Pinned CPU weights are unavailable") from None
        if actual != digest:
            raise EncoderUnavailable("Pinned CPU weights checksum mismatch")
        weights = (
            models.MobileNet_V3_Small_Weights.IMAGENET1K_V1
            if name == "mobilenet_v3_small"
            else models.ShuffleNet_V2_X0_5_Weights.IMAGENET1K_V1
        )
        torch.set_num_threads(2)
        if torch.get_num_interop_threads() != 1:
            torch.set_num_interop_threads(1)
        torch.use_deterministic_algorithms(True)
        torch.manual_seed(0)
        self._torch = torch
        self._model = getattr(models, name)(weights=None)
        self._model.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
        if name == "mobilenet_v3_small":
            self._model.classifier = torch.nn.Identity()
        else:
            self._model.fc = torch.nn.Identity()
        self._model.eval().to("cpu")
        self._transform = weights.transforms()
        self._lock = threading.Lock()
        preprocess = "exif-transpose-rgb-v1;" + repr(self._transform)
        self._spec = EncoderSpec(
            name=name,
            version="torchvision-0.25.0+cpu:IMAGENET1K_V1",
            weights_sha256=digest,
            preprocess_version=hashlib.sha256(preprocess.encode()).hexdigest(),
            dimensions=dimensions,
        )

    @property
    def spec(self) -> EncoderSpec:
        return self._spec

    def encode(self, image: Image.Image) -> Sequence[float]:
        with self._lock, self._torch.inference_mode():
            tensor = self._transform(image).unsqueeze(0)
            values = self._model(tensor).flatten().tolist()
        return normalized(values, self.spec.dimensions)
