from __future__ import annotations

import argparse
import asyncio
import inspect
import sys
from typing import Any, Dict, Optional

# Importing tasks ensures that all worker modules are loaded and registered
# via the wireloft_controller.registry -> wireloft_motherboard.registry integration.
import wireloft_controller.tasks  # noqa: F401
from wireloft_motherboard.scheduler.registry import all_definitions, get_task


class CLIProgress:
    def set(self, percent: int, message: Optional[str] = None, meta: Optional[dict] = None):
        p = max(0, min(100, int(percent)))
        parts = [f"{p:3d}%"]
        if message:
            parts.append(str(message))
        if meta:
            parts.append(str(meta))
        print(" | ".join(parts), file=sys.stderr)


def _parse_kv_list(kvs: list[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for item in kvs:
        if "=" not in item:
            # treat as flag True
            out[item.replace("-", "_")] = True
            continue
        key, val = item.split("=", 1)
        key = key.strip().replace("-", "_")
        val = val.strip()
        # Light heuristics for types
        if val.lower() in {"true", "false"}:
            out[key] = (val.lower() == "true")
        else:
            try:
                if val.isdigit() or (val.startswith("-") and val[1:].isdigit()):
                    out[key] = int(val)
                else:
                    out[key] = float(val)
            except ValueError:
                out[key] = val
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wireloft-controller",
        description="WireLoft Controller CLI — list and run controller workers",
    )

    sub = parser.add_subparsers(dest="command")

    # list
    p_list = sub.add_parser("list", help="List available workers (task definitions)")
    p_list.add_argument("--verbose", action="store_true", help="Show full descriptions")

    # run
    p_run = sub.add_parser("run", help="Run a worker by its definition key")
    p_run.add_argument("key", help="Task definition key")

    # Common convenience arguments used by many workers
    p_run.add_argument("--resource-id", "--id", type=int, help="Resource id for the task (if required)")
    p_run.add_argument("--slug", help="Resource slug for the task (if supported by the worker)")

    # Generic passthrough kwargs: name=value; may be repeated
    p_run.add_argument(
        "--arg",
        action="append",
        default=[],
        help="Additional keyword arguments as name=value. Repeat for multiple.",
    )

    return parser


def _merge_kwargs(ns: argparse.Namespace) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {}
    if getattr(ns, "resource_id", None) is not None:
        kwargs["resource_id"] = ns.resource_id
    if getattr(ns, "slug", None) is not None:
        kwargs["slug"] = ns.slug
    if getattr(ns, "arg", None):
        kwargs.update(_parse_kv_list(ns.arg))
    return kwargs


def _callable_accepts_progress(fn) -> bool:
    try:
        sig = inspect.signature(fn)
        return any(p.kind in (inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
                   and p.name == "progress" for p in sig.parameters.values())
    except (TypeError, ValueError):
        return True  # assume yes if unsure


def _run_task(def_key: str, kwargs: Dict[str, Any]) -> int:
    meta, fn = get_task(def_key)

    # Provide a simple progress sink if the callable supports it
    if _callable_accepts_progress(fn) and "progress" not in kwargs:
        kwargs["progress"] = CLIProgress()

    try:
        if inspect.iscoroutinefunction(fn):
            asyncio.run(fn(**kwargs))
        else:
            fn(**kwargs)
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def run_cli(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "list":
        defs = sorted(all_definitions(), key=lambda d: d.key)
        for d in defs:
            if args.verbose:
                print(f"{d.key}\n  title: {d.title}\n  description: {d.description}\n  allowed: {', '.join(d.allowed_resource_types)}\n")
            else:
                print(f"{d.key}: {d.title}")
        return 0

    if args.command == "run":
        kwargs = _merge_kwargs(args)
        if not kwargs:
            # Try calling with just progress, many tasks expect keyword-only args
            kwargs = {}
        return _run_task(args.key, kwargs)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
