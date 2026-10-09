"""Actual Hermes dispatch across the retained Fork / new upstream seams.

SDK and auxiliary-model responses are deterministic doubles; no remote writes.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.memory_manager import MemoryManager
from plugins.memory.hindsight.recall_cache import RecallSnapshot
from plugins.memory.hindsight.recall_preprocessor import RecallPreprocessDecision
from test_hindsight_provider import provider_with_config


@pytest.mark.parametrize("rewritten", [False, True])
def test_manager_prefetch_keeps_fork_pipeline_and_upstream_bank_score_filters(
    provider_with_config, monkeypatch, rewritten,
):
    provider = provider_with_config(
        bank_id="primary", recall_additional_banks=["shared"],
        recall_min_scores={"reranker": 0.5},
    )
    calls = []

    async def recall(**kwargs):
        calls.append(kwargs)
        bank = kwargs["bank_id"]
        return SimpleNamespace(results=[
            SimpleNamespace(text=f"{bank} relevant", scores=SimpleNamespace(reranker=0.8)),
            SimpleNamespace(text=f"{bank} off-topic", scores=SimpleNamespace(reranker=0.1)),
        ])

    provider._client.arecall = AsyncMock(side_effect=recall)
    decisions = []

    def decide(**kwargs):
        decisions.append(kwargs)
        return RecallPreprocessDecision(drop_old_refs=(1,), new_query="rewritten query")

    monkeypatch.setattr("plugins.memory.hindsight.recall_preprocessor.run_recall_preprocessor", decide)
    if rewritten:
        provider._recall_cache.seed(RecallSnapshot(query="old", results=("old irrelevant",)))
    manager = MemoryManager(external_prefetch_timeout=2)
    manager.add_provider(provider)
    result = manager.prefetch_all(
        "current query", session_id="test-session", turn_id="new-turn",
        previous_assistant_message="prior answer" if rewritten else "",
    )
    assert "primary relevant" in result and "shared relevant" in result
    assert "off-topic" not in result and "old irrelevant" not in result
    assert {call["bank_id"] for call in calls} == {"primary", "shared"}
    assert len(calls) == 2
    assert all(call["query"] == ("rewritten query" if rewritten else "current query") for call in calls)
    assert all(call["min_scores"] == {"reranker": 0.5} for call in calls)
    assert len(decisions) == int(rewritten)
    if rewritten:
        assert decisions[0]["current_user_message"] == "current query"
        assert decisions[0]["previous_assistant_message"] == "prior answer"
    provider.shutdown()


@pytest.mark.parametrize("action", ["add", "replace"])
def test_memory_tool_notification_keeps_official_write_independent_of_auto_retain(
    provider_with_config, action,
):
    provider = provider_with_config(auto_retain=False, bank_id="primary", recall_additional_banks=["readonly"])
    client = provider._client
    manager = MemoryManager()
    manager.add_provider(provider)
    manager.notify_memory_tool_write(
        {"success": True}, {"action": action, "target": "user", "content": "用户偏好原文"},
    )
    provider.shutdown()  # actual writer queue is drained, not replaced by an inline stub
    client.aretain_batch.assert_awaited_once()
    call = client.aretain_batch.call_args.kwargs
    assert call["bank_id"] == "primary"
    assert call["items"][0]["content"] == "用户偏好原文"
    assert f"builtin-action:{action}" in call["items"][0]["tags"]
