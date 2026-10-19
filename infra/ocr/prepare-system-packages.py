"""Build-only bounded parallel fetch; APT still verifies signed metadata/package integrity."""

import hashlib
import shlex
import subprocess
import urllib.request
from urllib.parse import unquote, urlsplit
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PACKAGES = ["libgomp1", "libgl1", "libglib2.0-0", "fonts-dejavu-core"]


def fetch(line: str) -> None:
    url, filename, raw_size, *_ = shlex.split(line)
    size = int(raw_size)
    if (
        Path(filename).name != filename
        or not filename.endswith(".deb")
        or size > 128 * 1024 * 1024
    ):
        raise ValueError("Invalid APT package metadata")
    metadata = subprocess.check_output(
        ["apt-cache", "show", filename.split("_", 1)[0]], text=True
    )
    digest = None
    for paragraph in metadata.split("\n\n"):
        fields = dict(
            row.split(": ", 1)
            for row in paragraph.splitlines()
            if ": " in row and not row.startswith(" ")
        )
        source = fields.get("Filename")
        if source and unquote(urlsplit(url).path).endswith("/" + source):
            digest = fields.get("SHA256")
            break
    if digest is None:
        raise ValueError("APT SHA256 metadata unavailable")
    algorithm = "sha256"
    target = Path("/var/cache/apt/archives") / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    if (
        target.is_file()
        and hashlib.new(algorithm, target.read_bytes()).hexdigest() == digest
    ):
        return
    chunk = 1024 * 1024

    def part(start: int) -> tuple[int, bytes]:
        end = min(size - 1, start + chunk - 1)
        for attempt in range(3):
            try:
                request = urllib.request.Request(
                    url, headers={"Range": f"bytes={start}-{end}"}
                )
                with urllib.request.urlopen(request, timeout=90) as response:
                    data = response.read(end - start + 2)
                if len(data) != end - start + 1:
                    raise ValueError("Unexpected package range")
                return start, data
            except (OSError, ValueError):
                if attempt == 2:
                    raise
        raise RuntimeError("Download exhausted")

    temporary = target.with_suffix(".deb.partial")
    with temporary.open("wb") as output:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for start, data in pool.map(part, range(0, size, chunk)):
                output.seek(start)
                output.write(data)
    if hashlib.new(algorithm, temporary.read_bytes()).hexdigest() != digest:
        raise ValueError("APT package checksum mismatch")
    temporary.replace(target)
    print("APT cache verified:", filename, flush=True)


def main() -> None:
    listing = subprocess.check_output(
        [
            "apt-get",
            "--print-uris",
            "--yes",
            "--no-install-recommends",
            "install",
            *PACKAGES,
        ],
        text=True,
    )
    entries = [line for line in listing.splitlines() if line.startswith("'")]
    if len(entries) > 128:
        raise ValueError("APT package set exceeds build limit")
    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(fetch, entries))


if __name__ == "__main__":
    main()
