"""Hindsight cases that upstream Hermes dropped from its core test files when the provider moved out.

Carried over from the CHANTXU64/hermes-agent fork:

* ``tests/agent/test_memory_session_switch.py`` — Hindsight reference implementation of
  ``on_session_switch`` state flushing.
* ``tests/plugins/memory/test_multiplex_memory_identity_scope.py`` — a secondary multiplexed profile
  must never inherit the default profile's Hindsight identity or retain shaping.
* ``tests/plugins/memory/test_provider_threads_inherit_profile.py`` — the provider's background
  thread runs under the spawning profile's HERMES_HOME.
"""

from __future__ import annotations

import pytest

from agent import secret_scope
from hermes_constants import get_hermes_home, reset_hermes_home_override, set_hermes_home_override
from plugins.memory.hindsight.recall_cache import HindsightRecallCache


# ---------------------------------------------------------------------------
# on_session_switch state flushing
# ---------------------------------------------------------------------------


def _make_hindsight_provider():
    """Build a bare HindsightMemoryProvider that skips network setup.

    We instantiate without importing optional deps at class-level by
    bypassing __init__ and seeding the attributes on_session_switch
    reads/writes. This keeps the test hermetic.
    """
    import threading
    hindsight_mod = pytest.importorskip("plugins.memory.hindsight")
    provider = object.__new__(hindsight_mod.HindsightMemoryProvider)
    provider._session_id = "old-sid"
    provider._parent_session_id = ""
    provider._document_id = "old-sid-20260101_000000_000000"
    provider._session_turns = ["turn-1", "turn-2"]
    provider._last_flushed_turn_count = 0
    provider._last_queued_flush_count = 2
    provider._retain_flush_pending = False
    provider._retain_generation = 0
    provider._retain_flush_lock = threading.Lock()
    provider._auto_retain = True
    provider._turn_counter = 2
    provider._turn_index = 2
    # Attrs read by _build_metadata / _build_retain_kwargs when the
    # buffer-flush path on session switch fires. Empty strings keep the
    # metadata minimal but well-formed.
    provider._retain_source = ""
    provider._platform = ""
    provider._user_id = ""
    provider._user_name = ""
    provider._chat_id = ""
    provider._chat_name = ""
    provider._chat_type = ""
    provider._thread_id = ""
    provider._agent_identity = ""
    provider._agent_workspace = ""
    provider._retain_tags = []
    provider._retain_context = "test-context"
    provider._retain_async = False
    provider._bank_id = "test-bank"
    provider._write_bank_ids = ["test-bank"]
    # Carried recall state the switch path clears.
    provider._recall_cache = HindsightRecallCache(initial_session_id="old-sid")
    # Sync thread tracking (legacy alias at the writer).
    provider._sync_thread = None
    # Writer queue infra the flush-on-switch path enqueues onto. We stub
    # _ensure_writer / _register_atexit so no real thread is spawned;
    # tests exercising flush delivery live in
    # tests/plugins/memory/test_hindsight_provider.py where the full
    # writer-queue wiring is in place.
    import queue as _queue
    provider._retain_queue = _queue.Queue()
    provider._shutting_down = threading.Event()
    provider._atexit_registered = True
    provider._ensure_writer = lambda: None
    provider._register_atexit = lambda: None
    # Mode + API state used by _resolve_retain_target; stub the resolver
    # so tests don't actually probe the API. Real probe behavior is
    # exercised by tests in tests/plugins/memory/test_hindsight_provider.py.
    provider._mode = "cloud"
    provider._api_url = ""
    provider._api_key = ""
    provider._client = None
    provider._resolve_retain_target = lambda fb: (fb, None)
    # Stub the network-touching helper so any enqueued flush closure is
    # a no-op if ever drained in a unit test.
    provider._run_hindsight_operation = lambda _op: None
    return provider


def test_hindsight_on_session_switch_updates_session_id_and_mints_fresh_doc():
    provider = _make_hindsight_provider()
    old_doc = provider._document_id

    provider.on_session_switch(
        "new-sid", parent_session_id="old-sid", reset=False, reason="resume"
    )

    assert provider._session_id == "new-sid"
    assert provider._parent_session_id == "old-sid"
    # Document id MUST be fresh — else next retain overwrites old session doc
    assert provider._document_id != old_doc
    assert provider._document_id.startswith("new-sid-")


def test_hindsight_on_session_switch_clears_turn_buffers():
    """Accumulated _session_turns must not leak into the next session.

    Hindsight batches turns under a single _document_id. If the buffer
    isn't cleared on switch, the next retain under the new _document_id
    flushes turns that belong to the previous session.
    """
    provider = _make_hindsight_provider()
    provider.on_session_switch("new-sid", parent_session_id="old-sid")
    assert provider._session_turns == []
    assert provider._turn_counter == 0
    assert provider._turn_index == 0



# ---------------------------------------------------------------------------
# Multiplexed profiles: identity and retain shaping stay per-profile
# ---------------------------------------------------------------------------

_DEFAULT_ENV = {
    "HINDSIGHT_BANK_ID": "bank-default", "HINDSIGHT_MODE": "local_external", "HINDSIGHT_API_URL": "http://hs.default",
    "HINDSIGHT_RETAIN_TAGS": "tag-default", "HINDSIGHT_RETAIN_OBSERVATION_SCOPES": "per_tag",
    "HINDSIGHT_RETAIN_SOURCE": "source-default", "HINDSIGHT_RETAIN_USER_PREFIX": "UserDefault",
    "HINDSIGHT_RETAIN_ASSISTANT_PREFIX": "AssistantDefault",
}


