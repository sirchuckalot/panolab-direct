# Managed Codex jobs

Use Python 3.9+ in the existing Linux development container. The deployed
launcher lives at `/workspace/codex-job-control/launcher.py` and uses the
`jobs/` directory next to the resolved script. Each start requires an absolute
workdir, a UTF-8 prompt, and a JSON prerequisite manifest. Declare every
required input and tool for the assigned task and pin expected SHA-256 values
when the task requires a specific file revision.

```json
{
  "files": [{"path": "/repo/AGENTS.md", "sha256": "<replace with expected lowercase SHA-256>"}],
  "directories": ["/repo/docs"],
  "executables": ["python3"]
}
```

The manifest permits up to 64 KiB and 128 entries per array. All three arrays
are required. Use explicit empty arrays only when the task has no additional
requirements of that kind. Paths must be absolute within `/repo` or
`/workspace`. Use approved, nonprivate paths without symlinks. For directories
the launcher checks accessibility and identity. List revision-critical files
individually to verify their contents. Executable names are resolved through
absolute entries on the inherited PATH. Tool checks inspect executable
identity and permissions without running shell probes. Codex is always
required. The launcher always reads the current policy from
`/repo/AGENTS.md`.

```bash
JOB_ID=$(python3 launcher.py start --workdir /workspace/codex-job-control \
  --prompt-file /workspace/codex-job-control/my-prompt.txt \
  --prerequisites /workspace/codex-job-control/my-prerequisites.json)
python3 launcher.py status "$JOB_ID"
python3 launcher.py result "$JOB_ID"
python3 launcher.py tail "$JOB_ID" --bytes 8192
```

On successful admission, `start` prints the job ID and returns once the
detached supervisor has spawned. The supervisor rechecks admission inputs and
the stored instructions before starting Codex, then waits without a runtime
timeout. Keep launch inputs available through that recheck. The job keeps the
exact canonical policy bytes at the start of its stdin snapshot and records
`policy_sha256`. Failed initial admission exits 2 with an
`INFRASTRUCTURE_BLOCKED` diagnostic on stderr and spawns nothing. For an
existing blocked job, `status` and `result` print the diagnostic to stderr,
retain the job JSON on stdout, and exit 2. Diagnostics identify the failed
resource, error, last step, and stopped work.

## Job records

The existing job directories, combined `codex.log`, prompt snapshot, supervisor
lock, and atomic `status.json` remain in use. `result` includes the relative
log filename and `tail` creates a private snapshot. Historical terminal
records remain readable with their original fields and logs.

| State | Execution meaning |
| --- | --- |
| `running` | Supervisor holds the lock and a terminal record is pending. |
| `succeeded` | Codex exited with code 0. |
| `failed` | Codex exited nonzero or was terminated by a signal. Negative codes denote signals. |
| `interrupted` | The supervisor or Codex could not start, including failed readmission. |
| `lost` | The supervisor lock was released before a terminal record appeared. |

The Codex CLI writes the final assistant message to `final-message.txt` using
`--output-last-message`. The last line must be a standalone JSON object.
`{"outcome":"COMPLETED"}`, `{"outcome":"ENGINEERING_BLOCKED"}`, and
`{"outcome":"PASS"}` populate `engineering_outcome`. Workers use `PASS` only
for an assigned gate with verified acceptance criteria. Explicit infrastructure
reports use a single line in this format:

```json
{"outcome":"INFRASTRUCTURE_BLOCKED","resource":"/repo/example","error":"required file is missing","last_step":"read policy","stopped_work":"dependent verification"}
```

A missing or malformed final verdict blocks acceptance, including when
`state` is `succeeded`. Review the execution result, infrastructure verdict,
and actual evidence independently before accepting an engineering outcome.
The reporting convention depends on workers following the canonical policy at
runtime. A lost supervisor can leave its Codex process running. Inspect the
affected job through the approved interface before restarting it. Each job
uses its own lock and files.

## Verification and activation

Run candidate tests with `python3 -B -m unittest -v test_launcher`. These use a
synthetic Codex executable and temporary fixtures offline.

ChatGPT independently reviews and activates through the existing approved
deployment interface. Confirm the job store, launcher and installed Codex CLI
are accessible, including support for `--output-last-message`. Pause submissions
and drain all jobs. Record the current source revision, launcher and startup
pointer hashes, modes and owners. Preserve the current launcher and startup
shim in approved owner storage.

Publish and fast-forward the clean laptop checkout to the reviewed revision.
Verify the exact bytes of `/repo/AGENTS.md`. Atomically replace the deployed launcher
and `/codex-auth/AGENTS.md` with the verified launcher and staged
`startup-AGENTS.md`, preserving ownership and modes. Keep `jobs/` in place.
Block new submissions throughout this sequence.

Run a read-only canary through managed `start`, `status` and `result`.
Check its reported SHA-256 against the actual root file, job `policy_sha256`
and exact injected bytes. Verify the explicit canary verdict and record the
evidence before resuming submissions.

If activation fails, keep submissions paused and preserve the job store, owner
work and failure evidence. Diagnose the failure and plan recovery from the
current system state through the approved maintenance process. Verify the
normal-path canary before resuming submissions.
