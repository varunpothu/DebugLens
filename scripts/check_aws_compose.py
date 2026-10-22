"""CLI for checking a rendered AWS Docker Compose configuration."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from app.deployment_policy import validate_compose_config


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("Usage: python scripts/check_aws_compose.py <rendered-compose.json>", file=sys.stderr)
        return 2
    path = Path(args[0])
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Could not read rendered Compose JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(config, dict):
        print("Rendered Compose configuration must be a JSON object.", file=sys.stderr)
        return 2
    errors = validate_compose_config(config)
    if errors:
        print("AWS Compose policy failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("AWS Compose policy checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