@pytest.fixture
def secondary_profile(monkeypatch, tmp_path):
    """Multiplex ON; default profile's values in environ; secondary profile `b` scope with only its
    own API keys (no identity/tenant/endpoint vars)."""
    for k, v in _DEFAULT_ENV.items():
        monkeypatch.setenv(k, v)
    home = tmp_path / ".hermes"
    prof_b = home / "profiles" / "b"
    prof_b.mkdir(parents=True)
    (prof_b / "config.yaml").write_text("{}\n")
    monkeypatch.setenv("HERMES_HOME", str(prof_b))
    secret_scope.set_multiplex_active(True)
    token = secret_scope.set_secret_scope({"RETAINDB_API_KEY": "rdb-b", "SUPERMEMORY_API_KEY": "sm-b",
                                           "HONCHO_API_KEY": "honcho-b", "MEM0_API_KEY": "mem0-b"})
    try:
        yield prof_b
    finally:
        secret_scope.reset_secret_scope(token)
        secret_scope.set_multiplex_active(False)


def test_secondary_profile_hindsight_identity_never_inherits_default_environ(secondary_profile):
    import plugins.memory.hindsight as hindsight

    hcfg = hindsight._load_config()
    assert (hcfg["banks"]["hermes"]["bankId"], hcfg["mode"]) == ("hermes", "cloud")


def test_hindsight_retain_shaping_is_not_re_read_from_the_default_profile_environ(secondary_profile):
    """The provider must retain with ITS OWN shaping, not the default profile's.

    ``_load_config`` resolves retain shaping through the secret scope, but the values it produces
    pass through ``_apply_retain_settings``, whose ``cfg_or_env`` half re-read ``os.environ`` — so
    every scoped miss came back as the default profile's tag, scope, source and speaker prefixes.
    ``metadata.source`` is opt-in by AGENTS.md, and tags are the retrieval partition, so a secondary
    profile's memories were both mislabelled and selectable by the default profile's tag filters.
    """
    import plugins.memory.hindsight as hindsight
    from plugins.memory.hindsight.settings import _DEFAULT_RETAIN_SOURCE

    cfg = hindsight._load_config()
    assert (cfg["retain_source"], cfg["retain_user_prefix"], cfg["retain_assistant_prefix"]) == (
        _DEFAULT_RETAIN_SOURCE, "User", "Assistant")

    provider = hindsight.HindsightMemoryProvider()
    provider._apply_retain_settings(cfg)
    assert provider._retain_tags == []
    assert provider._observation_scopes is None
    assert provider._retain_source == _DEFAULT_RETAIN_SOURCE
    assert (provider._retain_user_prefix, provider._retain_assistant_prefix) == ("User", "Assistant")

    # A config.json install never reaches ``_load_config``'s scoped read at all, so the fallback
    # inside ``_apply_retain_settings`` is the only gate for it.
    provider._apply_retain_settings({})
    assert provider._retain_tags == []
    assert provider._retain_source == _DEFAULT_RETAIN_SOURCE

    # The profile's OWN scoped values still win — this is isolation, not a blindfold.
    token = secret_scope.set_secret_scope({"HINDSIGHT_RETAIN_TAGS": "tag-b", "HINDSIGHT_RETAIN_SOURCE": "source-b"})
    try:
        provider._apply_retain_settings({})
    finally:
        secret_scope.reset_secret_scope(token)
    assert provider._retain_tags == ["tag-b"]
    assert provider._retain_source == "source-b"


def test_hindsight_retain_shaping_still_reads_the_process_env_for_a_single_profile(monkeypatch, tmp_path):
    """No multiplexing: the process env IS this profile's own .env, so it must keep being read."""
    import plugins.memory.hindsight as hindsight

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("HINDSIGHT_RETAIN_TAGS", "solo-tag")
    monkeypatch.setenv("HINDSIGHT_RETAIN_SOURCE", "solo-source")
    monkeypatch.setenv("HINDSIGHT_RETAIN_USER_PREFIX", "Operator")

    provider = hindsight.HindsightMemoryProvider()
    provider._apply_retain_settings({})
    assert provider._retain_tags == ["solo-tag"]
    assert provider._retain_source == "solo-source"
    assert provider._retain_user_prefix == "Operator"



# ---------------------------------------------------------------------------
# Background threads inherit the spawner's profile
# ---------------------------------------------------------------------------


def test_retain_writer_thread_sees_spawner_profile_home(tmp_path, monkeypatch):
    """Recall runs on the caller's thread (the fork's recall cache dropped the prefetch thread), so
    the provider's background thread is the retain writer: a job it drains after the spawning turn
    has left the profile scope must still resolve that profile's home, not the launch default."""
    import plugins.memory.hindsight as hindsight

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "default"))
    profile_home = tmp_path / "profiles" / "b"
    profile_home.mkdir(parents=True)
    seen: dict = {}
    p = hindsight.HindsightMemoryProvider()
    p._apply_retain_settings({})
    p._retain_async = False
    p._resolve_retain_target = lambda fallback: (fallback, None)
    p._retain_batch = lambda *args, **kwargs: seen.setdefault("home", get_hermes_home())
    token = set_hermes_home_override(profile_home)
    try:
        p.sync_turn("remember this", "noted")
        thread = p._writer_thread
    finally:
        reset_hermes_home_override(token)
    assert thread is not None
    try:
        p._retain_queue.join()
    finally:
        p.shutdown()
    assert seen.get("home") == profile_home
