"""Static application metadata for the Help > About dialog.

Nothing here is computed from the project session: it is the same for every
window, so it is exposed as its own context property rather than bolted onto
an existing controller.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QObject

from inductor_designer import __version__
from inductor_designer.application.services.aedt_support import (
    SUPPORTED_AEDT_EDITION,
    SUPPORTED_AEDT_RELEASE,
)


class AppInfoController(QObject):
    def _get_application_name(self) -> str:
        return "PyAEDT Inductor Designer"

    applicationName = Property(str, _get_application_name, constant=True)

    def _get_version(self) -> str:
        return __version__

    version = Property(str, _get_version, constant=True)

    def _get_supported_aedt_release(self) -> str:
        return str(SUPPORTED_AEDT_RELEASE)

    supportedAedtRelease = Property(str, _get_supported_aedt_release, constant=True)

    def _get_supported_aedt_edition(self) -> str:
        return SUPPORTED_AEDT_EDITION.value

    supportedAedtEdition = Property(str, _get_supported_aedt_edition, constant=True)
