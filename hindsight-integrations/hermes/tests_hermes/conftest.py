"""Run the plugin against a real Hermes Agent checkout instead of the stubbed core in ``tests/``.

These are the Hindsight regression tests carried over from the CHANTXU64/hermes-agent fork, where
the plugin used to be bundled as ``plugins.memory.hindsight``. They exercise the plugin together with
Hermes' real ``agent.*`` / ``plugins.memory`` / ``tools.*`` modules, so they need a Hermes checkout:

    HERMES_AGENT_ROOT=~/.hermes/hermes-agent \
        ~/.hermes/hermes-agent/.venv/bin/python -m pytest tests_hermes

Run them separately from ``tests/``: that suite replaces Hermes core modules with stubs in
``sys.modules`` and the two cannot share one interpreter.

The target is the CHANTXU64/hermes-agent fork. A few recall-preprocessor cases drive the fork's
``MemoryManager.prefetch_all(turn_id=..., previous_assistant_message=...)`` and prefetch-timeout
hooks end to end; against an upstream checkout without those hooks they fail by design, which is
the signal that an upstream sync dropped the core half of this plugin's recall pipeline.

Hermes' own ``tests/conftest.py`` is loaded as a plugin so every test gets the same hermetic
sandbox (per-test HERMES_HOME, scrubbed credential env vars, live-system guards) as in Hermes.
The plugin directory is then registered under its former bundled name, so the carried-over tests
and their ``monkeypatch.setattr("plugins.memory.hindsight....")`` targets need no rewriting.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent
HERMES_ROOT = Path(os.environ.get("HERMES_AGENT_ROOT", "~/.hermes/hermes-agent")).expanduser().resolve()
PLUGIN_MODULE = "plugins.memory.hindsight"

if not (HERMES_ROOT / "agent" / "memory_provider.py").is_file():
    raise RuntimeError(
        f"tests_hermes needs a Hermes Agent checkout; set HERMES_AGENT_ROOT (tried {HERMES_ROOT})"
    )
if str(HERMES_ROOT) not in sys.path:
    sys.path.insert(0, str(HERMES_ROOT))

# Hermes' conftest sandboxes HERMES_HOME at import time, so it must run before any Hermes module is
# imported (which is why the plugin is registered in pytest_configure, not at module level here).
pytest_plugins = ["tests.conftest"]


def _register_plugin_as_bundled_provider() -> None:
    import plugins.memory as memory_package

    # A Hermes checkout that still bundles the provider must not shadow this directory.
    for name in [n for n in sys.modules if n == PLUGIN_MODULE or n.startswith(PLUGIN_MODULE + ".")]:
        del sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        PLUGIN_MODULE, PLUGIN_DIR / "__init__.py", submodule_search_locations=[str(PLUGIN_DIR)]
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[PLUGIN_MODULE] = module
    spec.loader.exec_module(module)
    memory_package.hindsight = module


def pytest_configure(config):
    _register_plugin_as_bundled_provider()


def pytest_report_header(config):
    return f"hindsight plugin: {PLUGIN_DIR}\nhermes agent: {HERMES_ROOT}"
