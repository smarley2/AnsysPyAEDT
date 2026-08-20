"""Build the shareable contents of a diagnostic bundle.

This is the second and last place that redacts (the first is the application
log formatter). Every entry's text *and* name passes through `redact_text` in
one loop, so an added source cannot skip redaction by accident, and the archive
writer accepts only what this function produced.

The project document is deliberately not a source: it carries a user-authored
project name and description, and diagnosis does not need them.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

from inductor_designer.application.services.redaction import (
    REDACTED_EMAIL,
    REDACTED_HOST,
    REDACTED_LICENSE_SERVER,
    REDACTED_PATH,
    REDACTED_USER,
    RedactionContext,
    redact_text,
)

BUNDLE_CONTENTS_FILENAME = "bundle-contents.json"


@dataclass(frozen=True, slots=True)
class BundleSource:
    """One file read from disk, before redaction."""

    name: str
    text: str


@dataclass(frozen=True, slots=True)
class BundleEntry:
    """One redacted member of the archive."""

    name: str
    text: str


def _unique(name: str, taken: set[str]) -> str:
    """Redaction can collapse two distinct paths onto one name."""
    if name not in taken:
        return name
    for index in range(2, 1000):
        candidate = f"{name}.{index}"
        if candidate not in taken:
            return candidate
    raise ValueError(f"Too many bundle entries collide on {name!r}.")


def build_bundle_entries(
    sources: Sequence[BundleSource],
    context: RedactionContext,
    *,
    application_version: str,
    created_utc: str,
) -> tuple[BundleEntry, ...]:
    """Redacted entries, with a contents index first."""
    entries: list[BundleEntry] = []
    taken: set[str] = set()
    for source in sources:
        name = _unique(redact_text(source.name, context), taken)
        taken.add(name)
        entries.append(BundleEntry(name=name, text=redact_text(source.text, context)))
    index = json.dumps(
        {
            "applicationVersion": application_version,
            "createdUtc": created_utc,
            "entries": [entry.name for entry in entries],
            "redaction": {
                "applied": True,
                "markers": [
                    REDACTED_EMAIL,
                    REDACTED_HOST,
                    REDACTED_LICENSE_SERVER,
                    REDACTED_PATH,
                    REDACTED_USER,
                ],
                "removed": [
                    "absolute filesystem paths",
                    "machine names",
                    "licence server identifiers",
                    "user names",
                    "e-mail addresses",
                ],
                # A support engineer must be able to tell a deliberately narrow
                # bundle from a broken one, and a user must be able to see what to
                # attach by hand if they judge it safe. Silence about an exclusion
                # reads as a missing file.
                "excluded": {
                    "project document": (
                        "User-authored text -- project name, description, "
                        "winding labels, terminal intent -- cannot be "
                        "classified by any redaction rule. Every physical "
                        "input is in the run manifests instead. Attach the "
                        ".inductor.json yourself if you judge it safe to "
                        "share."
                    ),
                    "AEDT log files": (
                        "Written by AEDT in a format this application does "
                        "not control, so their redaction cannot be proven. "
                        "The desktop messages captured during a failed run "
                        "are in the application log instead."
                    ),
                },
            },
        },
        indent=2,
        sort_keys=True,
    )
    return (
        # The index is redacted like everything else: an entry name that needed
        # redaction must not reappear in clear text here.
        BundleEntry(name=BUNDLE_CONTENTS_FILENAME, text=redact_text(index, context)),
        *entries,
    )
