"""Collect aggregate HTTP timings and cgroup resource counters from isolated smoke services.

No environment/config values, request payloads, cookies, images or individual predictions
are exported. Startup and fixture preparation contribute to cgroup lifetime peak memory.
"""

import json
import subprocess
import sys
from pathlib import Path

COMPOSE = [
    "docker",
    "compose",
    "-f",
    "compose.yaml",
    "-f",
    "compose.test.yaml",
    "-f",
    "compose.smoke.yaml",
    "-f",
    "compose.recognition-eval.yaml",
    "--profile",
    "test",
]
SERVICES = ("api-smoke", "web-smoke", "db-test")


def resources(service: str) -> dict[str, int]:
    script = "cat /sys/fs/cgroup/memory.peak /sys/fs/cgroup/memory.max; cat /sys/fs/cgroup/cpu.stat"
    result = subprocess.check_output(
        COMPOSE + ["exec", "-T", service, "sh", "-c", script], text=True
    )
    lines = result.splitlines()
    counters = dict(line.split() for line in lines[2:])
    return {
        "peak_memory_bytes": int(lines[0]),
        "memory_limit_bytes": int(lines[1]),
        "cpu_usage_usec": int(counters["usage_usec"]),
        "cpu_throttled_usec": int(counters.get("throttled_usec", 0)),
    }


def main() -> None:
    destination = Path(sys.argv[1])
    # Exclusive reservation before starting the workload, never overwrite an existing artifact.
    with destination.open("x") as output:
        before = {service: resources(service) for service in SERVICES}
        result = subprocess.run(
            COMPOSE
            + [
                "run",
                "--rm",
                "--no-deps",
                "api-test",
                "python",
                "tests/smoke_recognition_evaluation.py",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=240,
        )
        # Test failures never print captured secrets/response bodies. Keep diagnostics local.
        if result.returncode:
            output.write(json.dumps({"status": "FAILED", "exit_code": result.returncode}))
            raise SystemExit(
                "HTTP evaluation failed; report records failure without private output"
            )
        payloads = [
            line.removeprefix("EVALUATION_JSON=")
            for line in result.stdout.splitlines()
            if line.startswith("EVALUATION_JSON=")
        ]
        if len(payloads) != 1:
            raise SystemExit("Evaluation did not produce exactly one aggregate result")
        report = json.loads(payloads[0])
        after = {service: resources(service) for service in SERVICES}
        report["resources"] = {
            service: {
                **after[service],
                "workload_cpu_usec": after[service]["cpu_usage_usec"]
                - before[service]["cpu_usage_usec"],
                "workload_throttled_usec": after[service]["cpu_throttled_usec"]
                - before[service]["cpu_throttled_usec"],
            }
            for service in SERVICES
        }
        report["resource_scope"] = (
            "cgroup-v2 lifetime peak including startup/cache; CPU delta includes synthetic setup, "
            "login and HTTP scenarios; excludes test runner and host"
        )
        report["latency_scope"] = (
            "single serial cold session; generated 32x24 PNG; no warmup; proxy+API+DB; "
            "per-operation small sample; excludes CSRF/session fetch and setup; "
            "no real inference or SLA claim"
        )
        output.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print("PASS HTTP evaluation aggregate report written; no real-device accuracy claim")


if __name__ == "__main__":
    main()
