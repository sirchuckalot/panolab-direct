# PanoLab mandatory agent execution and hard-stop policy

**Authority:** owner-directed engineering process. Applies equally to ChatGPT (systems engineering, orchestration, independent verification) and Codex (implementation, integration, engineering documentation and tests). This is a required operating rule, not a suggestion or a product design revision.

## Admission before work

At every new session/job and before each dependent gate, identify the exact task authority, required canonical source files/directories, revision, tools, permissions, environment and evidence. Read the current policy and the task's actual controlling documents; check required paths and access via their approved interfaces, the expected revision, tool readiness and result retrieval. Check applicable dependencies before consuming substantial compute or editing. Use the canonical source, not chat summaries, stale copies or unverified substitutes. A deliberately limited mount is not authority to ignore a required input. If a required resource is unavailable, STOP before dependent work. Do not access private/unauthorized data to satisfy admission.

## HARD STOP — execution infrastructure

A missing, inaccessible, unreadable, truncated, stale or unverifiable REQUIRED specification/source/directory/dependency/artifact; wrong revision or unavailable mount; permission or authentication failure; missing required executable/tool; unexpected execution timeout, lost job, transport/RPC failure, malformed result, insufficient tool output or other framework failure that prevents the prescribed engineering action or verification is an **INFRASTRUCTURE_BLOCKED** condition. This includes a required file or operation that an agent cannot reach because of the approved interface. It is not permission to infer, substitute, skip or route around the failure.

On first detection, stop the affected job and its dependent work immediately. Preserve existing files, logs and completed evidence safely; do not launch additional dependent tests, builds, searches, edits, retries or replacement paths just to continue. Return the blocker as the first and most prominent result, not a footnote at the end. Do not report PASS or partial completion as acceptance. Report:

- Status: INFRASTRUCTURE_BLOCKED; affected task/gate and job ID if known.
- Exact required resource or operation, canonical path/interface, expected behavior, observed error (redacted where needed), and the last completed step.
- What work stopped, preserved evidence, and any independent work still running that is demonstrably unaffected.
- Smallest proposed root-cause correction, relevant permission/approval boundary, and exact normal-path retest needed before resumption.

Codex must end the affected session promptly and return that status to ChatGPT. ChatGPT must surface it to the owner immediately when observed, not continue the dependent engineering task. ChatGPT may diagnose and orchestrate the narrowly scoped infrastructure repair when authorized, including via the existing owner-trusted maintenance process; Codex may be assigned a separate repair job with its own verified prerequisites. Do not weaken access controls, invent substitute data, use copied sources as a workaround, silently skip a required test, or use a different execution path merely to avoid the broken normal interface. Preserve unrelated independent jobs only if their inputs and environment are unaffected and explicitly report their state. After the root cause is corrected, verify the original required operation through the intended interface, then restart the affected work from its admission check. No automatic approval of physical operations or security changes.

## Distinguish engineering findings

A validly executed test that exposes a product defect, incomplete product implementation, failed design/qualification criterion or genuine product architecture decision is an engineering finding (ENGINEERING_BLOCKED when it prevents the gate), not an infrastructure access failure. Continue bounded diagnosis and corrective iterations within the assigned engineering scope and approved resources, but never silently weaken requirements or claim a gate PASS. Escalate an actual owner decision. Expected negative-test failures and explicitly non-required future capabilities are not infrastructure failures. A planned test venue may differ by design only if declared up front, approved and appropriate for that gate; never change venue after a failure just to conceal it.

## Session enforcement and reporting

The root AGENTS.md links this policy; the canonical container-readable source is /repo/docs/AGENT_EXECUTION_POLICY.md. Before invoking Codex, the orchestrator must load the current policy and make it part of the session instructions, verify all declared required inputs or report INFRASTRUCTURE_BLOCKED, and record the policy revision with the job. No unguarded engineering sessions. A worker's process exit code is not a gate verdict. Record explicit engineering outcome, execution outcome and infrastructure blockers separately. A missing required final verdict or inaccessible report is itself an infrastructure blocker for acceptance. Before claiming completion, independently verify the actual normal-path operation and relevant evidence. Do not imply that policy text alone guarantees automatic detection of every possible runtime error; implement and test admission and reporting controls, and require both agents to honor the policy.

This policy does not change product scope, protected identity, authorization, licensing, physical-operation approval or source publication boundaries.
