# Local Modifications — CHANTXU64/hindsight

This is the single intent index for the Hermes plugin Fork, not a server deployment log.

- Fork: https://github.com/CHANTXU64/hindsight.git
- Upstream: https://github.com/vectorize-io/hindsight.git
- Stable branch: `chantxu64/hermes-fork`
- Maintenance mode: merge fixed upstream snapshots on an isolated sync branch; preserve public history.
- Scope: `hindsight-integrations/hermes/`. Upstream monorepo content is merged normally; no Hindsight server deployment is implied.
- Operational evidence: `docs/FORK_SYNC_HISTORY.jsonl`. Historical coverage begins with this index; earlier intent is reconstructed only from the two existing Fork commits and carried tests.

## Active maintenance units

### Context-aware recall pipeline

- ID: `hermes-context-aware-recall`
- Status: active
- Depends on: none
- Source boundary: logical-only (introduced by `702855c1`; not an independently replayable topic)

Files / touchpoints:
- `hindsight-integrations/hermes/__init__.py` — provider registration, initialization, prefetch, timeout, rewind, session switching and shutdown seams.
- `hindsight-integrations/hermes/recall_cache.py` — Fork-owned session/turn/generation snapshots.
- `hindsight-integrations/hermes/recall_preprocessor.py` — Fork-owned P5 decision and auxiliary routing.
- `hindsight-integrations/hermes/tests/test_provider.py` — upstream registration fixture accepts auxiliary task registration.
- `hindsight-integrations/hermes/tests_hermes/test_fork_recall_cache.py`
- `hindsight-integrations/hermes/tests_hermes/test_fork_recall_preprocessor.py`
- `hindsight-integrations/hermes/tests_hermes/test_fork_p5_policy.py`
- `hindsight-integrations/hermes/tests_hermes/test_fork_provider_regressions.py`
- `hindsight-integrations/hermes/tests_hermes/test_fork_upstream_sync.py`

Intent / invariants:
- Cache misses can recall synchronously; P5 consumes current user text, previous assistant text and the preceding real recall snapshot, selecting references and optionally generating a new query.
- No raw post-turn background recall; failed preprocessing/retrieval preserves the specified fallback semantics, including empty-cache behavior.
- Stale session/generation results must not re-enter context after timeout, rewind or rotation; the host receives the full bounded prefetch timeout and turn metadata.
- Existing P5 prompt, configured auxiliary routing and fallback policy stay intact. Upstream score filtering and optional multi-bank routing apply to new SDK retrievals without replacing P5.
- Requires the existing Hermes Fork MemoryManager turn/timeout hooks; this repository does not modify the Hermes host.

Merge decision:
- Preserve when: upstream does not cover all snapshot, P5 and lifecycle invariants.
- Drop when: a fully verified upstream equivalent is explicitly accepted by the user.
- Ask user when: query policy, defaults, auxiliary routing or fallback/lifecycle behavior would change.

Verification:
```bash
HERMES_AGENT_ROOT=/path/to/hermes-agent python -m pytest hindsight-integrations/hermes/tests_hermes -q -o addopts=
python -m pytest hindsight-integrations/hermes/tests -q -o addopts=
```
Run suites in separate interpreters: upstream tests stub Hermes modules; tests_hermes loads the real checkout.

- Upstream status: fork-only; upstream multi-bank and minimum-score features are complementary, not accepted P5 replacements.
- Last validated: upstream `6d8b096786df335fc2cc1e5d6662092f0e1b8694`; Fork merge candidate based on `3981e1d47ee1a4cdd2c50c368a5ab9f2089af585` (see sync record).
- Feature docs: none — module docstrings and behavior tests carry the detailed contract.

### Real Hermes compatibility and retired-retain guards

- ID: `hermes-host-compatibility`
- Status: active
- Depends on: `hermes-context-aware-recall`
- Source boundary: logical-only

