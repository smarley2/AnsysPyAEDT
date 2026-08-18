# tests/unit/application/test_redaction.py
from __future__ import annotations

from inductor_designer.application.services.redaction import (
    REDACTED_EMAIL,
    REDACTED_HOST,
    REDACTED_LICENSE_SERVER,
    REDACTED_PATH,
    REDACTED_USER,
    RedactionContext,
    redact_text,
)

CONTEXT = RedactionContext(
    user_names=("jane.doe", "fpo01"), host_names=("BRUSA-WS42", "brusa-ws42.brusa.biz")
)


def test_drive_letter_path_keeps_only_its_extension() -> None:
    text = r"Engine Detected Error: C:\Users\jane.doe\runs\20260818-101500\model.adp not found"
    redacted = redact_text(text, CONTEXT)
    assert "jane.doe" not in redacted
    assert "C:" not in redacted
    assert f"{REDACTED_PATH}.adp" in redacted


def test_drive_letter_path_without_extension_is_removed_entirely() -> None:
    redacted = redact_text(r"run folder: D:\work\projects\boost", CONTEXT)
    assert redacted == f"run folder: {REDACTED_PATH}"


def test_unc_path_is_removed() -> None:
    redacted = redact_text(r"saved \\BRUSA-FS01\share\model.aedt", CONTEXT)
    assert "BRUSA-FS01" not in redacted
    assert f"{REDACTED_PATH}.aedt" in redacted


def test_posix_home_path_is_removed() -> None:
    redacted = redact_text("wrote /home/jane.doe/.local/share/app.log", CONTEXT)
    assert "jane.doe" not in redacted
    assert f"{REDACTED_PATH}.log" in redacted


def test_email_address_is_removed() -> None:
    redacted = redact_text("contact jane.doe@brusa.biz for the licence", CONTEXT)
    assert redacted == f"contact {REDACTED_EMAIL} for the licence"


def test_license_server_identifier_is_removed() -> None:
    redacted = redact_text("checkout failed on 1055@LICSRV01", CONTEXT)
    assert redacted == f"checkout failed on {REDACTED_LICENSE_SERVER}"


def test_host_and_user_names_are_removed_case_insensitively() -> None:
    redacted = redact_text("session on brusa-ws42 started by JANE.DOE", CONTEXT)
    assert REDACTED_HOST in redacted
    assert REDACTED_USER in redacted
    assert "ws42" not in redacted.casefold()


def test_redaction_is_idempotent() -> None:
    text = (
        r"C:\Users\jane.doe\model.aedt jane.doe@brusa.biz 1055@LICSRV01 BRUSA-WS42"
    )
    once = redact_text(text, CONTEXT)
    assert redact_text(once, CONTEXT) == once


def test_short_tokens_are_ignored_so_ordinary_text_survives() -> None:
    context = RedactionContext(user_names=("ab",), host_names=("x",))
    assert redact_text("a stable absolute value", context) == "a stable absolute value"


def test_a_token_that_collides_with_a_marker_word_is_ignored() -> None:
    context = RedactionContext(user_names=("path",))
    assert redact_text(r"C:\tmp\a.adp", context) == f"{REDACTED_PATH}.adp"


def test_text_with_nothing_to_redact_is_returned_unchanged() -> None:
    assert redact_text("analyze: succeeded", CONTEXT) == "analyze: succeeded"
