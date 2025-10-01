from __future__ import annotations

import argparse
import json
from typing import Any

import yaml

from .getter import get_settings


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Print the current WireLoft configuration")
    parser.add_argument("--format", "-f", choices=["json", "yaml"], default="json", help="Output format")
    args = parser.parse_args(argv)

    print("# WireLoft Settings\n")
    if args.format == "yaml":
        data: dict[str, Any] = get_settings().model_dump(mode="python", by_alias=True)
        print(yaml.safe_dump(data, sort_keys=False))
    else:
        data: dict[str, Any] = get_settings().model_dump(mode="python", by_alias=False)
        print(json.dumps(data, indent=2, default=str))


if __name__ == "__main__":
    main()
