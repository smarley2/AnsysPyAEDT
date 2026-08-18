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


def test_drive_letter_path_with_space_in_directory_name_is_fully_redacted() -> None:
    """A space inside a directory name must not end the path match: the first
    attempt stopped at the space and published the surname in "Jane Doe".
    """
    text = r"C:\Users\Jane Doe\Documents\notes.txt"
    redacted = redact_text(text, CONTEXT)
    assert redacted == f"{REDACTED_PATH}.txt"


def test_unc_path_with_space_in_directory_name_is_fully_redacted() -> None:
    """Same early-stop defect on the UNC branch: a share path with a spacey
    directory left everything after the space, host included, in the output.
    """
    text = r"\\brusa-fs01\share\sub dir\file.txt"
    redacted = redact_text(text, CONTEXT)
    assert redacted == f"{REDACTED_PATH}.txt"


def test_bare_unc_host_without_share_is_redacted() -> None:
    r"""The UNC pattern once required a share segment, so a bare "\\HOST" -- a
    machine name on its own -- was never matched and passed through intact.
    """
    redacted = redact_text(r"\\BRUSA-FS01", CONTEXT)
    assert redacted == REDACTED_PATH


def test_license_server_with_domain_is_labelled_as_license_server_not_email() -> None:
    """A fully qualified "port@host" also matches the e-mail shape; when e-mail
    ran first it mislabelled a licence identifier as an address.
    """
    redacted = redact_text("checkout failed on 1055@licsrv01.brusa.biz", CONTEXT)
    assert redacted == f"checkout failed on {REDACTED_LICENSE_SERVER}"


def test_user_token_matching_inside_a_marker_word_does_not_corrupt_output() -> None:
    """A user token that is merely a substring of a marker (here "cted" inside
    "[redacted-path]") once re-redacted the marker just produced.
    """
    context = RedactionContext(user_names=("cted",))
    redacted = redact_text(r"C:\tmp\a.adp", context)
    assert redacted == f"{REDACTED_PATH}.adp"


def test_closing_punctuation_after_a_path_without_extension_is_preserved() -> None:
    """Trailing punctuation trimmed off a path match for extension detection was
    discarded rather than reattached, silently dropping the closing bracket.
    """
    redacted = redact_text(r"see (C:\temp\dump)", CONTEXT)
    assert redacted == f"see ({REDACTED_PATH})"


def test_longest_host_token_is_matched_before_its_shorter_prefix() -> None:
    """Matching a short host token before its fully qualified form leaves the
    domain suffix behind, which still identifies the machine.
    """
    redacted = redact_text("session on brusa-ws42.brusa.biz started", CONTEXT)
    assert redacted == f"session on {REDACTED_HOST} started"


def test_dotted_user_name_as_final_segment_keeps_no_extension() -> None:
    """The extension guess read "jane.doe" as name-plus-extension and published
    "[redacted-path].doe", leaking the surname it exists to remove.
    """
    redacted = redact_text(r"home dir C:\Users\jane.doe", CONTEXT)
    assert redacted == f"home dir {REDACTED_PATH}"


def test_dotted_user_name_in_posix_home_keeps_no_extension() -> None:
    """Same leak through the POSIX branch: "/home/jane.doe" became
    "[redacted-path].doe".
    """
    redacted = redact_text("wrote /home/m.signer", CONTEXT)
    assert redacted == f"wrote {REDACTED_PATH}"


def test_prose_after_an_extensionless_path_is_not_swallowed() -> None:
    """With no extension to find, the path match ran to the end of the line and
    deleted the sentence that followed it.
    """
    redacted = redact_text(r"D:\work\projects\boost done, moving on", CONTEXT)
    assert redacted == f"{REDACTED_PATH} done, moving on"


def test_prose_after_a_bare_unc_host_is_not_swallowed() -> None:
    """The bare-host branch had no end boundary at all, so "\\HOST is down"
    lost the diagnosis and kept only the marker.
    """
    redacted = redact_text(r"host \\BRUSA-FS01 is down, escalate now", CONTEXT)
    assert redacted == f"host {REDACTED_PATH} is down, escalate now"


def test_allowlisted_extension_survives_a_path_with_spaces() -> None:
    """The diagnostic value of a path is its file type, so a real technical
    extension must still be reported once the path itself is gone.
    """
    redacted = redact_text(r"missing C:\Program Files\ANSYS Inc\v252\Setup1.adp", CONTEXT)
    assert redacted == f"missing {REDACTED_PATH}.adp"


def test_suffix_outside_the_allowlist_is_redacted_with_the_path() -> None:
    """Only extensions this application and its solvers produce are kept; any
    other trailing suffix could be a personal name and goes with the path.
    """
    redacted = redact_text(r"C:\Users\jane.doe\report.docx", CONTEXT)
    assert redacted == REDACTED_PATH
