# CRM SRE Mac T04c / T05 / T06 source rework: evidence-limited review

## Scope and immutable baseline

- Mac-tested source SHA: `f4729dff88a6d67fd22fe9f772b82ec821bdcaeb`; do not revert to `8cad07af`.
- Runtime held fixed: Harness `0.2.2-rc.1`, Agent Teams `0.1.30`, model `zhipu-bigmodel/glm-5.3-flash`.
- User reports Mac T04c/T05/T06 acceptance `FAIL`. These historical results were not changed.
- No production connections, extra permissions, model calls, Windows VERIFY, merge or installation changes.

## Evidence availability

The execution account could read the pinned public GitHub source. Original Mac attachments **were not available** in this conversation or container: `HANDOFF.md`, `t05-recheck.json`, `t06-recheck.json`, `review-disposition.json`, `acceptance.md`, `results.json`, `environment.json`, `evidence-manifest.json`, the T04c/T05 event/tool/model-input timeline, the T06 request and both full replies, and `e401-followup.md`. No `/Volumes` file was opened.

Therefore this change does **not** independently attribute the original failures to an exact runtime event or identify action-by-action omissions in the real T06 answers. The user-provided summary is a diagnostic clue, not the missing primary record.

## Code-level findings and changes

**T04c/T05, receive-round completion:** the pinned lead rules already required sending the new material, a content ACK and confirmation that the receive round ended; they did not explicitly state that the actual trusted end evidence must appear in the specific captain model decision input that initiates `agent_teams_reassign_task`. The updated rules require a verified end event from that round bound to real task, attempt, member and material; any *equivalent trusted completion evidence* is acceptable. Mere ACK, send/readAt, queued notification or background log is not sufficient. Stale, cross-task and duplicate signals do not authorize reassign. Preserve the one-retry cap and block t2 until t1 really completes. The member prompt clarifies that the ACK does not assert runtime completion. This is a **prompt/contract guard only**, not an engine-level atomic pre-execution interceptor.

**T06, per-action review:** the baseline already prohibited production writes and required an action-review card. The lead prompt now requires each action *actually contained in the user's request* to receive a distinct evidence-bound assessment of its target, scope, prohibitions, human roles, impact, rollback and verification; generic safety disclaimers and empty headings do not suffice. The original T06 action list and responses are unavailable, so their particular omissions remain unverified; new instructions are not retroactive acceptance rules.

**Preserved boundaries:** no change to Agent Teams schema, member tool filter, production tool availability, the T02/T03 request count policy, T05 maximum one retry or downstream gating, model routing or approvals. Production output remains review-only.

## Tests and provenance

`tests/test_dsh.py` gains two **static prompt/source/render contract** tests; they do not simulate the real 0.1.30 scheduler or prove T04c/T05/T06 on a Mac. Existing tests must still pass. Build-generated `dsh/cordis.patch.yml`, `dsh/build-info.json`, and `prompt-bundles.lock` were updated from the canonical source. Confirm exact-commit CI logs for `check_dsh.py`, `validate_bundle.py --check-only`, full pytest suite, deterministic rebuild, `git diff --check` and clean status. If CI has not completed, mark `NOT_RUN`.

## Required next Mac acceptance

Use the new exact code SHA in an **independent worktree**, separate test profile and isolated Harness session, obtaining a fresh staged human approval. Preserve the existing FAIL workspace and archives. Reconstruct each T04c/T05 event sequence using the actual `reassign` decision-model input and all equivalent trusted end events: ACK, end signal generated/queued, end evidence consumed, invocation, tool acceptance, new attempt, new material, t1 completion and t2 release. Replay the original T06 request exactly and evaluate both outputs against the established rubric without adding retrospective criteria. Keep E401 follow-up material out of the initial failed-run session.

Mac acceptance `NOT_EVALUATED`, Windows VERIFY `BLOCKED`, MMX review `FAIL` and ZCode review `NOT_EVALUATED` until new evidence says otherwise.
