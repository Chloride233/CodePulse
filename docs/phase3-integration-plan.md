# Phase 3 Archive and Mainline Integration Plan

Status: proposed technical decision, Git operations not yet performed
Archive anchor: `5fbc52789558a71b812f8d494a0fb885c63a626e`
Mainline base: `4a30ca5c15b660a03942883836364b32b1623535`

## Decision

Do not merge or cherry-pick the Phase 3 branch wholesale.

The branch contains 57 commits, 85 changed files, and 8,739 inserted lines relative to
the current remote mainline. Its largest additions implement an experiment-specific
SWE-bench runner, rule-based candidate materialization, Phase 3 CLI commands, and a
custom Agent controller. Those responsibilities overlap maintained open-source
projects and are not CodePulse's differentiated value.

Preserve the complete branch as a research archive. Build a clean integration branch
from the mainline and copy only the status, final evidence, and generic behavioral
requirements listed below.

## Preserve in the Archive Only

The following code and intermediate artifacts remain reachable through the archive
anchor but do not enter the supported mainline:

- `codepulse/benchmark/swebench_runner.py` and its tests;
- `codepulse/evolve/candidate.py` and candidate materialization commands;
- Patch Guard changes in `codepulse/agent/real_agent.py`;
- Phase 3 training, evolution, screen, retry, image, and pricing CLI commands;
- hand-authored `skillopt-v1` through `skillopt-v5` Agent profiles;
- intermediate training cohorts, manifests, traces, and dated design specifications;
- the evolving `docs/phase3-evolution-protocol.md` runbook, whose commands reference
  archived intermediate files;
- local proxy and image-transport fixes that only supported the archived experiment.

The repository tool-contract change at `80140b8` is not selected automatically. Its
bounded reads and exact edit behavior are reasonable correctness fixes, but they belong
to the legacy `RealAgent`. Reconsider them only if that backend remains in the supported
public surface after an external Agent backend is adopted.

## Publish on the Mainline

### Current status and policy

- `README.md` positioning and evidence boundary;
- `AGENTS.md` build-or-buy rule and phase progression rule;
- `docs/project-status.md`;
- historical notices in `docs/PRD.md` and `docs/architecture.md`;
- this archive and integration plan.

### Final Phase 3 evidence

Copy these small, immutable evidence groups with their original contents and paths:

1. Complete V4 Flash paired comparison:
   - `experiments/phase3-swebench-evolution-v4/manifest.json`
   - `experiments/phase3-swebench-evolution-v4/evidence.json`
   - `experiments/phase3-swebench-evolution-v4/phase3-report.md`
2. Final same-model Patch Guard screen:
   - `experiments/phase3-swebench-screen-v3/manifest.json`
   - `experiments/phase3-swebench-screen-v3/candidate-provenance.json`
   - `experiments/phase3-swebench-screen-v3/evidence.json`
   - `experiments/phase3-swebench-screen-v3/screen-report.json`
3. Final V4 Pro screen:
   - `experiments/phase3-strong-model-screen-v1/manifest.json`
   - `experiments/phase3-strong-model-screen-v1/profile-provenance.json`
   - `experiments/phase3-strong-model-screen-v1/aborted-evidence-v1.json`
   - `experiments/phase3-strong-model-screen-v1/evidence.json`
   - `experiments/phase3-strong-model-screen-v1/screen-report.json`

These groups total less than 50 KiB. They preserve the final claims, configuration,
provenance, environment failure, and rejection decisions without restoring large raw
results or Docker assets.

Historical evidence files must remain byte-for-byte unchanged. The current cleanup
boundary belongs in `docs/project-status.md`, not in rewritten historical JSON.

## Reimplement as Generic Product Behavior

Do not cherry-pick commits `b1dca50`, `0f5ecbc`, `b7d92cb`, `651376d`, or `9e6b712`
verbatim. Their useful behavior should be expressed in the Phase 4 offline demo without
Phase 3 protocol names, fixed `k=3`, SkillOpt provenance versions, or one experiment's
budget schema.

The retained behavior is:

- reject duplicate, missing, extra, or unpaired `(task_id, repetition)` records;
- compare exactly one baseline and one candidate over a declared task set;
- derive pass@k and pass^k from the declared repetition count;
- classify improvement, regression, persistent failure, and stable success per task;
- reject a candidate with no positive stable gain, any task regression, invalid cost,
  or a configured resource-budget violation;
- render metrics, attribution, Gate reasons, representative cases, and evidence links.

Prefer existing mainline primitives such as `align_exact()` and `summarize_pilot()`.
Add the smallest pure reporting function needed by the offline demo rather than another
experiment runner or evolution abstraction.

## Mainline Integration Sequence

1. Preserve the archive anchor with a remote branch or annotated tag after explicit
   approval for the external write.
2. Create a clean branch from the current remote mainline.
3. Apply the status and policy documents from the current working tree.
4. Copy the three final evidence groups and verify their original hashes.
5. Run documentation checks and the existing mainline CI before adding Demo code.
6. Implement the generic offline report path in a separate change with fixture-only
   tests and no model, Docker, dataset download, or network dependency.

## Stop Conditions

Stop and review the plan again if integration requires any of the following:

- merging the full Phase 3 branch;
- restoring raw `results/phase3/` or Docker images;
- adding mini-SWE-agent, GEPA, SWE-ReX, or another dependency before the offline Demo;
- preserving a Phase 3-specific command solely to make an old reproduction command
  executable;
- changing historical evidence to make it match the cleaned local filesystem;
- starting a paid model call or a new candidate experiment.

## Verification Bar

The archive step is complete only when the full Phase 3 history is remotely reachable.
The evidence step is complete only when selected file hashes match the archive anchor.
The product extraction step is complete only when the generic offline Demo passes CI
from committed fixtures and produces no network, model, or Docker activity.
