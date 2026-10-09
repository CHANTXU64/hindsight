"""Prepare declared remote-client dependencies without mutating live imports."""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from packaging.version import Version

from .settings import _MIN_CLIENT_VERSION


def _client_ready() -> bool:
    try:
        return Version(version("hindsight-client")) >= Version(_MIN_CLIENT_VERSION)
    except PackageNotFoundError:
        return False


def prepare_remote_dependencies(*, explicit: bool) -> tuple[bool, str]:
    """PM publishes a new generation; it does not upgrade this process's imports.

    Keep the legacy installer only for older Hermes hosts, which may still be
    running while the plugin is updated without restarting the gateway.
    """
    if _client_ready():
        return True, "Remote client dependencies are up to date."
    try:
        from pm import sync_venv
    except ModuleNotFoundError as exc:
        if exc.name != "pm":
            raise
        from tools.lazy_deps import install_specs

        outcome = install_specs([f"hindsight-client>={_MIN_CLIENT_VERSION},<1"], timeout=120)
        if outcome.ok:
            return True, "Remote client dependencies installed."
        return False, outcome.reason or (outcome.stderr or "").strip() or "Dependency installation failed."

    try:
        # The enabled plugin's pyproject owns the complete, bounded requirement
        # set. Do not replace the selected environment with just this SDK.
        sync_venv(explicit=explicit)
    except Exception as exc:
        return False, f"Hermes PM could not prepare the remote client: {exc}"
    if _client_ready():
        return True, "Remote client dependencies are up to date."
    return False, (
        "Hermes PM prepared dependencies for a new environment; this running process "
        "still has the old client. Restart Hermes to activate the prepared environment."
    )
