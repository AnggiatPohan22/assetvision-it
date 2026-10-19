import copy
import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image
from tools.recognition_eval.manifest import DatasetError, fingerprints, image_rgb, load_dataset
from tools.recognition_eval.metrics import (
    evaluate,
    normalized,
    rank_models,
    summarize,
    threshold_from_calibration,
)
from tools.recognition_eval.synthetic import generate


class ManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name) / "fixture"
        cls.manifest = generate(cls.root)
        cls.data = json.loads(cls.manifest.read_text())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def check_manifest(self, mutate):
        data = copy.deepcopy(self.data)
        mutate(data)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(data))
            return load_dataset(path, self.root)

    def invalid(self, mutate):
        with self.assertRaises(DatasetError):
            self.check_manifest(mutate)

    def test_complete_manifest_and_synthetic_provenance(self):
        dataset = load_dataset(self.manifest, self.root)
        self.assertEqual(len(dataset.samples), 52)
        self.assertTrue(dataset.synthetic)
        self.assertEqual(len(dataset.manifest_sha256), 64)

    def test_unknown_schema_or_fields_fail(self):
        self.invalid(lambda d: d.update(schema_version=2))
        self.invalid(lambda d: d.update(schema_version=True))
        self.invalid(lambda d: d.update(surprise="ignored?"))
        self.invalid(lambda d: d.update(synthetic="false"))

    def test_sample_id_and_provenance_are_required(self):
        self.invalid(lambda d: d["samples"][1].update(id=d["samples"][0]["id"]))
        for field in ("license", "source", "capture_group"):
            self.invalid(lambda d, field=field: d["samples"][0].update({field: ""}))
        self.invalid(lambda d: d["samples"][0].update(captured_at="2026-01-01"))

    def test_bad_split_and_identity_fail(self):
        self.invalid(lambda d: d["samples"][0].update(split=[]))
        self.invalid(lambda d: d["samples"][0].update(split="train"))
        self.invalid(lambda d: d["samples"][0].update(model_id=None))
        self.invalid(lambda d: d["samples"][-1].update(model_id="known"))
        self.invalid(lambda d: d["samples"][0].update(model_id=["wrong"]))

    def test_missing_unknown_calibration_or_model_reference_fails(self):
        self.invalid(
            lambda d: d.update(
                samples=[s for s in d["samples"] if s["split"] != "unknown_calibration"]
            )
        )
        self.invalid(lambda d: d["samples"][5].update(model_id="no-reference"))
        self.invalid(
            lambda d: d.update(
                samples=[
                    s
                    for s in d["samples"]
                    if not (s["model_id"] == "synthetic-model-0" and s["split"] == "test")
                ]
            )
        )

    def test_capture_group_cannot_cross_splits(self):
        self.invalid(
            lambda d: d["samples"][5].update(capture_group=d["samples"][0]["capture_group"])
        )

    def test_duplicate_bytes_and_wrong_hash_fail(self):
        self.invalid(
            lambda d: d["samples"][1].update(
                path=d["samples"][0]["path"], sha256=d["samples"][0]["sha256"]
            )
        )
        self.invalid(lambda d: d["samples"][0].update(sha256="0" * 64))

    def test_path_escape_absolute_url_and_symlink_fail(self):
        for path in ("../outside.png", "/etc/passwd", "https://example.test/img.png", "C:/img.png"):
            self.invalid(lambda d, path=path: d["samples"][0].update(path=path))
        link = self.root / "escape.png"
        link.symlink_to("/etc/passwd")
        try:
            self.invalid(lambda d: d["samples"][0].update(path="escape.png"))
        finally:
            link.unlink()

    def test_reencoded_and_near_duplicate_leakage(self):
        source = self.root / self.data["samples"][0]["path"]
        image = image_rgb(source)
        for mode in ("reencoded", "near"):
            target = self.root / (mode + ".png")
            copy_image = image.copy()
            if mode == "near":
                copy_image.putpixel((0, 0), (255, 255, 255))
            copy_image.save(target, compress_level=0)
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            try:
                self.invalid(
                    lambda d, target=target, digest=digest: d["samples"][5].update(
                        path=target.name, sha256=digest
                    )
                )
            finally:
                target.unlink()

    def test_image_limits_formats_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, size, fmt in (
                ("small.png", (32, 64), "PNG"),
                ("large.png", (4097, 64), "PNG"),
                ("fake.png", (64, 64), "GIF"),
            ):
                image = Image.new("RGB", size)
                image.save(root / name, format=fmt)
                with self.assertRaises(DatasetError):
                    image_rgb(root / name)
            (root / "bad.png").write_bytes(b"not a png")
            with self.assertRaises(DatasetError):
                image_rgb(root / "bad.png")
            with (root / "huge.png").open("wb") as stream:
                stream.truncate(10 * 1024 * 1024 + 1)
            with self.assertRaises(DatasetError):
                image_rgb(root / "huge.png")

    def test_rgb_fingerprint_independent_of_encoding(self):
        image = image_rgb(self.root / self.data["samples"][0]["path"])
        self.assertEqual(image.mode, "RGB")
        self.assertEqual(fingerprints(image), fingerprints(image.copy()))

    def test_real_latency_profile_never_masquerades_as_evaluation(self):
        data = copy.deepcopy(self.data)
        data["samples"] = data["samples"][:5]
        data["synthetic"] = False
        for row in data["samples"]:
            row["split"] = "profile"
            row["captured_at"] = None
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            path.write_text(json.dumps(data))
            dataset = load_dataset(path, self.root, require_splits=False)
            self.assertFalse(dataset.synthetic)
            with self.assertRaises(DatasetError):
                load_dataset(path, self.root)
            data["samples"][0]["split"] = "test"
            path.write_text(json.dumps(data))
            with self.assertRaises(DatasetError):
                load_dataset(path, self.root, require_splits=False)

    def test_fixture_will_not_overwrite_existing_data(self):
        with self.assertRaises(FileExistsError):
            generate(self.root)


