# src/inductor_designer/application/services/redaction.py
"""Turn diagnostic text into text that is allowed to leave this machine.

BRUSA policy is that no personally identifiable information leaves BRUSA
systems, so the diagnostic bundle is designed to be shareable rather than
sanitised afterwards. This module is the only place that decides what
"shareable" means, and exactly two writers call it: the application log
formatter (`adapters/system/app_logging.py`) and the bundle builder
(`application/services/diagnostic_bundle.py`).

A file extension deliberately survives. `[redacted-path].adp` is what makes an
AEDT ``Engine Detected Error`` about a missing ``.adp`` diagnosable, and an
extension names nobody.

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

# E-mail first: its local part may contain a user name, and its domain would
# otherwise be left behind once the user token is replaced by a marker whose
# brackets stop the e-mail pattern from matching at all.
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_UNC_PATH = re.compile(r"\\\\[^\s\\/]+\\[^\s\"'<>|]*")
_DRIVE_PATH = re.compile(r"[A-Za-z]:[\\/][^\s\"'<>|]*")
_POSIX_HOME_PATH = re.compile(r"/(?:home|Users)/[^\s\"'<>|]*")
# FlexNet identifiers are `port@host`; the host alone identifies a BRUSA server.
_LICENSE_SERVER = re.compile(r"\b\d{1,5}@[A-Za-z0-9._-]+")
_EXTENSION = re.compile(r"\.([A-Za-z0-9]{1,6})$")

# A token equal to a word inside a marker would re-redact the marker and break
# idempotence, so those tokens are dropped rather than applied.
_MARKER_WORDS = frozenset(
    {"redacted", "path", "user", "host", "email", "license", "server"}
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
    # Trailing sentence punctuation is not part of the path, and would
    # otherwise be mistaken for the extension.
    extension = _EXTENSION.search(match.group(0).rstrip(".,;:)’'\""))
    if extension is None:
        return REDACTED_PATH
    return f"{REDACTED_PATH}.{extension.group(1)}"


def _token_pattern(tokens: tuple[str, ...]) -> re.Pattern[str] | None:
    usable = {
        token
        for token in tokens
        if len(token) >= _MINIMUM_TOKEN_LENGTH and token.casefold() not in _MARKER_WORDS
    }
    if not usable:
        return None
    # Longest first, so a fully qualified host name is replaced as one token
    # rather than leaving its domain behind.
    ordered = sorted(usable, key=len, reverse=True)
    return re.compile("|".join(re.escape(token) for token in ordered), re.IGNORECASE)


def redact_text(text: str, context: RedactionContext) -> str:
    """Remove every shareability hazard. Idempotent by construction."""
    redacted = _EMAIL.sub(REDACTED_EMAIL, text)
    redacted = _UNC_PATH.sub(_path_replacement, redacted)
    redacted = _DRIVE_PATH.sub(_path_replacement, redacted)
    redacted = _POSIX_HOME_PATH.sub(_path_replacement, redacted)
    redacted = _LICENSE_SERVER.sub(REDACTED_LICENSE_SERVER, redacted)
    hosts = _token_pattern(context.host_names)
    if hosts is not None:
        redacted = hosts.sub(REDACTED_HOST, redacted)
    users = _token_pattern(context.user_names)
    if users is not None:
        redacted = users.sub(REDACTED_USER, redacted)
    return redacted
