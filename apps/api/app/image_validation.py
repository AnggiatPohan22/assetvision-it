"""Decode and re-encode only bounded, single-frame JPEG/PNG/WebP images."""

import hashlib
import io
import threading
import warnings
from dataclasses import dataclass

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import get_settings

FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}
decode_lock = threading.Lock()


@dataclass(frozen=True)
class ValidatedImage:
    data: bytes
    mime_type: str
    extension: str
    sha256: str


def validate_image(data: bytes, claimed_type: str) -> ValidatedImage:
    settings = get_settings()
    if len(data) > settings.image_max_bytes:
        raise HTTPException(413, "Image exceeds configured byte limit")
    if data.startswith(b"\xff\xd8\xff"):
        expected = "JPEG"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        expected = "PNG"
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        expected = "WEBP"
    else:
        raise HTTPException(415, "Only JPEG, PNG and WebP images are accepted")
    mime_type, extension = FORMATS[expected]
    if claimed_type != mime_type:
        raise HTTPException(415, "Image content type does not match its contents")
    try:
        with decode_lock, warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=[expected]) as original:
                width, height = original.size
                if (
                    max(width, height) > settings.image_max_dimension
                    or width * height > settings.image_max_pixels
                ):
                    raise HTTPException(
                        422, "Image dimensions or pixel count exceed configured limit"
                    )
                if getattr(original, "n_frames", 1) != 1:
                    raise HTTPException(422, "Animated or multi-frame images are not accepted")
                original.verify()
            with Image.open(io.BytesIO(data), formats=[expected]) as original:
                original.load()
                oriented = ImageOps.exif_transpose(original)
                # New pixel buffer intentionally drops EXIF/GPS, ICC, text, and trailing data.
                converted = oriented.convert("RGB" if expected == "JPEG" else "RGBA")
                clean = Image.new(converted.mode, converted.size)
                clean.paste(converted)
                output = io.BytesIO()
                clean.save(output, format=expected)
                encoded = output.getvalue()
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise HTTPException(422, "Image could not be safely decoded") from None
    if len(encoded) > settings.image_max_bytes:
        raise HTTPException(413, "Sanitized image exceeds configured byte limit")
    return ValidatedImage(encoded, mime_type, extension, hashlib.sha256(encoded).hexdigest())