class MetricTests(unittest.TestCase):
    def test_l2_and_vector_validation(self):
        np.testing.assert_allclose(normalized([3, 4]), [0.6, 0.8])
        for vector in ([], [0, 0], [float("nan"), 1], [float("inf")], [[1, 0]]):
            with self.assertRaises(ValueError):
                normalized(vector)
        with self.assertRaises(ValueError):
            rank_models([1, 0], [("a", [1, 0, 0])])

    def test_model_rank_max_reference_and_stable_tie(self):
        self.assertEqual(
            rank_models([1, 0], [("b", [1, 0]), ("a", [1, 0]), ("a", [0, 1])]),
            [("a", 1.0), ("b", 1.0)],
        )
        with self.assertRaises(ValueError):
            rank_models([1, 0], [])

    def test_calibration_frozen_threshold_and_boundary(self):
        threshold = threshold_from_calibration([0.9, 0.8], [0.3, 0.4])
        self.assertGreater(threshold, 0.4)
        self.assertLessEqual(threshold, 0.8)
        # All tied: conservative threshold rejects all, finite and slightly above one allowed.
        self.assertGreater(threshold_from_calibration([1], [1]), 1)
        for known, unknown in (([], [0]), ([0], []), ([float("nan")], [0])):
            with self.assertRaises(ValueError):
                threshold_from_calibration(known, unknown)

    def test_metrics_known_unknown_denominators_and_raw_topk(self):
        known = [
            ("a", [("a", 0.9), ("b", 0.1)]),
            ("b", [("a", 0.8), ("b", 0.2)]),
            ("b", [("b", 0.3), ("a", 0.1)]),
        ]
        unknown = [[("a", 0.1)], [("b", 0.9)]]
        result = summarize(known, unknown, 0.5)
        self.assertAlmostEqual(result["top1_accuracy"], 2 / 3)
        self.assertEqual(result["top3_accuracy"], 1)
        self.assertEqual(result["unknown_precision"], 0.5)
        self.assertEqual(result["unknown_recall"], 0.5)
        self.assertEqual(result["unknown_false_accept_rate"], 0.5)
        self.assertAlmostEqual(result["known_wrong_accept_rate"], 1 / 3)

    def test_no_predicted_unknown_precision_is_undefined(self):
        result = summarize([("a", [("a", 1)])], [[("a", 1)]], 0.5)
        self.assertIsNone(result["unknown_precision"])
        self.assertEqual(result["unknown_recall"], 0)
        self.assertIsNone(result["unknown_f1"])

    def test_test_labels_cannot_change_calibration_threshold(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "patterns"
            dataset = load_dataset(generate(root), root)
            vectors = {s.id: np.eye(6)[int(s.id.split("-")[1])] for s in dataset.samples}
            before = evaluate(dataset, vectors)
            for sample in dataset.samples:
                if sample.split in {"test", "unknown_test"}:
                    vectors[sample.id] = np.eye(6)[3]
            after = evaluate(dataset, vectors)
            self.assertEqual(before["threshold"], after["threshold"])
            self.assertEqual(before["top3_go_no_go"], "NO_GO")
            self.assertFalse(before["dataset_selection_eligible"])
            self.assertEqual(before["metrics"]["top1_accuracy"], 1)
            self.assertNotEqual(before["metrics"], after["metrics"])
            self.assertTrue(math.isfinite(before["threshold"]))
            vectors.pop(next(iter(vectors)))
            with self.assertRaises(ValueError):
                evaluate(dataset, vectors)


if __name__ == "__main__":
    unittest.main()
