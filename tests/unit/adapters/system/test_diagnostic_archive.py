"""The security test: nothing forbidden survives into a real archive."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

from inductor_designer.adapters.system.diagnostic_archive import (
    collect_bundle_sources,
    write_diagnostic_archive,
)
from inductor_designer.application.services.diagnostic_bundle import (
    BUNDLE_CONTENTS_FILENAME,
    BundleSource,
    build_bundle_entries,
)
from inductor_designer.application.services.redaction import RedactionContext

# Written independently of the production patterns on purpose: this list is the
# requirement, not a restatement of the implementation.
FORBIDDEN = (
    re.compile(r"[A-Za-z]:[\\/]"),
    re.compile(r"\\\\[A-Za-z0-9]"),
    re.compile(r"/home/"),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"\b\d{1,5}@[A-Za-z0-9]"),
    re.compile(r"jane\.doe", re.IGNORECASE),
    re.compile(r"BRUSA-WS42", re.IGNORECASE),
    re.compile(r"BRUSA-FS01", re.IGNORECASE),
    re.compile(r"LICSRV01", re.IGNORECASE),
)

CONTEXT = RedactionContext(
    user_names=("jane.doe",), host_names=("BRUSA-WS42", "BRUSA-FS01")
)


def _seed(tmp_path: Path) -> tuple[Path, Path]:
    document = tmp_path / "project" / "boost.inductor.json"
    document.parent.mkdir(parents=True)
    document.write_text("{}", encoding="utf-8")
    run = document.parent / "runs" / "20260818-101500-maxwell-3d" / "results"
    run.mkdir(parents=True)
    (run.parent / "run-manifest.json").write_text(
        json.dumps(
            {
                "runId": "20260818-101500",
                "status": "failed",
                "diagnostics": [
                    r"Engine Detected Error: cannot open C:\Users\jane.doe\m.adp",
                    "licence checkout failed on 1055@LICSRV01",
                ],
                "artifacts": [{"kind": "aedt-project", "path": "runs/x/m.aedt"}],
            }
        ),
        encoding="utf-8",
    )
    (run / "solve-log.txt").write_text(
        "launch\tfailed\t" + r"\\BRUSA-FS01\share\m.aedt" + "\n", encoding="utf-8"
    )
    (run / "results.json").write_text('{"runId": "20260818-101500"}', encoding="utf-8")
    log_directory = tmp_path / "logs"
    log_directory.mkdir()
    log_path = log_directory / "inductor-designer.log"
    log_path.write_text(
        "2026-08-18\tWARNING\tinductor_designer\tmail jane.doe@brusa.biz on BRUSA-WS42\n",
        encoding="utf-8",
    )
    return document, log_path


def test_collect_reads_the_log_the_manifests_and_the_result_files(
    tmp_path: Path,
) -> None:
    document, log_path = _seed(tmp_path)

    names = [source.name for source in collect_bundle_sources(document, log_path)]

    assert any(name.endswith("inductor-designer.log") for name in names)
    assert any(name.endswith("run-manifest.json") for name in names)
    assert any(name.endswith("solve-log.txt") for name in names)


def test_the_project_document_never_becomes_an_entry(tmp_path: Path) -> None:
    """The document locates the runs directory; it is not itself collected.

    Ruled 2026-08-18. The parameter is a document path, so the cheapest wrong
    change in this file is to read it -- which would put user-authored text into a
    bundle built to be shareable. This test is the guard on that decision.
    """
    document, _ = _seed(tmp_path)
    document.write_text(
        '{"name": "a customer name no redactor can classify"}', encoding="utf-8"
    )

    sources = collect_bundle_sources(document, None)

    assert sources  # the runs beside it were still found
    assert all(document.name not in source.name for source in sources)
    assert all("no redactor can classify" not in source.text for source in sources)
    assert any(source.name.endswith("results.json") for source in sources)


def test_the_project_document_is_not_collected(tmp_path: Path) -> None:
    document, log_path = _seed(tmp_path)

    names = [source.name for source in collect_bundle_sources(document, log_path)]

    assert not any(name.endswith("boost.inductor.json") for name in names)


def test_the_written_archive_carries_nothing_forbidden(tmp_path: Path) -> None:
    document, log_path = _seed(tmp_path)
    entries = build_bundle_entries(
        collect_bundle_sources(document, log_path),
        CONTEXT,
        application_version="0.9.0",
        created_utc="2026-08-18T12:00:00+00:00",
    )

    archive_path = write_diagnostic_archive(
        tmp_path / "out.diagnostics.zip", entries
    )

    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        assert names
        for name in names:
            payload = archive.read(name).decode("utf-8")
            for pattern in FORBIDDEN:
                assert pattern.search(name) is None, (pattern.pattern, name)
                assert pattern.search(payload) is None, (pattern.pattern, name)


def test_the_archive_still_carries_the_diagnosable_extension(tmp_path: Path) -> None:
    document, log_path = _seed(tmp_path)
    entries = build_bundle_entries(
        collect_bundle_sources(document, log_path),
        CONTEXT,
        application_version="0.9.0",
        created_utc="2026-08-18T12:00:00+00:00",
    )

    archive_path = write_diagnostic_archive(tmp_path / "o.diagnostics.zip", entries)

    with zipfile.ZipFile(archive_path) as archive:
        payload = "".join(
            archive.read(name).decode("utf-8") for name in archive.namelist()
        )
    assert "].adp" in payload
    assert "Engine Detected Error" in payload


def test_missing_sources_produce_an_archive_rather_than_an_error(
    tmp_path: Path,
) -> None:
    entries = build_bundle_entries(
        collect_bundle_sources(None, None),
        CONTEXT,
        application_version="0.9.0",
        created_utc="2026-08-18T12:00:00+00:00",
    )

    archive_path = write_diagnostic_archive(tmp_path / "e.diagnostics.zip", entries)

    with zipfile.ZipFile(archive_path) as archive:
        assert archive.namelist() == ["bundle-contents.json"]


def test_a_run_directory_with_aedt_files_contributes_only_our_own_evidence(
    tmp_path: Path,
) -> None:
    """AEDT's own project/results/log files must never ride along.

    A run directory routinely holds the `.aedt` project AEDT wrote, a FEMM
    `.fem` file, and AEDT's own `batch.log` -- none of them ours to redact.
    Only our manifest and our result files may become sources.
    """
    document = tmp_path / "project" / "coil.inductor.json"
    document.parent.mkdir(parents=True)
    document.write_text("{}", encoding="utf-8")
    run_directory = document.parent / "runs" / "20260818-120000-maxwell-3d"
    results = run_directory / "results"
    results.mkdir(parents=True)
    (run_directory / "run-manifest.json").write_text("{}", encoding="utf-8")
    (run_directory / "model.aedt").write_text("aedt binary stand-in", encoding="utf-8")
    (run_directory / "coil.fem").write_text("femm stand-in", encoding="utf-8")
    (run_directory / "batch.log").write_text(
        "CH01NB296.brusa.biz_9996.pjt opened by jane.doe\n", encoding="utf-8"
    )
    (results / "results.json").write_text("{}", encoding="utf-8")

    names = [
        source.name for source in collect_bundle_sources(document, None)
    ]

    assert any(name.endswith("run-manifest.json") for name in names)
    assert any(name.endswith("results.json") for name in names)
    assert not any(name.endswith(".aedt") for name in names)
    assert not any(name.endswith(".fem") for name in names)
    assert not any(name.endswith("batch.log") for name in names)


def test_a_redacted_entry_name_does_not_reappear_in_clear_text_in_the_index() -> None:
    """The index lists entry names -- which must be the redacted ones."""
    entries = {
        entry.name: entry.text
        for entry in build_bundle_entries(
            (BundleSource(name="logs/jane.doe.log", text="ok"),),
            CONTEXT,
            application_version="0.9.0",
            created_utc="2026-08-18T12:00:00+00:00",
        )
    }

    assert "jane.doe" not in entries[BUNDLE_CONTENTS_FILENAME]
