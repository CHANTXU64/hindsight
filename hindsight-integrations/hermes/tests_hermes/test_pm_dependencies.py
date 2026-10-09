"""Remote dependency management against the real Hermes PM interface."""
from __future__ import annotations

import builtins
import io
from types import SimpleNamespace

import pm
import pytest

from plugins.memory.hindsight import HindsightMemoryProvider, dependencies


def test_current_client_never_installs(monkeypatch):
    monkeypatch.setattr(dependencies, "version", lambda _: dependencies._MIN_CLIENT_VERSION)

    def unexpected(**kwargs):
        pytest.fail("an already available client must not rebuild the application environment")

    monkeypatch.setattr(pm, "sync_venv", unexpected)
    ready, notice = dependencies.prepare_remote_dependencies(explicit=True)
    assert ready is True
    assert "up to date" in notice


@pytest.mark.parametrize("explicit", [True, False])
def test_preparation_does_not_claim_live_activation(monkeypatch, explicit):
    monkeypatch.setattr(dependencies, "version", lambda _: "0.0.1")
    calls = []
    monkeypatch.setattr(pm, "sync_venv", lambda **kw: calls.append(kw))
    ready, notice = dependencies.prepare_remote_dependencies(explicit=explicit)
    assert calls == [{"explicit": explicit}]
    assert ready is False
    assert "Restart Hermes" in notice


def test_missing_client_reports_pm_failure_without_raw_install(monkeypatch):
    def missing(_):
        raise dependencies.PackageNotFoundError("hindsight-client")

    def refused(**kwargs):
        raise RuntimeError("dependency union conflict")

    monkeypatch.setattr(dependencies, "version", missing)
    monkeypatch.setattr(pm, "sync_venv", refused)
    ready, notice = dependencies.prepare_remote_dependencies(explicit=True)
    assert ready is False
    assert "dependency union conflict" in notice


def test_legacy_host_keeps_legacy_installer(monkeypatch):
    monkeypatch.setattr(dependencies, "version", lambda _: "0.0.1")
    real_import = builtins.__import__

    def old_host(name, *args, **kwargs):
        if name == "pm":
            raise ModuleNotFoundError("No module named 'pm'", name="pm")
        return real_import(name, *args, **kwargs)

    calls = []
    monkeypatch.setattr(builtins, "__import__", old_host)
    monkeypatch.setattr(
        "tools.lazy_deps.install_specs",
        lambda specs, **kw: calls.append((specs, kw)) or SimpleNamespace(ok=True),
    )
    ready, _ = dependencies.prepare_remote_dependencies(explicit=True)
    assert ready is True
    assert calls == [([f"hindsight-client>={dependencies._MIN_CLIENT_VERSION},<1"], {"timeout": 120})]


def test_broken_pm_import_does_not_fall_back_to_retired_installer(monkeypatch):
    monkeypatch.setattr(dependencies, "version", lambda _: "0.0.1")
    real_import = builtins.__import__

    def broken_host(name, *args, **kwargs):
        if name == "pm":
            raise ModuleNotFoundError("PM dependency missing", name="pm_dependency")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", broken_host)
    with pytest.raises(ModuleNotFoundError, match="PM dependency missing"):
        dependencies.prepare_remote_dependencies(explicit=True)


def test_external_setup_uses_pm_and_preserves_existing_preferences(tmp_path, monkeypatch, capsys):
    """Drive the real setup entry, with only interactive input and the PM side effect stubbed."""
    monkeypatch.setattr("hermes_cli.memory_setup._curses_select", lambda *a, **kw: 2)
    monkeypatch.setattr("hermes_cli.config.save_config", lambda cfg: None)
    monkeypatch.setattr("plugins.memory.hindsight.templates.run_template_step", lambda **kw: None)
    monkeypatch.setattr(dependencies, "version", lambda _: "0.0.1")
    calls = []
    monkeypatch.setattr(pm, "sync_venv", lambda **kw: calls.append(kw))
    monkeypatch.setattr(builtins, "input", lambda prompt: "http://127.0.0.1:9999")
    monkeypatch.setattr("sys.stdin", io.StringIO("\n"))
    provider = HindsightMemoryProvider()
    provider._config = {"mode": "local_external", "auto_retain": False, "auto_recall": True, "bank_id": "fixture-bank"}
    provider.post_setup(str(tmp_path), {"memory": {}})
    import json
    saved = json.loads((tmp_path / "hindsight/config.json").read_text())
    assert calls == [{"explicit": True}]
    assert saved["mode"] == "local_external"
    assert saved["auto_retain"] is False
    assert saved["auto_recall"] is True
    assert saved["bank_id"] == "fixture-bank"
    assert saved["api_url"] == "http://127.0.0.1:9999"
    assert "Restart Hermes" in capsys.readouterr().out
