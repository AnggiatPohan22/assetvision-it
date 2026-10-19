"""Opt-in CPU encoder behind hard process deadlines; no runtime weight download."""

import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from PIL import Image

from app.recognition_encoder import EncoderUnavailable, normalized
from app.recognition_schemas import EncoderSpec


class ProcessCPUEncoder:
    def __init__(self, name: str, root: Path) -> None:
        self.name, self.root = name, root
        self._spec: EncoderSpec | None = None

    def _run(self, data: bytes, *, spec: bool = False) -> Any:
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "app.recognition_http_worker",
                    self.name,
                    str(self.root),
                    "spec" if spec else "encode",
                ],
                input=data,
                capture_output=True,
                timeout=10,
                check=False,
            )
            if result.returncode or len(result.stdout) > 128 * 1024:
                raise ValueError()
            return json.loads(result.stdout)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            raise EncoderUnavailable("Local CPU encoder unavailable") from None

    @property
    def spec(self) -> EncoderSpec:
        if self._spec is None:
            try:
                self._spec = EncoderSpec.model_validate(self._run(b"", spec=True))
            except ValueError:
                raise EncoderUnavailable("Invalid local encoder specification") from None
        return self._spec

    def encode(self, image: Image.Image) -> list[float]:
        data = io.BytesIO()
        image.save(data, format="PNG")
        try:
            reading = self._run(data.getvalue())
            if EncoderSpec.model_validate(reading["spec"]) != self.spec:
                raise ValueError()
            return normalized(reading["vector"], self.spec.dimensions)
        except (KeyError, TypeError, ValueError):
            raise EncoderUnavailable("Invalid or changed CPU encoder output") from None
