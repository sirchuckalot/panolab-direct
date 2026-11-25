# GitHub publishing and laptop push authentication

**Record:** PLR-GIT-001 | **Date:** 2026-11-23 Pacific | **Status:** **OWNER_AUTHENTICATION_ACCEPTED**. Owner-private, fine-grained GitHub push credential configured; scoped mount, rebuilt repository gateway and authenticated dry-run succeeded. Independent live `repo_push` returned exit code 0 (`Everything up-to-date`). This documentation update is the deliberately small real-commit push qualification.

## Two working paths, not two GitHub repositories

PanoLab Direct's GitHub repository is [sirchuckalot/panolab-direct](https://github.com/sirchuckalot/panolab-direct). GitHub's **default branch is `main`**, an accepted software baseline, while all current Rescue implementation work is on **[`development`](https://github.com/sirchuckalot/panolab-direct/tree/development)**. **Historical counts:** at `04632b4`, GitHub `main` had 44 tracked files
and `development` had 77. These are **not current file counts**; the
`development` tree now includes thousands of selective, versioned
third-party source files and vendor/toolchain test recipes. Compare
current branches via Git rather than relying on the dated counts.

This project has used the **connected GitHub integration** for real server-side Git commits and non-force ref updates, followed by fast-forward synchronization of the laptop checkout. That method is already authenticated and works. The historical failure `fatal: could not read Username for 'https://github.com': terminal prompts disabled` affected the **separate Git push operation inside the existing laptop `repo-git` gateway** before owner credential setup. It has since been resolved. It was never evidence that GitHub commits had not been published.

**Migration notice:** The source-visible `third_party/` snapshots are now
selected by `projects/rescue/project.toml`. The original statement below
describes the **pre-migration image bootstrap strategy**, not how
the new Rescue project resolves source.

Historically this repository did **not vendor the entire LiteX/Migen/LiteEth/LiteSPI codebases**: the [Docker development recipe](../docker/modern/Dockerfile) clones pinned upstream source revisions specified in [the lock](../docker/modern/litex-upstream.lock.json). Their full checkout appears inside the modern image at `/opt/panolab/litex/upstream/`, not as thousands of duplicated GitHub files. Our own G2 source is under [`boards/pano_g2_rev_b/`](../boards/pano_g2_rev_b/) and the recovery architecture is [`specs/PANOLAB_RESCUE_V1.md`](../specs/PANOLAB_RESCUE_V1.md).

## Dedicated write credentials for the existing repository gateway

No new general development image, Docker service, GitHub repository or privileged container is required. `git` is already installed in `repo-git` (`docker/control/Repo.Dockerfile`) and in the modern development container. The modern development container intentionally has no `/repo/.git` or host Docker socket and must **not** receive GitHub write credentials.

The host's ignored, owner-private file is:
```text
docker/private/github-git-auth/github-push-token
```
The containing directory is mode **0700**, token file **0600**. The opt-in [Compose overlay](../docker/compose.git-push.yaml) mounts **only that directory** read-only at `/run/panolab-git-auth` in the existing `repo-git` service. The gateway's normal `/repo/docker/private` path remains masked by an empty Docker volume, preventing access to the other project secrets. No GitHub credential goes in `docker/.env`, `~/.gitconfig`, a remote URL, git command-line argument, Dockerfile, test log or chat.

The helper [`docker/control/github_askpass.py`](../docker/control/github_askpass.py) is enabled **only** for the gateway's allowlisted push. It reads the token directly from the read-only mount. The gateway continues to verify the expected GitHub origin and clean working tree, refuses force pushes, and permits direct pushes **only** to `refs/heads/development`. Remote branch protections and GitHub's normal permissions still apply.

## Completed one-time owner setup (repeat only if credential rotation is required)

1. In your browser, use [GitHub fine-grained personal access tokens](https://github.com/settings/personal-access-tokens/new). Choose owner **`sirchuckalot`**, access to **only `panolab-direct`**, repository permission **Contents: Read and write**, and a finite expiration. Metadata read permission is added automatically. Do not select broad organization/all-repository scopes.
2. From the local checkout, run the one command below as your ordinary laptop user **without sudo**. It will prompt for the token *without echoing it*, write it to the ignored private file, rebuild **only** the existing `repo-git` image and recreate **only** its service with the opt-in read-only mount. No ISE, dev-container or FPGA changes.
3. The script validates the mount scope and executes `git push --dry-run origin HEAD:refs/heads/development` through the credential helper. It does **not** publish a new commit. The owner completed this setup successfully, and the independent live gateway operation then reported `Everything up-to-date` with exit code 0.

```bash
cd "$HOME/Projects/repos/panolab-direct-main" && bash ./panolab-install.sh --enable-github-push
```

**Never paste a token into ChatGPT or send `github-push-token` file contents.** If it expires, revoke it in GitHub and use the same owner-local renewal workflow after inspecting the existing private file; the script deliberately refuses silently overwriting an existing credential.

## Completed local prerequisites and remaining work

**Historical setup acceptance (2026-11-23):** repository
`development` synchronization, unified modern image rebuild
(`--upgrade-dev`), rootless Buildx installation and exact old rollback
cleanup (`--finalize-maintenance`) were verified with six active
services at that time. Those commands **must not be rerun merely to
republish Git**, and the old six-service count is not the later ISE
development configuration. See the [current baseline](ENGINEERING_BASELINE.md).

**GitHub setup completed:** the owner executed `--enable-github-push`, the Buildx-powered rebuild and replacement of **only** the existing repository gateway succeeded, `GITHUB_SECRET_MOUNT_SCOPE=PASS`, `GITHUB_SECRET_AND_ASKPASS=PASS`, and `GITHUB_PUSH_AUTH=PASS` were reported. An independent PanoLab `repo_push` completed with `Everything up-to-date` and no secret exposure. This document serves as the reviewed source change for an actual local commit/push qualification; confirm the resulting GitHub branch SHA following publication.

**Updated qualification boundaries:** genuine licensed ISE 14.7 vendor
implementation and **two unattended disposable vendor installs** now
pass on the provisioned rootless laptop. A later named G2 diagnostic ISE timing pass is documented in the [Rescue checkpoint](../projects/rescue/experiments/iteration-15/README.md). Stock Ethernet identity and backup passed separately. Physical Rescue boot and A/B/ICAP recovery remain unqualified. The scoped credential mount
continues to authorize only non-force pushes of `development`; it
never authorizes changes to `main`. Follow the
[current engineering handoff](ENGINEERING_BASELINE.md) and
[temporary-component register](TEMPORARY_COMPONENTS.md) for the latest
state.

The gateway now recognizes the approved `research/` source root (commit `029141f`). It retains explicit-file commits (maximum 20 paths) and existing parent-directory requirements; a larger atomic milestone needs owner-side local staging and commit before the scoped push.

The connected GitHub integration remains a valid publishing path regardless of whether owner-local direct Git push is enabled.
