"""Official dependency admission: no runtime or setup-time installation.

Replaces the retired Fork prepare_remote_dependencies contract after the user
accepted upstream dependency management. No live environment is modified.
"""
from __future__ import annotations

import builtins
import io
import json
import pytest
import pm

from plugins.memory.hindsight import HindsightMemoryProvider, _warn_if_client_outdated


@pytest.mark.parametrize("version", ["0.0.1", "0.10.3"])
def test_client_check_never_prepares_environment(monkeypatch, caplog, version):
    import importlib.metadata as md
    calls = []
    monkeypatch.setattr(md, "version", lambda _: version)
    monkeypatch.setattr(pm, "sync_venv", lambda **kw: calls.append(kw))
    with caplog.at_level("WARNING"):
        _warn_if_client_outdated()
    assert calls == []
    assert ("hermes plugins update hindsight" in caplog.text) == (version == "0.0.1")


def test_external_setup_checks_only_and_preserves_preferences(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("hermes_cli.memory_setup._curses_select", lambda *a, **kw: 2)
    monkeypatch.setattr("hermes_cli.config.save_config", lambda cfg: None)
    monkeypatch.setattr("plugins.memory.hindsight.templates.run_template_step", lambda **kw: None)
    calls = []
    monkeypatch.setattr(pm, "sync_venv", lambda **kw: calls.append("pm"))
    monkeypatch.setattr("tools.lazy_deps.install_specs", lambda *a, **kw: calls.append("legacy"))
    monkeypatch.setattr(builtins, "input", lambda prompt: "http://127.0.0.1:9999")
    monkeypatch.setattr("sys.stdin", io.StringIO("\n"))
    provider = HindsightMemoryProvider()
    provider._config = {"mode": "local_external", "auto_retain": False, "auto_recall": True, "bank_id": "fixture-bank"}
    provider.post_setup(str(tmp_path), {"memory": {}})
    saved = json.loads((tmp_path / "hindsight/config.json").read_text())
    assert calls == []
    assert saved["mode"] == "local_external"
    assert saved["auto_retain"] is False
    assert saved["auto_recall"] is True
    assert saved["bank_id"] == "fixture-bank"
    assert saved["api_url"] == "http://127.0.0.1:9999"
    assert "Dependencies up to date" in capsys.readouterr().out
