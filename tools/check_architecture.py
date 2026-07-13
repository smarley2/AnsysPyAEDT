from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

INNER_PACKAGES = frozenset({"domain", "geometry", "materials", "simulation"})
FORBIDDEN_ROOTS = frozenset({"ansys", "pyaedt", "PySide6", "sqlite3", "os", "platform"})


@dataclass(frozen=True, slots=True)
class Violation:
    path: Path
    line: int
    imported: str
    inner_package: str


def _imported_names(node: ast.Import | ast.ImportFrom) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)
    return (node.module or "",)


def find_forbidden_imports(source_root: Path) -> tuple[Violation, ...]:
    violations: list[Violation] = []
    package_root = source_root / "inductor_designer"
    for inner_package in sorted(INNER_PACKAGES):
        for path in sorted((package_root / inner_package).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Import, ast.ImportFrom)):
                    continue
                for imported in _imported_names(node):
                    if imported.split(".", maxsplit=1)[0] in FORBIDDEN_ROOTS:
                        violations.append(
                            Violation(path, node.lineno, imported, inner_package)
                        )
    return tuple(violations)


def main() -> int:
    violations = find_forbidden_imports(Path("src"))
    for item in violations:
        print(f"{item.path}:{item.line}: {item.inner_package} imports {item.imported}")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
