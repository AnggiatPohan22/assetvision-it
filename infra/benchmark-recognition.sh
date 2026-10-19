#!/usr/bin/env bash
# Usage: bash infra/benchmark-recognition.sh DATASET_ROOT NEW_REPORT_DIR [PROFILE_MANIFEST]
# Requires prebuilt evaluation image; no downloads/network/application services at runtime.
set -euo pipefail
if (( $# < 2 || $# > 3 )); then echo "Usage: $0 DATASET_ROOT NEW_REPORT_DIR [PROFILE_MANIFEST]" >&2; exit 2; fi
dataset_root="$(realpath -e -- "$1")"
[[ -d "$dataset_root" ]] || exit 2
manifest="$(realpath -e -- "${3:-$dataset_root/manifest.json}")"
[[ -f "$manifest" ]] || exit 2
# Never overwrite a prior report/dataset. Parent must already exist.
report_parent="$(realpath -e -- "$(dirname -- "$2")")"
report_dir="$report_parent/$(basename -- "$2")"
[[ ! -e "$report_dir" && "$report_dir" != "$dataset_root" ]] || exit 2
case "$report_dir/" in "$dataset_root/"*) exit 2 ;; esac
mkdir -- "$report_dir"
run=(docker run --rm --network none --read-only --tmpfs /tmp:size=128m
  --env TORCHINDUCTOR_CACHE_DIR=/tmp/torchinductor-eval
  --cpus 2 --memory 2g --pids-limit 256 --cap-drop ALL --security-opt no-new-privileges
  --user "$(id -u):$(id -g)" --mount "type=bind,src=$dataset_root,dst=/dataset,readonly"
  --mount "type=bind,src=$manifest,dst=/input/manifest.json,readonly"
  --mount "type=bind,src=$report_dir,dst=/reports" assetvision-recognition-eval:3-01)
profile_args=()
if (( $# == 3 )); then
  profile_args=(--profile-only)
else
  "${run[@]}" validate --root /dataset --manifest /input/manifest.json
fi
# Independent fresh processes ensure each encoder has its own peak RSS.
for encoder in mobilenet_v3_small shufflenet_v2_x0_5; do
  "${run[@]}" benchmark --root /dataset --manifest /input/manifest.json \
    "${profile_args[@]}" --encoder "$encoder" --threads 2 --repeats 3 --warmup 5 --output "/reports/$encoder.json"
done
