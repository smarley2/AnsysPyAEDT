from __future__ import annotations

from collections.abc import Iterable, Set


def ensure_complete_family_results(
    summaries: Iterable[dict[str, object]], *, required_codes: Set[str]
) -> None:
    """Fail closed when any required KDM family is absent, failed, or empty."""
    by_code = {str(entry.get("code")): entry for entry in summaries}
    failures: list[str] = []
    for code in sorted(required_codes):
        entry = by_code.get(code)
        if entry is None:
            failures.append(f"{code}: family result missing")
            continue
        records = entry.get("records")
        error = entry.get("error")
        if error:
            failures.append(f"{code}: {error}")
        elif not isinstance(records, int) or records <= 0:
            failures.append(f"{code}: zero records")
    if failures:
        raise RuntimeError("Incomplete KDM family import:\n" + "\n".join(failures))
