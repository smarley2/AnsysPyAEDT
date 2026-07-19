from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

FORBIDDEN_ROOTS = frozenset(
    {
        "PySide6",
        "ansys",
        "ctypes",
        "femm",
        "mcp",
        "multiprocessing",
        "os",
        "pathlib",
        "platform",
        "pyaedt",
        "resource",
        "shutil",
        "socket",
        "sqlite3",
        "subprocess",
        "tempfile",
        "winreg",
    }
)
# The application layer defines ports and services; it may pass pathlib/OS
# values through DTOs but must never import solver, UI, or persistence
# infrastructure directly (dependency inversion, spec section 4.4).
_APPLICATION_FORBIDDEN_ROOTS = frozenset({"PySide6", "ansys", "femm", "mcp", "pyaedt", "sqlite3"})
_APPLICATION_FORBIDDEN_PREFIXES = ("inductor_designer.adapters",)
PACKAGE_FORBIDDEN_ROOTS: dict[str, frozenset[str]] = {
    "application": _APPLICATION_FORBIDDEN_ROOTS,
    "domain": FORBIDDEN_ROOTS,
    "geometry": FORBIDDEN_ROOTS,
    "materials": FORBIDDEN_ROOTS,
    "simulation": FORBIDDEN_ROOTS,
}
INNER_PACKAGES = frozenset(PACKAGE_FORBIDDEN_ROOTS)


@dataclass(frozen=True, slots=True)
class Violation:
    path: Path
    line: int
    imported: str
    inner_package: str


def _imported_names(node: ast.Import | ast.ImportFrom) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)
    module = node.module or ""
    if module == "inductor_designer":
        return tuple(f"{module}.{alias.name}" for alias in node.names)
    return (module,)


def find_forbidden_imports(source_root: Path) -> tuple[Violation, ...]:
    violations: list[Violation] = []
    package_root = source_root / "inductor_designer"
    for inner_package in sorted(INNER_PACKAGES):
        forbidden = PACKAGE_FORBIDDEN_ROOTS[inner_package]
        for path in sorted((package_root / inner_package).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Import, ast.ImportFrom)):
                    continue
                for imported in _imported_names(node):
                    is_forbidden = imported.split(".", maxsplit=1)[0] in forbidden
                    if inner_package == "application":
                        is_forbidden = is_forbidden or imported.startswith(
                            _APPLICATION_FORBIDDEN_PREFIXES
                        )
                    if is_forbidden:
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