Files / touchpoints:
- `hindsight-integrations/hermes/tests_hermes/conftest.py`
- `hindsight-integrations/hermes/tests_hermes/test_hermes_core_integration.py`
- `hindsight-integrations/hermes/tests_hermes/test_hindsight_provider.py`
- `hindsight-integrations/hermes/tests_hermes/test_hindsight_env_perms.py`
- `hindsight-integrations/hermes/tests_hermes/test_hindsight_health_grace_timeout.py`
- `hindsight-integrations/hermes/tests_hermes/test_hindsight_root_guard.py`
- `hindsight-integrations/hermes/tests_hermes/test_fork_manual_retain_removed.py`
- `hindsight-integrations/hermes/tests_hermes/test_fork_unicode_contract.py`
- `hindsight-integrations/hermes/tests_hermes/test_pm_dependencies.py`
- `hindsight-integrations/hermes/tests_hermes/test_fork_upstream_sync.py`

Intent / invariants:
- Exercise the plugin with real Hermes host dispatch, isolated homes and fake remote/model clients.
- Preserve UTF-8, bank/tags/metadata, secret scope, file permissions, runtime warning policy and session rotation; these tests do not claim all covered behavior is Fork-exclusive.
- Do not revive the retired provider-owned manual session ledger or retain-on-new API.
- Official built-in-memory add/replace notification remains independent of `auto_retain`. The user explicitly rejected adding a new gate here.
- Update fixtures for upstream interfaces (bank write sets, runtime status objects, plain HTTP clients), not production code to satisfy obsolete mocks.

Merge decision:
- Preserve when: covered user behavior remains required.
- Drop when: the user has explicitly retired the covered behavior; record replacement/deletion in the sync ledger.
- Ask user when: a compatibility adaptation would change production behavior.

Verification:
```bash
HERMES_AGENT_ROOT=/path/to/hermes-agent python -m pytest hindsight-integrations/hermes/tests_hermes -q -o addopts=
```
Compare collected node IDs before/after, not only total counts.

- Upstream status: carried regression coverage and Fork integration seams.
- Last validated: upstream `6d8b096786df335fc2cc1e5d6662092f0e1b8694`; Fork merge candidate based on `3981e1d47ee1a4cdd2c50c368a5ab9f2089af585`.
- Feature docs: none — regression tests specify the compatibility surface.

## Historical / obsolete units

### Runtime dependency preparation

- ID: `hermes-runtime-dependency-preparation`
- Status: obsolete
- Depends on: none
- Source boundary: historical commit `3981e1d4`

Files / touchpoints:
- `hindsight-integrations/hermes/__init__.py` — now uses upstream warning-only dependency check.
- `hindsight-integrations/hermes/setup.py` — now byte-identical to upstream.
- `hindsight-integrations/hermes/dependencies.py` — deleted; historical path only.
- `hindsight-integrations/hermes/tests_hermes/test_pm_dependencies.py` — replaced preparation tests with no-runtime-install/setup-preservation checks.

Intent / invariants:
- Former behavior prepared a new PM environment on an outdated client and retained a legacy fallback. User explicitly accepted upstream dependency management instead.
- Dependencies are declared in upstream pyproject.toml; do not silently resurrect runtime PM sync, legacy installer or hindsight-all installation.

Merge decision:
- Preserve when: keeping this retirement notice, not the old implementation.
- Drop when: retirement notice is no longer needed to prevent accidental resurrection.
- Ask user when: proposing runtime dependency mutation again.

Verification:
```bash
python -m pytest hindsight-integrations/hermes/tests_hermes/test_pm_dependencies.py -q -o addopts=
```

- Upstream status: upstream dependency policy explicitly accepted.
- Last validated: upstream `6d8b096786df335fc2cc1e5d6662092f0e1b8694`; Fork merge candidate based on `3981e1d47ee1a4cdd2c50c368a5ab9f2089af585`.
- Feature docs: none — retirement boundary is complete here.
