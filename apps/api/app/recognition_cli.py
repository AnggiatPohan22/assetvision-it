"""Explicit local-operator CLI. No public recognition endpoint or automatic rebuild."""

import argparse
import json
import sys
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import get_settings
from app.recognition_encoder import WEIGHTS, EncoderUnavailable, TorchCPUEncoder
from app.recognition_index import actor, catalog_snapshot, head, rebuild_index, search_models
from app.recognition_schemas import RebuildRequest, SearchRequest
from app.storage import get_storage


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actor-id", required=True, type=uuid.UUID)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    build = sub.add_parser("rebuild")
    query = sub.add_parser("search")
    for command in (build, query):
        command.add_argument("--encoder", choices=tuple(WEIGHTS), required=True)
        command.add_argument(
            "--weights-root", type=Path, default=Path("/opt/weights/hub/checkpoints")
        )
    build.add_argument("--expected-version", type=int, required=True)
    build.add_argument("--reason", required=True)
    build.add_argument("--confirm-rebuild", action="store_true", required=True)
    build.add_argument("--calibration-report", type=Path)
    build.add_argument("--calibration-reference-fingerprint")
    query.add_argument("--image", type=Path, required=True)
    query.add_argument(
        "--mime-type", choices=("image/jpeg", "image/png", "image/webp"), required=True
    )
    query.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()
    engine = create_engine(get_settings().db_url)
    try:
        with Session(engine, expire_on_commit=False) as db:
            # CLI assumes an authorized local operator. UUID is audit attribution, not a
            # replacement browser login. Future HTTP callers must supply authenticated actors.
            actor(db, args.actor_id, admin=args.command == "rebuild")
            if args.command == "status":
                state = head(db)
                snapshot = catalog_snapshot(db)
                result = {
                    "generation_version": state.version,
                    "current_index_id": str(state.current_index_id)
                    if state.current_index_id
                    else None,
                    "reference_fingerprint": snapshot.fingerprint,
                    "active_reference_count": len(snapshot.references),
                }
            else:
                encoder = TorchCPUEncoder(args.encoder, args.weights_root)
                if args.command == "rebuild":
                    report = None
                    if args.calibration_report:
                        with args.calibration_report.open("rb") as stream:
                            raw = stream.read(2 * 1024 * 1024 + 1)
                        if len(raw) > 2 * 1024 * 1024:
                            raise ValueError("Calibration report exceeds limit")
                        report = json.loads(raw)
                        if not isinstance(report, dict):
                            raise ValueError("Calibration report must be an object")
                    record = rebuild_index(
                        db,
                        get_storage(),
                        encoder,
                        RebuildRequest(
                            expected_version=args.expected_version,
                            reason=args.reason,
                            calibration_reference_fingerprint=args.calibration_reference_fingerprint,
                        ),
                        args.actor_id,
                        report,
                    )
                    result = {
                        "index_id": str(record.id),
                        "reference_count": record.reference_count,
                        "encoder": record.encoder_spec,
                        "calibrated": record.calibration is not None,
                        "generation_version": head(db).version,
                    }
                else:
                    with args.image.open("rb") as stream:
                        data = stream.read(get_settings().image_max_bytes + 1)
                    result = search_models(
                        db,
                        encoder,
                        data,
                        args.mime_type,
                        SearchRequest(top_k=args.top_k),
                        args.actor_id,
                    ).model_dump(mode="json")
            print(json.dumps(result, allow_nan=False))
    except HTTPException as error:
        print(f"Recognition command rejected ({error.status_code})", file=sys.stderr)
        return 2
    except (ValueError, OSError, EncoderUnavailable):
        print("Recognition configuration, image or encoder unavailable", file=sys.stderr)
        return 2
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
