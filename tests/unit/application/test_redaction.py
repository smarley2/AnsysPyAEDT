from __future__ import annotations

import json

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


def test_two_windows_paths_on_one_line_keep_the_prose_between_them() -> None:
    r"""A colon allowed inside a path component let "dump and see D:" read as one
    interior segment, so both paths and the words between them became a single
    marker.
    """
    redacted = redact_text(r"copied C:\temp\dump and see D:\out\file.log", CONTEXT)
    assert redacted == f"copied {REDACTED_PATH} and see {REDACTED_PATH}.log"


def test_extension_allowlist_comparison_ignores_case() -> None:
    """AEDT writes upper-case names too; the allowlist is a set of lower-case
    extensions, so the compare has to fold the case or ".ADP" is thrown away.
    """
    assert redact_text(r"C:\runs\MODEL.ADP", CONTEXT) == f"{REDACTED_PATH}.ADP"


def test_windows_path_with_trailing_space_in_a_component_is_fully_redacted() -> None:
    r"""``Path("C:/Users/Jane Doe ")/"Documents"`` really produces this string, and
    requiring a non-space before every separator broke the segment chain there and
    published "Doe" plus the rest of the path.
    """
    redacted = redact_text(r"C:\Users\Jane Doe \Documents\notes.txt", CONTEXT)
    assert redacted == f"{REDACTED_PATH}.txt"


def test_forward_slash_unc_path_hides_the_file_server_name() -> None:
    """Manifest paths are written with ``Path.as_posix()``, so a share arrives as
    "//HOST/share/..."; the UNC rule matched only backslashes and the POSIX rule
    needs "/home/" or "/Users/", so the server name survived untouched.
    """
    redacted = redact_text("saved //BRUSA-FS01/share/model.aedt", CONTEXT)
    assert redacted == f"saved {REDACTED_PATH}.aedt"


def test_url_scheme_is_not_read_as_a_path() -> None:
    """The drive-letter rule fired on the "p:" of "https:", turning a support link
    into "http[redacted-path]/..." and destroying diagnostic text.
    """
    redacted = redact_text("see https://ansys.com/kb/12345", CONTEXT)
    assert redacted == "see https://ansys.com/kb/12345"


def test_file_url_keeps_its_scheme_and_still_loses_the_whole_path() -> None:
    """The third slash of "file:///" looked like the start of a UNC host, which
    consumed only the drive letter and left the directories -- a user name among
    them -- behind for no later rule to catch.
    """
    redacted = redact_text("wrote file:///D:/work/jane.doe/notes.txt", CONTEXT)
    assert redacted == f"wrote file:///{REDACTED_PATH}.txt"


def test_email_with_a_dotless_internal_domain_is_removed() -> None:
    """An internal address has no dotted TLD, and requiring one let the whole
    address through.
    """
    redacted = redact_text("owner jane.doe@brusa", CONTEXT)
    assert redacted == f"owner {REDACTED_EMAIL}"


def test_posix_path_with_trailing_space_in_a_component_is_fully_redacted() -> None:
    r"""Fix wave 4. The forward-slash branch forbade a trailing space before
    "/", so ``Path("C:/Users/Jane Doe ")/"Documents"`` -- which really does
    produce this POSIX-form string -- broke the segment chain at the space and
    published "Doe /Documents/notes.txt". `_PATH_SEGMENT` now tolerates a
    trailing space before either separator, matching the backslash form.
    """
    text = "C:/Users/Jane Doe /Documents/notes.txt"
    redacted = redact_text(text, CONTEXT)
    assert redacted == f"{REDACTED_PATH}.txt"
    assert "Doe" not in redacted


def test_two_posix_paths_on_one_line_merge_when_the_first_has_a_trailing_space() -> None:
    """Accepted trade, not a bug: an interior segment may contain a space, so
    two paths on one line merge into a single match whenever nothing between
    them ends a segment (only a colon does). The prose between them is lost.
    That is a loss of diagnostic text, not a leak -- the asymmetric rule this
    replaced bought anti-merge behaviour for one shape at the price of
    publishing a surname, which is the wrong trade. Do not "fix" this back into
    a leak; over-redaction is the correct direction. This test pins the exact
    merged output so a future change to the pattern has to consciously decide
    to alter it.
    """
    text = (
        "wrote /home/jane.doe/Jane Doe /notes.txt and see /home/other/report.log"
    )
    redacted = redact_text(text, CONTEXT)
    assert redacted == f"wrote {REDACTED_PATH}.log"


