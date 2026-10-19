"""Explicit offline evaluation CLI; never connects to application DB or storage."""

import argparse
import json
import sys
from pathlib import Path

from .manifest import DatasetError, load_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare-weights", help="Explicit public pretrained weight download")
    fixture = sub.add_parser("synthetic", help="Generate a new synthetic fixture directory")
    fixture.add_argument("root", type=Path)
    validate = sub.add_parser("validate")
    run = sub.add_parser("benchmark")
    for command in (validate, run):
        command.add_argument("--manifest", type=Path, required=True)
        command.add_argument("--root", type=Path, required=True)
    run.add_argument(
        "--encoder", choices=("mobilenet_v3_small", "shufflenet_v2_x0_5"), required=True
    )
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--profile-only", action="store_true", help="Latency only; profile manifest")
    run.add_argument("--threads", type=int, default=2)
    run.add_argument("--repeats", type=int, default=3)
    run.add_argument("--warmup", type=int, default=5)
    args = parser.parse_args()
    try:
        if args.command == "prepare-weights":
            from .torch_cpu import prepare_weights

            prepare_weights()
            print("Public pretrained weights cached and checksum prefixes verified")
        elif args.command == "synthetic":
            from .synthetic import generate

            generate(args.root)
            print("Synthetic fixture created; prohibited as production selection evidence")
        elif args.command == "validate":
            dataset = load_dataset(args.manifest, args.root)
            print(
                json.dumps(
                    {
                        "dataset_id": dataset.id,
                        "samples": len(dataset.samples),
                        "synthetic": dataset.synthetic,
                        "manifest_sha256": dataset.manifest_sha256,
                    }
                )
            )
        else:
            from .torch_cpu import benchmark

            if args.output.exists():
                raise DatasetError("Output already exists; choose a new report path")
            result = benchmark(
                args.manifest,
                args.root,
                args.encoder,
                args.threads,
                args.repeats,
                args.warmup,
                args.profile_only,
            )
            # Exclusive create preserves earlier evidence. Parent must exist.
            with args.output.open("x") as stream:
                json.dump(result, stream, indent=2, allow_nan=False)
                stream.write("\n")
            print(
                json.dumps(
                    {
                        "encoder": args.encoder,
                        "samples": sum(result["counts"].values()),
                        "top3_go_no_go": result["top3_go_no_go"],
                        "encoder_selection": result["encoder_selection"],
                    }
                )
            )
    except (DatasetError, ValueError, OSError) as error:
        # No stack traces/EXIF/secret environment in normal CLI diagnostics.
        message = str(error) if isinstance(error, DatasetError) else type(error).__name__
        print(f"Evaluation failed: {message}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
