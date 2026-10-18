"""Create local development secrets, preserving an invalid existing file as a private backup."""
import os
import re
import secrets
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = root / ".env"
lines = (target if target.exists() else root / ".env.example").read_text().splitlines()
if any(line.strip() and not line.lstrip().startswith("#")
       and not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", line) for line in lines):
    backup = root / ".env.backup-sprint0"
    if backup.exists():
        raise SystemExit("Invalid .env; backup already exists. Review both files manually.")
    shutil.copy2(target, backup)
    if os.name != "nt":
        backup.chmod(0o600)
    lines = (root / ".env.example").read_text().splitlines()
    print("Invalid .env preserved in ignored .env.backup-sprint0; using .env.example.")
values = dict(line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))
for key in ("POSTGRES_PASSWORD", "JWT_SECRET"):
    value = values.get(key, "").strip()
    if not value or value.upper() == "CHANGE_ME":
        values[key] = secrets.token_urlsafe(48)
        lines = [line for line in lines if not line.startswith(key + "=")]
        lines.append(key + "=" + values[key])
target.write_text("\n".join(lines) + "\n")
if os.name != "nt":
    target.chmod(0o600)
print("Local .env is ready. Existing non-placeholder secrets preserved.")