def test_json_escaped_drive_path_is_fully_redacted() -> None:
    r"""Fix wave 5. ``json.dumps`` doubles every backslash, and `run-manifest.json`
    puts AEDT free text through it, so this is the shape the bundle really
    carries. A segment could not cross the second backslash of a doubled pair,
    so the match stopped after the drive and published the surname:
    "C:[redacted-path]\Jane Doe[redacted-path].aedt".
    """
    text = json.dumps({"p": r"C:\Users\Jane Doe\model.aedt"})
    redacted = redact_text(text, CONTEXT)
    assert redacted == '{"p": "' + REDACTED_PATH + '.aedt"}'


def test_json_escaped_unc_path_is_fully_redacted_and_idempotent() -> None:
    r"""Same defect on the UNC branch, and worse: every doubled pair read as a
    fresh UNC opener, so the first pass left "\\[redacted-path]\share..." and a
    second pass produced a different string again -- redaction was not
    idempotent for the one shape the bundle writes most.
    """
    text = json.dumps({"p": r"\\FS01\share\Jane Doe\model.aedt"})
    once = redact_text(text, CONTEXT)
    assert once == '{"p": "' + REDACTED_PATH + '.aedt"}'
    assert redact_text(once, CONTEXT) == once


def test_json_escaped_paths_in_a_run_manifest_diagnostic_are_redacted() -> None:
    """End-to-end shape check on the actual writer's output: `diagnostics` and
    `stages[].diagnostic` are free text holding AEDT engine errors, and
    `run_manifest_json` serialises them with ``json.dumps``.
    """
    text = json.dumps(
        {
            "diagnostics": [r"Engine Detected Error: C:\Users\Jane Doe\runs\m.adp"],
            "stages": [{"diagnostic": r"see \\FS01\share\Jane Doe\solve.log"}],
        }
    )
    redacted = redact_text(text, CONTEXT)
    assert "Jane" not in redacted
    assert "Doe" not in redacted
    assert "FS01" not in redacted
    assert f"{REDACTED_PATH}.adp" in redacted
    assert f"{REDACTED_PATH}.log" in redacted


def test_second_unc_server_name_on_a_line_is_not_stranded() -> None:
    r"""An interior segment may contain a space, so "f.log b " plus the FIRST
    backslash of "\\FS02" was consumed as one segment and the surviving lone
    backslash then matched nothing: the match ended there and FS02 was published
    intact. Reading a separator run as one separator removes the leak; the two
    raw paths now merge, which loses the prose but never the server name.
    """
    for first, second in ((r"\\", r"\\"), ("//", "//"), ("//", r"\\"), (r"\\", "//")):
        first_sep = "\\" if first == r"\\" else "/"
        second_sep = "\\" if second == r"\\" else "/"
        text = (
            f"a {first}FS01{first_sep}s{first_sep}f.log"
            f" b {second}FS02{second_sep}s{second_sep}g.csv"
        )
        redacted = redact_text(text, CONTEXT)
        assert redacted == f"a {REDACTED_PATH}.csv", text
        assert redact_text(redacted, CONTEXT) == redacted


def test_two_json_escaped_unc_paths_on_one_line_are_redacted_separately() -> None:
    r"""In the escaped form the opener is four backslashes and a separator is
    two, so the two are told apart: the first match ends before the second
    opener instead of stranding its server name, and the prose survives.
    """
    text = json.dumps(r"a \\FS01\s\f.log b \\FS02\s\g.csv")
    redacted = redact_text(text, CONTEXT)
    assert redacted == f'"a {REDACTED_PATH}.log b {REDACTED_PATH}.csv"'


def test_extended_length_prefix_path_is_fully_redacted() -> None:
    r"""The UNC rule read the "?" of "\\?\C:\..." as the host and stopped at the
    excluded colon, which ate the drive letter and left the drive rule nothing to
    anchor on: "opened [redacted-path]:\Users\Jane Doe\file.txt".
    """
    redacted = redact_text(r"opened \\?\C:\Users\Jane Doe\file.txt", CONTEXT)
    assert redacted == f"opened {REDACTED_PATH}.txt"
    assert redact_text(redacted, CONTEXT) == redacted


def test_extended_length_unc_prefix_and_device_path_still_redact() -> None:
    r"""The other two "\\"-prefixed forms must keep working: an extended-length
    UNC path, and a device path whose host segment is a bare dot.
    """
    assert (
        redact_text(r"opened \\?\UNC\FS01\share\Jane Doe\f.log", CONTEXT)
        == f"opened {REDACTED_PATH}.log"
    )
    assert redact_text(r"\\.\PhysicalDrive0 is busy", CONTEXT) == (
        f"{REDACTED_PATH} is busy"
    )


