"""Explicit build-time public model download; runtime never invokes this script."""

import argparse
import hashlib
import json
import tarfile
import tempfile
import urllib.request
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--archive-cache-url", default="")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    args.root.mkdir(parents=True, exist_ok=True)
    for name, entries in manifest.items():
        url = (
            "https://paddle-model-ecology.bj.bcebos.com/paddlex/"
            "official_inference_model/paddle3.0.0/" + name + "_infer.tar"
        )
        if args.archive_cache_url:
            url = args.archive_cache_url.rstrip("/") + "/" + name + "_infer.tar"
        with urllib.request.urlopen(url, timeout=120) as response:
            data = response.read(40 * 1024 * 1024 + 1)
        if len(data) > 40 * 1024 * 1024:
            raise ValueError("Model archive exceeds limit")
        with tempfile.TemporaryFile() as stream:
            stream.write(data)
            stream.seek(0)
            with tarfile.open(fileobj=stream) as bundle:
                directory = args.root / name
                directory.mkdir(exist_ok=True)
                for filename, digest in entries.items():
                    members = [
                        member for member in bundle.getmembers()
                        if member.name.rsplit("/", 1)[-1] == filename and member.isfile()
                    ]
                    if len(members) != 1 or members[0].size > 32 * 1024 * 1024:
                        raise ValueError("Invalid model archive")
                    source = bundle.extractfile(members[0])
                    if source is None:
                        raise ValueError("Model file unavailable")
                    content = source.read(32 * 1024 * 1024 + 1)
                    if hashlib.sha256(content).hexdigest() != digest:
                        raise ValueError("Pinned model checksum mismatch")
                    # Extract only fixed filenames; never trust archive paths or symlinks.
                    (directory / filename).write_bytes(content)


if __name__ == "__main__":
    main()
