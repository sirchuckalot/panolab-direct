# Low-noise development and GitHub workflow

**Design → experiment locally → verify locally → review → one working
commit → publish once.** GitHub is source control and review, not
the default laboratory. The laptop's rootless Docker containers run
development, build, simulation and host integration tests.

## Before a commit

1. Check live GitHub refs and `repo_status`; identify the active
   checkout, branch and ancestry. Define the smallest useful deliverable
   and acceptance tests.
2. Work in `/workspace`, a disposable local checkout or an approved
   isolated laptop container. Keep intermediate experiments, logs,
   generated artifacts and failures **uncommitted and unpushed**.
3. Iterate on local failures until the intended behavior works. Run
   the relevant source checks, then local integration/hardware gates
   appropriate to the change and available authorizations.
4. Inspect the complete final diff for correctness, private material
   and unrelated changes; record test evidence and explicit PENDING
   gates. If the essential gate has not run, don't publish as verified.
   Ask before publishing a marked draft.
5. Make **one focused commit for the working change**, with a useful
   message, and publish once using the GitHub integration's expected
   parent SHA. One commit is not a goal by itself; later independently
   tested work warrants its own commit.
6. Confirm the remote SHA. Use `repo_sync` only when the current
   laptop checkout is clean, on a compatible branch and **shares
   ancestry** with GitHub. Never reset or force-push to conceal drift.

Avoid commit/push per attempted fix, per log inspection or per CI
permutation. Private local checkpoints for long work are fine, but
published history should communicate verified engineering progress.
Do not produce unrelated sweeping commits merely to minimize count.

## When CI is legitimate

Short, deterministic unit/lint/static/security checks, clean-environment
builds or narrow PR quality gates are normal uses of GitHub Actions
when they add evidence. Define a specific question, runner constraints,
timeout and resource budget. CI **does not** verify the owner's rootless
Docker Engine, local MCP/tunnel, licensed ISE or physical G2 hardware.

On CI failure, read the logs, reproduce and fix locally, re-run the
local acceptance test, then publish a correction only when it passes.
Do not repeatedly change runner settings and push experimental commits.
This repository intentionally has no Actions workflows by default.

## Clean-history and laptop safety

The reviewed `main` snapshot has unrelated ancestry to the laptop's
retained older `development` checkout. That old checkout and its
running Git gateway must **not** be automatically reset or merged by
the routine source workflow. Reconciliation requires a separate safe
local migration, not a CI workaround. Never overwrite private files,
force-update shared refs or disrupt active authenticated services.
