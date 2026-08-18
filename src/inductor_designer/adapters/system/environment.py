"""What this machine is, and where the application keeps its private state.

A Project document is shareable and its directory belongs to the user, so the
recovery snapshot and the application log live outside it -- an autosave must
never appear as a stray file next to a project a user is about to send to a
colleague.
"""

from __future__ import annotations

import contextlib
import getpass
import os
import platform
from pathlib import Path

from inductor_designer.application.services.redaction import RedactionContext

APPLICATION_DIRECTORY_NAME = "InductorDesigner"

# The minimum a redaction token must clear before it is trusted not to
# collide with ordinary prose; see `redaction._MINIMUM_TOKEN_LENGTH`. Kept
# here too so an empty or one-character environment value never becomes a
# token that would corrupt unrelated text -- `redact_text` already drops
# short tokens, but filtering here keeps a name like "" or "no" out of the
# context in the first place, which is what the "at least one" test needs
# to mean anything.
_MINIMUM_TOKEN_LENGTH = 3


def application_data_directory() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    # Windows is the product platform (ADR 0004). The fallback exists only so
    # the non-solver suite runs on the Linux CI runner; it is not a supported
    # product configuration. `Path.home()` can raise `RuntimeError` in a fully
    # stripped environment (no home directory resolvable); that is acceptable
    # fail-fast behaviour for a configuration this product does not support,
    # not a case to guard against here.
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / APPLICATION_DIRECTORY_NAME


def recovery_directory() -> Path:
    return application_data_directory() / "recovery"


def log_directory() -> Path:
    return application_data_directory() / "logs"


def _usable(name: str | None) -> str | None:
    if name is None:
        return None
    stripped = name.strip()
    return stripped if len(stripped) >= _MINIMUM_TOKEN_LENGTH else None


def environment_redaction_context() -> RedactionContext:
    """The user and host tokens no regular expression can recognise."""
    users = {
        token
        for token in (
            _usable(os.environ.get("USERNAME")),
            _usable(os.environ.get("USER")),
        )
        if token
    }
    with contextlib.suppress(Exception):
        # getpass consults the password database on POSIX and can raise there.
        token = _usable(getpass.getuser())
        if token:
            users.add(token)
    with contextlib.suppress(Exception):
        token = _usable(Path.home().name)
        if token:
            users.add(token)
    hosts = {
        token
        for token in (
            _usable(os.environ.get("COMPUTERNAME")),
            _usable(platform.node()),
        )
        if token
    }
    # A node may be reported fully qualified; its first label identifies the
    # machine on its own, so both forms are redacted.
    hosts |= {token for host in tuple(hosts) if (token := _usable(host.split(".")[0]))}
    return RedactionContext(
        user_names=tuple(sorted(users)), host_names=tuple(sorted(hosts))
    )
