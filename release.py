#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent
SEMVER_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
VERSION_LINE_PATTERN = re.compile(r'^(?P<prefix>\s*version\s*=\s*")[^"]+(?P<suffix>".*)$')
MODULE_VERSION_PATTERN = re.compile(
    r'^(?P<prefix>\s*__version__\s*=\s*["\'])[^"\']+(?P<suffix>["\'].*)$'
)


class ReleaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class Component:
    name: str
    version: str
    manifest: Path
    path: Path

    @property
    def tag_prefix(self) -> str:
        return normalize_distribution_name(self.name)

    @property
    def tag(self) -> str:
        return f"{self.tag_prefix}-v{self.version}"


def run(
    *args: str,
    check: bool = True,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        capture_output=capture_output,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ReleaseError(f"Command failed ({' '.join(args)}): {detail}")
    return result


def git(*args: str, check: bool = True) -> str:
    return run("git", *args, check=check).stdout.strip()


def normalize_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_semver(version: str) -> tuple[int, int, int]:
    match = SEMVER_PATTERN.fullmatch(version)
    if match is None:
        raise ReleaseError(
            f"Version '{version}' is not supported. Use semantic versioning as MAJOR.MINOR.PATCH."
        )
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def bump_version(version: str, level: str) -> str:
    major, minor, patch = parse_semver(version)
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    if level == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ReleaseError(f"Unknown version bump '{level}'.")


def read_project(manifest: Path) -> tuple[str, str]:
    with manifest.open("rb") as file:
        project = tomllib.load(file).get("project", {})
    name = project.get("name")
    version = project.get("version")
    if not isinstance(name, str) or not isinstance(version, str):
        raise ReleaseError(f"{manifest} must define [project].name and [project].version.")
    parse_semver(version)
    return name, version


def discover_components() -> list[Component]:
    components: list[Component] = []
    server_dir = ROOT / "server"
    for manifest in sorted(server_dir.glob("*/pyproject.toml")):
        name, version = read_project(manifest)
        components.append(
            Component(
                name=name,
                version=version,
                manifest=manifest,
                path=manifest.parent,
            )
        )
    return components


def replace_project_version(text: str, version: str) -> str:
    parse_semver(version)
    lines = text.splitlines(keepends=True)
    in_project = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_project = stripped == "[project]"
            continue
        if not in_project:
            continue
        body = line.rstrip("\r\n")
        newline = line[len(body):]
        match = VERSION_LINE_PATTERN.match(body)
        if match is not None:
            lines[index] = f"{match.group('prefix')}{version}{match.group('suffix')}{newline}"
            return "".join(lines)
    raise ReleaseError("Could not find [project].version in pyproject.toml.")


def replace_module_version(text: str, version: str) -> str:
    parse_semver(version)
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        body = line.rstrip("\r\n")
        newline = line[len(body):]
        match = MODULE_VERSION_PATTERN.match(body)
        if match is not None:
            lines[index] = f"{match.group('prefix')}{version}{match.group('suffix')}{newline}"
            return "".join(lines)
    return text


def module_version_files(component: Component) -> list[Path]:
    source_dir = component.path / "src"
    if not source_dir.is_dir():
        return []
    files: list[Path] = []
    for init_file in sorted(source_dir.glob("*/__init__.py")):
        if "__version__" in init_file.read_text(encoding="utf-8"):
            files.append(init_file)
    return files


def version_tags(prefix: str) -> list[tuple[tuple[int, int, int], str]]:
    tags = git("tag", "--list", f"{prefix}*", "--sort=-v:refname").splitlines()
    parsed: list[tuple[tuple[int, int, int], str]] = []
    for tag in tags:
        version = tag.removeprefix(prefix)
        try:
            parsed.append((parse_semver(version), tag))
        except ReleaseError:
            continue
    parsed.sort(key=lambda item: item[0], reverse=True)
    return parsed


def latest_tag(prefix: str) -> str | None:
    tags = version_tags(prefix)
    return tags[0][1] if tags else None


def latest_tag_version(prefix: str) -> str | None:
    tag = latest_tag(prefix)
    return tag.removeprefix(prefix) if tag is not None else None


def path_changed_since(tag: str, path: Path) -> bool:
    relative_path = path.relative_to(ROOT).as_posix()
    result = run("git", "diff", "--quiet", f"{tag}..HEAD", "--", relative_path, check=False)
    if result.returncode == 0:
        return False
    if result.returncode == 1:
        return True
    raise ReleaseError(result.stderr.strip() or f"Could not compare {relative_path} with {tag}.")


def ensure_git_repository() -> None:
    repository_root = Path(git("rev-parse", "--show-toplevel")).resolve()
    if repository_root != ROOT.resolve():
        raise ReleaseError(f"release.py must live at the WireLoft repository root ({ROOT}).")


def ensure_clean_worktree() -> None:
    if git("status", "--porcelain"):
        raise ReleaseError("The working tree must be clean before preparing or publishing a release.")


def refresh_tags() -> None:
    run("git", "fetch", "origin", "--tags", "--quiet", capture_output=False)


def choose_version(label: str, current: str, *, allow_keep: bool) -> str:
    choices = [
        ("major", bump_version(current, "major")),
        ("minor", bump_version(current, "minor")),
        ("patch", bump_version(current, "patch")),
    ]
    print(f"\n{label}: current version {current}")
    for index, (level, version) in enumerate(choices, start=1):
        print(f"  {index}. {level:<5} -> {version}")
    next_index = 4
    if allow_keep:
        print(f"  {next_index}. keep  -> {current}")
        next_index += 1
    print(f"  {next_index}. exact version")

    while True:
        answer = input("Choose: ").strip().lower()
        aliases = {"major": "1", "minor": "2", "patch": "3"}
        answer = aliases.get(answer, answer)
        if answer in {"1", "2", "3"}:
            return choices[int(answer) - 1][1]
        if allow_keep and answer in {"4", "keep", "k"}:
            return current
        exact_index = "5" if allow_keep else "4"
        if answer in {exact_index, "exact", "e"}:
            exact = input("Version (MAJOR.MINOR.PATCH): ").strip()
            try:
                parse_semver(exact)
                return exact
            except ReleaseError as exc:
                print(exc)
                continue
        print("Choose major, minor, patch" + (", keep" if allow_keep else "") + ", or exact.")


def choose_package_bump(component: Component, baseline_tag: str) -> str:
    print(f"\n{component.name} changed since {baseline_tag}.")
    choices = ("major", "minor", "patch")
    for index, level in enumerate(choices, start=1):
        print(f"  {index}. {level:<5} -> {bump_version(component.version, level)}")
    while True:
        answer = input("Choose: ").strip().lower()
        aliases = {"major": "1", "minor": "2", "patch": "3"}
        answer = aliases.get(answer, answer)
        if answer in {"1", "2", "3"}:
            return bump_version(component.version, choices[int(answer) - 1])
        print("Choose major, minor, or patch.")


def show_status() -> None:
    refresh_tags()
    app_name, app_version = read_project(ROOT / "pyproject.toml")
    app_release_tag = latest_tag("v")
    print(f"{app_name}: {app_version} (latest tag: {app_release_tag or 'none'})")

    for component in discover_components():
        prefix = f"{component.tag_prefix}-v"
        tag = latest_tag(prefix)
        if tag is None:
            state = "no baseline tag"
        else:
            state = "changed" if path_changed_since(tag, component.path) else "unchanged"
        print(
            f"{component.name}: {component.version} "
            f"(latest tag: {tag or 'none'}, {state})"
        )


def apply_component_version(component: Component, version: str) -> list[Path]:
    changed: list[Path] = []
    manifest_text = component.manifest.read_text(encoding="utf-8")
    updated_manifest = replace_project_version(manifest_text, version)
    if updated_manifest != manifest_text:
        component.manifest.write_text(updated_manifest, encoding="utf-8")
        changed.append(component.manifest)

    for module_file in module_version_files(component):
        original = module_file.read_text(encoding="utf-8")
        updated = replace_module_version(original, version)
        if updated != original:
            module_file.write_text(updated, encoding="utf-8")
            changed.append(module_file)
    return changed


def validate_new_app_version(version: str) -> None:
    parse_semver(version)
    previous = latest_tag_version("v")
    if previous is not None and parse_semver(version) <= parse_semver(previous):
        raise ReleaseError(
            f"WireLoft {version} must be newer than the latest release tag v{previous}."
        )


def prepare_release(args: argparse.Namespace) -> None:
    ensure_clean_worktree()
    refresh_tags()
    if shutil.which("uv") is None and not args.dry_run:
        raise ReleaseError("uv is required so release preparation can refresh uv.lock safely.")

    app_manifest = ROOT / "pyproject.toml"
    app_name, current_app_version = read_project(app_manifest)
    if args.app_version:
        new_app_version = args.app_version
    elif args.app_bump:
        new_app_version = bump_version(current_app_version, args.app_bump)
    else:
        new_app_version = choose_version(app_name, current_app_version, allow_keep=False)
    validate_new_app_version(new_app_version)

    package_versions: dict[str, str] = {}
    for component in discover_components():
        prefix = f"{component.tag_prefix}-v"
        tag = latest_tag(prefix)
        if tag is None:
            print(
                f"{component.name}: no baseline tag yet; keeping {component.version} "
                f"and publishing {component.tag} with this release."
            )
            package_versions[component.name] = component.version
            continue
        if not path_changed_since(tag, component.path):
            print(f"{component.name}: unchanged since {tag}; no version bump needed.")
            package_versions[component.name] = component.version
            continue
        package_versions[component.name] = choose_package_bump(component, tag)

    print("\nRelease plan")
    print(f"  WireLoft: {current_app_version} -> {new_app_version}")
    components = {component.name: component for component in discover_components()}
    for name, version in package_versions.items():
        component = components[name]
        if version != component.version:
            print(f"  {name}: {component.version} -> {version}")
        else:
            print(f"  {name}: {component.version} (unchanged)")

    if args.dry_run:
        return

    tracked_paths = [app_manifest, ROOT / "uv.lock"]
    tracked_paths.extend(component.manifest for component in components.values())
    for component in components.values():
        tracked_paths.extend(module_version_files(component))
    originals = {path: path.read_bytes() for path in tracked_paths if path.exists()}

    try:
        app_text = app_manifest.read_text(encoding="utf-8")
        app_manifest.write_text(
            replace_project_version(app_text, new_app_version),
            encoding="utf-8",
        )
        for name, version in package_versions.items():
            component = components[name]
            if version != component.version:
                apply_component_version(component, version)
        run("uv", "lock", capture_output=False)
    except Exception:
        for path, content in originals.items():
            path.write_bytes(content)
        raise

    print("\nRelease versions prepared. Review the diff, run the test suite, commit, and merge it before publishing tags.")
    run("git", "diff", "--stat", capture_output=False)


def tag_exists(tag: str) -> bool:
    return bool(git("tag", "--list", tag))


def container_tags(version: str) -> list[str]:
    major, minor, _patch = parse_semver(version)
    return [version, f"{major}.{minor}", str(major), "latest"]


def verify_publish_state() -> None:
    ensure_clean_worktree()
    branch = git("branch", "--show-current")
    if branch != "main":
        raise ReleaseError(f"Publish releases only from main; current branch is '{branch or 'detached HEAD'}'.")
    run("git", "fetch", "origin", "main", "--tags", capture_output=False)
    if git("rev-parse", "HEAD") != git("rev-parse", "origin/main"):
        raise ReleaseError("Local main must exactly match origin/main before publishing a release.")


def tags_to_publish() -> list[str]:
    _app_name, app_version = read_project(ROOT / "pyproject.toml")
    validate_new_app_version(app_version)

    tags: list[str] = []
    for component in discover_components():
        prefix = f"{component.tag_prefix}-v"
        previous_tag = latest_tag(prefix)
        target_tag = component.tag
        if previous_tag is None:
            if not tag_exists(target_tag):
                tags.append(target_tag)
            continue
        if path_changed_since(previous_tag, component.path):
            previous_version = previous_tag.removeprefix(prefix)
            if parse_semver(component.version) <= parse_semver(previous_version):
                raise ReleaseError(
                    f"{component.name} changed since {previous_tag}, but its version is still "
                    f"{component.version}. Run release.py prepare and choose a version bump."
                )
            if tag_exists(target_tag):
                raise ReleaseError(f"Tag {target_tag} already exists.")
            tags.append(target_tag)

    app_release_tag = f"v{app_version}"
    if tag_exists(app_release_tag):
        raise ReleaseError(f"Tag {app_release_tag} already exists.")
    tags.append(app_release_tag)
    return tags


def publish_release(args: argparse.Namespace) -> None:
    verify_publish_state()
    _app_name, app_version = read_project(ROOT / "pyproject.toml")
    tags = tags_to_publish()
    image_tags = container_tags(app_version)

    print("Git tags to publish:")
    for tag in tags:
        print(f"  {tag}")
    if not args.skip_container:
        print("GHCR image tags to publish:")
        for tag in image_tags:
            print(f"  ghcr.io/samuelvisser/wireloft:{tag}")

    if not args.yes:
        answer = input("Publish this release? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Release publishing cancelled.")
            return

    if not args.skip_container:
        run("./deploy.sh", *image_tags, capture_output=False)

    created: list[str] = []
    try:
        for tag in tags:
            message = f"WireLoft {tag.removeprefix('v')}" if tag.startswith("v") else f"Release {tag}"
            run("git", "tag", "-a", tag, "-m", message, capture_output=False)
            created.append(tag)
        run("git", "push", "--atomic", "origin", *tags, capture_output=False)
    except Exception:
        for tag in created:
            run("git", "tag", "-d", tag, check=False, capture_output=False)
        raise

    print(
        f"Published {len(tags)} Git tag(s). "
        "The v* application tag will trigger the GitHub Release workflow."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare and publish WireLoft application and workspace package releases."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Show application/package versions and changed-package state.")

    prepare = subparsers.add_parser("prepare", help="Prompt for release versions and update manifests.")
    prepare.add_argument("--app-version", help="Set an exact WireLoft MAJOR.MINOR.PATCH version.")
    prepare.add_argument("--app-bump", choices=("major", "minor", "patch"))
    prepare.add_argument("--dry-run", action="store_true", help="Show the release plan without writing files.")

    publish = subparsers.add_parser(
        "publish",
        help="Publish the GHCR image, create package/app tags, and push them from main.",
    )
    publish.add_argument(
        "--skip-container",
        action="store_true",
        help="Do not build/push the versioned and latest GHCR image tags.",
    )
    publish.add_argument("--yes", action="store_true", help="Skip the final publish confirmation.")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        ensure_git_repository()
        if args.command == "status":
            show_status()
        elif args.command == "prepare":
            prepare_release(args)
        elif args.command == "publish":
            publish_release(args)
        else:
            parser.error(f"Unknown command {args.command}")
    except (ReleaseError, OSError, tomllib.TOMLDecodeError) as exc:
        print(f"release: error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
