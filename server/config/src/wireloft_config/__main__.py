from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import yaml

from .paths import find_project_root, possible_config_paths
from .settings import settings


def _resolve_config_file() -> Path | None:
    env_path = os.getenv("WL_CONFIG_FILE")
    if env_path:
        p = Path(env_path)
        return p if p.exists() else None
    for p in possible_config_paths(find_project_root()):
        if p.exists():
            return p
    return None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Print the current WireLoft configuration")
    parser.add_argument("--format", "-f", choices=["json", "yaml"], default="json", help="Output format")
    args = parser.parse_args(argv)

    data: dict[str, Any] = settings.model_dump(mode="python")

    print("# WireLoft Settings\n")
    print()

    if args.format == "yaml":
        print(yaml.safe_dump(data, sort_keys=False))
    else:
        print(json.dumps(data, indent=2, default=str))


if __name__ == "__main__":
    main()
