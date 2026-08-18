# src/inductor_designer/application/services/redaction.py
"""Turn diagnostic text into text that is allowed to leave this machine.

BRUSA policy is that no personally identifiable information leaves BRUSA
systems, so the diagnostic bundle is designed to be shareable rather than
sanitised afterwards. This module is the only place that decides what
"shareable" means, and exactly two writers call it: the application log
formatter (`adapters/system/app_logging.py`) and the bundle builder
(`application/services/diagnostic_bundle.py`).

A file extension deliberately survives, but only one this application or its
solvers actually produce. `[redacted-path].adp` is what makes an AEDT ``Engine
Detected Error`` about a missing ``.adp`` diagnosable, and such an extension
names nobody -- whereas the ``.doe`` of ``C:\\Users\\jane.doe`` is a surname.
Nothing structural separates the two, so only the allowlist below is kept.

Logs written inside a run directory are NOT redacted: they stay on the user's
own machine, where the absolute path is the useful part. Redaction happens on
the way into the bundle, not on the way onto disk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

REDACTED_EMAIL = "[redacted-email]"
REDACTED_HOST = "[redacted-host]"
REDACTED_LICENSE_SERVER = "[redacted-license-server]"
REDACTED_PATH = "[redacted-path]"
REDACTED_USER = "[redacted-user]"

# An extension is kept only if it names a file type this application, AEDT, or
# FEMM actually produces. This allowlist exists because nothing structural
# distinguishes a file name from a dotted personal name: "notes.txt" and
# "jane.doe" have the same shape, so keeping "whatever follows the last dot"
# publishes a surname. Anything not listed here is redacted with the path.
_TECHNICAL_EXTENSIONS = frozenset(
    {
        "adp", "aedt", "aedtresults", "aedz", "asol", "cfg", "csv", "err", "fem",
        "fnd", "json", "log", "ngmesh", "pjt", "profile", "prop", "py", "pyaedt",
        "qml", "sqlite", "stats", "svg", "tab", "txt", "xlsx", "xml", "zip",
    }
)

# An INTERIOR path character is anything except a separator, a line break, or
# the quoting/bracketing punctuation that marks where free-form text resumes.
# It deliberately allows spaces: "C:\Program Files" and "\\host\share\sub
# dir\file.txt" are the common case on Windows, not an edge case, so a space
# must not end the match early and leave a surname behind.
_PATH_CHAR = r'[^\\/\r\n"\'<>|]'
# A FINAL path character additionally excludes whitespace, which is what bounds
# the match: prose after a path always begins after a space.
_FINAL_CHAR = r'[^\\/\s"\'<>|]'
# An interior segment always ends in a separator, so an embedded space (the
# surname in "Jane Doe") is unambiguous: it is followed by more path. The last
# character before the separator must not be a space, because no real path has
# one there -- that is what stops "dump and see /home/x" from being read as a
# single segment and swallowing the prose between two paths.
_PATH_SEGMENT = _PATH_CHAR + r"*" + _FINAL_CHAR + r"[\\/]"
# The final segment may not contain whitespace, so it can never swallow the
# rest of the sentence. No extension guessing is involved in finding its end.
_PATH_TAIL = r"(?:" + _PATH_SEGMENT + r")*" + _FINAL_CHAR + r"*"

# License server first: `1055@licsrv01.brusa.biz` also matches the e-mail
# shape, and if e-mail runs first it mislabels a license identifier.
# FlexNet identifiers are `port@host`; the host alone identifies a BRUSA server.
_LICENSE_SERVER = re.compile(r"\b\d{1,5}@[A-Za-z0-9._-]+")
# E-mail next: its local part may contain a user name, and its domain would
# otherwise be left behind once the user token is replaced by a marker whose
# brackets stop the e-mail pattern from matching at all.
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# The share segment is optional: a bare `\\HOST` is still a machine identifier.
# The host itself uses the final-segment class, so a bare host ends at the same
# boundary as everything else instead of eating the rest of the line.
_UNC_PATH = re.compile(r"\\\\" + _FINAL_CHAR + r"+(?:[\\/]" + _PATH_TAIL + r")?")
_DRIVE_PATH = re.compile(r"[A-Za-z]:[\\/]" + _PATH_TAIL)
_POSIX_HOME_PATH = re.compile(r"/(?:home|Users)/" + _PATH_TAIL)
_EXTENSION = re.compile(r"\.([A-Za-z0-9]+)$")
# Trailing punctuation (closing bracket/quote, sentence punctuation) is never
# part of the path; it is trimmed off the match and reattached verbatim so it
# is not silently swallowed by a path that turned out to have no extension.
_TRAILING_PUNCTUATION = ".,;:)\u2019'\""

# A token contained anywhere in a marker string (e.g. user name "cted" inside
# "[redacted-path]") would re-redact the marker it just produced, so those
# tokens are dropped rather than applied. This makes "idempotent by
# construction" below actually true instead of true-except-for-this-case.
_MARKERS = (
    REDACTED_EMAIL,
    REDACTED_HOST,
    REDACTED_LICENSE_SERVER,
    REDACTED_PATH,
    REDACTED_USER,
)
# One- and two-character tokens match inside ordinary words; a machine that
# reports such a user name is better served by the path rules alone.
_MINIMUM_TOKEN_LENGTH = 3


@dataclass(frozen=True, slots=True)
class RedactionContext:
    """Machine-specific tokens no regular expression can recognise on its own."""

    user_names: tuple[str, ...] = ()
    host_names: tuple[str, ...] = ()


def _path_replacement(match: re.Match[str]) -> str:
    # Trailing sentence/bracket punctuation is not part of the path. Trim it
    # off before looking for the extension, but keep it: it belongs to the
    # surrounding text, not to the match that is being thrown away.
    raw = match.group(0)
    core = raw.rstrip(_TRAILING_PUNCTUATION)
    trailing = raw[len(core) :]
    extension = _EXTENSION.search(core)
    if extension is None or extension.group(1).casefold() not in _TECHNICAL_EXTENSIONS:
        return REDACTED_PATH + trailing
    return f"{REDACTED_PATH}.{extension.group(1)}{trailing}"


def _token_pattern(tokens: tuple[str, ...]) -> re.Pattern[str] | None:
    usable = {
        token
        for token in tokens
        if len(token) >= _MINIMUM_TOKEN_LENGTH
        and not any(token.casefold() in marker.casefold() for marker in _MARKERS)
    }
    if not usable:
        return None
    # Longest first, so a fully qualified host name is replaced as one token
    # rather than leaving its domain behind.
    ordered = sorted(usable, key=len, reverse=True)
    return re.compile("|".join(re.escape(token) for token in ordered), re.IGNORECASE)


def redact_text(text: str, context: RedactionContext) -> str:
    """Remove every shareability hazard. Idempotent by construction."""
    redacted = _LICENSE_SERVER.sub(REDACTED_LICENSE_SERVER, text)
    redacted = _EMAIL.sub(REDACTED_EMAIL, redacted)
    redacted = _UNC_PATH.sub(_path_replacement, redacted)
    redacted = _DRIVE_PATH.sub(_path_replacement, redacted)
    redacted = _POSIX_HOME_PATH.sub(_path_replacement, redacted)
    hosts = _token_pattern(context.host_names)
    if hosts is not None:
        redacted = hosts.sub(REDACTED_HOST, redacted)
    users = _token_pattern(context.user_names)
    if users is not None:
        redacted = users.sub(REDACTED_USER, redacted)
    return redacted
