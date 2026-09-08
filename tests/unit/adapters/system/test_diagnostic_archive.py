"""The security test: nothing forbidden survives into a real archive."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

import pytest

from inductor_designer.adapters.system.diagnostic_archive import (
    _MAX_SOURCE_BYTES,
    collect_bundle_sources,
    write_diagnostic_archive,
)
from inductor_designer.application.services.diagnostic_bundle import (
    BUNDLE_CONTENTS_FILENAME,
    BundleEntry,
    BundleSource,
    build_bundle_entries,
)
from inductor_designer.application.services.redaction import RedactionContext

# Written independently of the production patterns on purpose: this list is the
# requirement, not a restatement of the implementation.
# NOTE: the drive-letter pattern below also matches the "e:/" inside a
# "file:///[redacted-path].aedt" entry. A fixture that plants a real file://
# URL would fail this pattern spuriously -- that is a limitation of this
# test's own forbidden-list, not of production redaction.
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


def _filler(length: int) -> str:
    """`length` characters of harmless padding for a truncation fixture.

    Not a solid run of letters: `_EMAIL`'s unbounded `[A-Za-z0-9._%+-]+`
    local-part backtracks quadratically over a long run with no "@" to find,
    turning a single `redact_text` call on a ~512 kB solid-letter tail into a
    multi-minute hang. A newline every other character keeps every attempt
    O(1), which is also what real log padding looks like.
    """
    return ("y\n" * (length // 2 + 1))[:length]


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
        "WS0417.example.invalid_9996.pjt opened by jane.doe\n", encoding="utf-8"
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


def test_rotated_logs_are_collected_alongside_the_current_one(tmp_path: Path) -> None:
    """`app_logging` rotates the log; a bundle from a machine that has been in
    use must carry the rotated files too, not only `log_path` itself.
    """
    log_directory = tmp_path / "logs"
    log_directory.mkdir()
    log_path = log_directory / "inductor-designer.log"
    log_path.write_text("current\n", encoding="utf-8")
    (log_directory / "inductor-designer.log.1").write_text(
        "rotated\n", encoding="utf-8"
    )

    names = [source.name for source in collect_bundle_sources(None, log_path)]

    assert any(name.endswith("inductor-designer.log") for name in names)
    assert any(name.endswith("inductor-designer.log.1") for name in names)


def test_a_raw_slice_through_a_drive_letter_path_does_not_strand_the_remainder(
    tmp_path: Path,
) -> None:
    """A source bigger than `_MAX_SOURCE_BYTES` must not have its tail cut
    through the middle of a path: that strips the "C:\\" anchor the
    drive-path rule needs, and the customer directory name that follows is
    unknown to any redaction token -- only the anchored rule can catch it.
    """
    customer = "CustomerACME"
    path = rf"C:\Users\hans.mueller\Projects\{customer}\coil.aedt"
    line = f"solve failed: {path}\n"
    # Strand everything one character past the drive letter "C", i.e. the
    # raw tail begins with ":\Users\..." -- the anchor is gone.
    cut_point = line.index(path) + 1
    trailer = _filler(_MAX_SOURCE_BYTES + cut_point - len(line))
    log_path = tmp_path / "logs" / "inductor-designer.log"
    log_path.parent.mkdir()
    log_path.write_text(line + trailer, encoding="utf-8")

    sources = collect_bundle_sources(None, log_path)
    entries = {
        entry.name: entry.text
        for entry in build_bundle_entries(
            sources,
            CONTEXT,
            application_version="0.9.0",
            created_utc="2026-08-18T12:00:00+00:00",
        )
    }

    payload = entries["logs/inductor-designer.log"]
    # Collected into a list rather than asserted with `not in`: pytest rewrites
    # a failing `in` over a 512 kB string into a difflib diff, which took over
    # ten minutes and printed nothing. A regression here would have looked like
    # a hung CI job instead of a failed security test.
    assert [token for token in (customer, "hans.mueller") if token in payload] == []


def test_a_raw_slice_through_a_unc_opener_does_not_strand_the_file_server(
    tmp_path: Path,
) -> None:
    """A file-server name is never in `RedactionContext` -- only the UNC
    opener `\\\\host` can catch it. A raw slice that strips the opener down
    to a single backslash (below the two the UNC rule requires) must not
    leave the host and the customer directory it shares in clear text.
    """
    # No file server in this context on purpose: it never would be, in a
    # real `RedactionContext`, which holds only the local machine.
    no_server_context = RedactionContext(
        user_names=("jane.doe",), host_names=("BRUSA-WS42",)
    )
    customer = "CustomerACME"
    unc = f"\\\\BRUSA-FS01\\share\\{customer}\\coil.aedt"
    # The doubled-backslash form a JSON-escaped manifest carries.
    json_form = unc.replace("\\", "\\\\")
    line = f'"diagnostics": ["cannot reach {json_form}"]\n'
    # Strip 3 of the opener's 4 backslashes, leaving 1 -- below the `\\{2,4}`
    # the UNC rule requires.
    cut_point = line.index(json_form) + 3
    trailer = _filler(_MAX_SOURCE_BYTES + cut_point - len(line))
    log_path = tmp_path / "logs" / "inductor-designer.log"
    log_path.parent.mkdir()
    log_path.write_text(line + trailer, encoding="utf-8")

    sources = collect_bundle_sources(None, log_path)
    entries = {
        entry.name: entry.text
        for entry in build_bundle_entries(
            sources,
            no_server_context,
            application_version="0.9.0",
            created_utc="2026-08-18T12:00:00+00:00",
        )
    }

    payload = entries["logs/inductor-designer.log"]
    assert [token for token in ("BRUSA-FS01", customer) if token in payload] == []


def test_write_diagnostic_archive_rejects_zip_slip_member_names(
    tmp_path: Path,
) -> None:
    """Nothing upstream actually enforces "one of our own entry names" --
    it is convention. An absolute name or a `..` segment would otherwise be
    written verbatim, a zip-slip onto the support engineer's machine when
    they extract the bundle.
    """
    with pytest.raises(ValueError):
        write_diagnostic_archive(
            tmp_path / "evil.zip",
            (BundleEntry(name="../../evil.txt", text="x"),),
        )
    with pytest.raises(ValueError):
        write_diagnostic_archive(
            tmp_path / "evil2.zip",
            (BundleEntry(name="/etc/passwd", text="x"),),
        )
    # The Windows shapes, which the first version of this guard accepted:
    # `ZipInfo` rewrites os.sep to "/" AFTER the check, so a backslash name
    # was checked as one thing and STORED as the very name being rejected. A
    # drive letter survived as `C:/Windows/...`, and a NUL was silently
    # truncated, so the archive held a member the contents index did not name.
    for name in (
        "..\\..\\evil.txt",
        "C:\\Windows\\evil.txt",
        "C:/Windows/evil.txt",
        "\\\\HOST\\share\\evil.txt",
        "evil\x00",
    ):
        with pytest.raises(ValueError):
            write_diagnostic_archive(
                tmp_path / "evil-windows.zip", (BundleEntry(name=name, text="x"),)
            )