def test_a_token_is_matched_literally_not_as_a_regular_expression() -> None:
    """Without ``re.escape`` the dots of a fully qualified host name become
    wildcards, so an unrelated word of the same length is redacted as if it were
    the machine.
    """
    context = RedactionContext(host_names=("ws42.brusa",))
    assert redact_text("node ws42.brusa stays", context) == f"node {REDACTED_HOST} stays"
    assert redact_text("node ws42Xbrusa stays", context) == "node ws42Xbrusa stays"


def test_a_token_containing_regex_metacharacters_redacts_instead_of_raising() -> None:
    """Without ``re.escape`` a name containing "[", "(", "+" or "*" makes
    ``re.compile`` raise, so ``redact_text`` throws and nothing is redacted at
    all. Real machine and user values reach this pattern.
    """
    context = RedactionContext(host_names=("brusa-ws42[+",))
    assert (
        redact_text("machine brusa-ws42[+ down", context)
        == f"machine {REDACTED_HOST} down"
    )


def test_host_tokens_are_substituted_before_user_tokens() -> None:
    """When a user token is a substring of a host token, substituting users
    first replaces the prefix and leaves the rest of the machine name behind
    ("[redacted-user]-ws42").
    """
    context = RedactionContext(user_names=("brusa",), host_names=("brusa-ws42",))
    assert redact_text("session on brusa-ws42", context) == f"session on {REDACTED_HOST}"


def test_a_colon_ends_the_final_path_segment() -> None:
    """The colon guard is needed on the final-segment class too, not only on the
    interior one: with a colon allowed, a "path:line:" suffix from a tool report
    is swallowed into the match, the extension is no longer found, and the words
    after it are deleted.
    """
    redacted = redact_text(r"C:\src\main.py:42: SyntaxError", CONTEXT)
    assert redacted == f"{REDACTED_PATH}.py:42: SyntaxError"


def test_macos_users_home_path_is_removed() -> None:
    """The POSIX rule covers "/Users/" as well as "/home/"; that branch is what
    catches a mac home directory, which no other rule reaches.
    """
    redacted = redact_text("wrote /Users/jane.doe/model.aedt", CONTEXT)
    assert redacted == f"wrote {REDACTED_PATH}.aedt"


def test_closing_punctuation_after_a_path_with_an_extension_is_preserved() -> None:
    """Trailing punctuation is trimmed before the extension is looked up, so the
    branch that KEEPS an extension has to reattach it too; only the
    no-extension branch was covered.
    """
    redacted = redact_text(r"see (C:\temp\dump.log)", CONTEXT)
    assert redacted == f"see ({REDACTED_PATH}.log)"


def test_a_long_allowlisted_extension_survives() -> None:
    """The extension is read with an unbounded run of characters; capping it at
    six silently drops ".aedtresults", the extension of an AEDT result folder.
    """
    assert redact_text(r"C:\runs\r.aedtresults", CONTEXT) == (
        f"{REDACTED_PATH}.aedtresults"
    )


def test_a_three_character_token_is_still_redacted() -> None:
    """The minimum token length is a floor, not a bar: three characters is the
    shortest token that IS applied, and raising the floor would publish short
    user names such as "fpo".
    """
    context = RedactionContext(user_names=("fpo",))
    assert redact_text("run by fpo", context) == f"run by {REDACTED_USER}"


def test_a_spacey_final_component_keeps_its_last_word() -> None:
    """A measured limit, pinned so nobody rediscovers it as a bug.

    A path with no allowlisted extension whose last component contains a space
    keeps the text after that space. Do not close this by making the final
    segment space-tolerant: that was tried, and it swallows the prose after
    every path in ordinary diagnostics. The caller closes it instead by
    supplying the machine's own login, which is a single token at BRUSA.
    """
    assert redact_text(r"opened C:\Users\Jane Doe", CONTEXT) == (
        f"opened {REDACTED_PATH} Doe"
    )


def test_a_supplied_login_does_not_rescue_the_spacey_component_shape() -> None:
    """The tempting assumption, disproved and pinned.

    It reads as though the token pass is a safety net under the path rules, so
    that anything they strand a supplied user name would still remove. It is
    not: the path rule consumes ``C:\\Users\\Jane`` first and leaves `` Doe``,
    which the token ``Jane Doe`` can no longer match. Only a token equal to the
    stranded word itself would. Whoever next reasons about the guarantee needs
    this written down rather than assumed.
    """
    context = RedactionContext(user_names=("Jane Doe",))

    assert redact_text(r"opened C:\Users\Jane Doe", context) == (
        f"opened {REDACTED_PATH} Doe"
    )

    # A token equal to the stranded word does remove it, which is the only
    # configuration that closes this shape.
    stranded = RedactionContext(user_names=("Doe",))
    assert redact_text(r"opened C:\Users\Jane Doe", stranded) == (
        f"opened {REDACTED_PATH} {REDACTED_USER}"
    )
