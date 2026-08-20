"""Every byte and every name in a bundle passes through redaction, in one loop."""

from __future__ import annotations

import json

from inductor_designer.application.services.diagnostic_bundle import (
    BUNDLE_CONTENTS_FILENAME,
    BundleSource,
    build_bundle_entries,
)
from inductor_designer.application.services.redaction import (
    REDACTED_PATH,
    RedactionContext,
)

CONTEXT = RedactionContext(user_names=("jane.doe",), host_names=("BRUSA-WS42",))


def _entries(*sources: BundleSource) -> dict[str, str]:
    built = build_bundle_entries(
        sources,
        CONTEXT,
        application_version="0.9.0",
        created_utc="2026-08-18T12:00:00+00:00",
    )
    return {entry.name: entry.text for entry in built}


def test_entry_text_is_redacted() -> None:
    entries = _entries(
        BundleSource(name="logs/app.log", text=r"saved C:\Users\jane.doe\b.aedt")
    )
    assert "jane.doe" not in entries["logs/app.log"]
    assert f"{REDACTED_PATH}.aedt" in entries["logs/app.log"]


def test_entry_name_is_redacted_too() -> None:
    entries = _entries(BundleSource(name="runs/jane.doe-run/x.json", text="ok"))
    assert not any("jane.doe" in name for name in entries)


def test_the_contents_index_lists_every_entry() -> None:
    entries = _entries(
        BundleSource(name="logs/app.log", text="a"),
        BundleSource(name="runs/r/run-manifest.json", text="b"),
    )
    index = json.loads(entries[BUNDLE_CONTENTS_FILENAME])
    assert index["applicationVersion"] == "0.9.0"
    assert index["createdUtc"] == "2026-08-18T12:00:00+00:00"
    assert "logs/app.log" in index["entries"]
    assert index["redaction"]["applied"] is True


def test_the_contents_index_is_itself_redacted() -> None:
    entries = _entries(BundleSource(name="notes.txt", text="jane.doe@brusa.biz"))
    assert "brusa.biz" not in entries[BUNDLE_CONTENTS_FILENAME]


def test_the_index_names_what_was_left_out_on_purpose() -> None:
    """A narrow bundle must not read as a broken one.

    Excluding the project document and AEDT's own logs is a decision, not an
    omission, and the person opening the archive cannot see the decision unless
    the index states it.
    """
    entries = _entries(BundleSource(name="logs/app.log", text="ok"))

    excluded = json.loads(entries[BUNDLE_CONTENTS_FILENAME])["redaction"]["excluded"]

    assert "project document" in excluded
    assert "AEDT log files" in excluded
    assert ".inductor.json" in excluded["project document"]


def test_no_sources_still_produces_the_contents_index() -> None:
    entries = _entries()
    assert list(entries) == [BUNDLE_CONTENTS_FILENAME]


def test_duplicate_names_after_redaction_stay_distinct() -> None:
    entries = _entries(
        BundleSource(name=r"C:\a\log.txt", text="one"),
        BundleSource(name=r"C:\b\log.txt", text="two"),
    )
    assert len(entries) == 3
