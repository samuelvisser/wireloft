from __future__ import annotations

import ast
from pathlib import Path


def test_task_manager_does_not_depend_on_backend_api_layer():
    repo_root = Path(__file__).resolve().parents[2]
    task_manager = repo_root / "server" / "task_manager" / "src" / "task_manager"
    violations: list[str] = []

    for path in task_manager.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "backend.api" or module.startswith("backend.api."):
                    violations.append(
                        f"{path.relative_to(repo_root)}:{node.lineno} imports {module}"
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "backend.api" or alias.name.startswith("backend.api."):
                        violations.append(
                            f"{path.relative_to(repo_root)}:{node.lineno} imports {alias.name}"
                        )

    assert violations == []
