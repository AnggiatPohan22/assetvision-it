"""Offline weight handling and CLI must fail without fetching or overwriting evidence."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.recognition_eval.manifest import DatasetError
from tools.recognition_eval.synthetic import generate
from tools.recognition_eval.torch_cpu import benchmark


class OfflineTests(unittest.TestCase):
    def test_missing_or_corrupted_weights_never_download(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "dataset"
            manifest = generate(root)
            checkpoint = Path(directory) / "encoder-01234567.pth"
            with (
                patch("tools.recognition_eval.torch_cpu.weight_path", return_value=checkpoint),
                patch("torch.set_num_threads"),
                patch("torch.set_num_interop_threads"),
                patch("torch.hub.download_url_to_file") as download,
            ):
                with self.assertRaisesRegex(DatasetError, "not cached"):
                    benchmark(manifest, root, "mobilenet_v3_small")
                checkpoint.write_bytes(b"corrupt checkpoint")
                with self.assertRaisesRegex(DatasetError, "checksum"):
                    benchmark(manifest, root, "mobilenet_v3_small")
                download.assert_not_called()

    def test_resource_arguments_are_bounded_before_loading(self):
        for arguments in (
            {"threads": 0},
            {"threads": 9},
            {"repeats": 0},
            {"repeats": 21},
            {"warmup": 0},
            {"warmup": 51},
        ):
            with self.assertRaises(ValueError):
                benchmark(Path("missing"), Path("missing"), "mobilenet_v3_small", **arguments)
        with self.assertRaises(ValueError):
            benchmark(Path("missing"), Path("missing"), "unreviewed_encoder")

    def test_cli_refuses_to_overwrite_existing_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "existing.json"
            report.write_text("keep this evidence")
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tools.recognition_eval",
                    "benchmark",
                    "--manifest",
                    str(root / "absent.json"),
                    "--root",
                    str(root),
                    "--encoder",
                    "mobilenet_v3_small",
                    "--output",
                    str(report),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("already exists", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(report.read_text(), "keep this evidence")


if __name__ == "__main__":
    unittest.main()
