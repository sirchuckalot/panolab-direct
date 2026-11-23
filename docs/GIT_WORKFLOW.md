# GitHub source workflow

GitHub is a **source and review** service, not the Docker installation
or test executor. The laptop's rootless development container runs
builds and tests; GitHub stores the reviewed recipe.

For agent-owned changes:
1. Read the live local and GitHub HEAD; confirm the worktree is clean.
2. Make a reviewed change and test locally inside PanoLab.
3. Publish with the connected GitHub integration, using a non-force,
   expected-parent update.
4. Use PanoLab `repo_sync` to fetch/fast-forward the existing laptop
   checkout. Verify equal SHA and no uncommitted files.

Do not create a separate local commit when the same patch is about to
be committed independently through the GitHub integration; that
creates divergence. If either side has unique edits, preserve them
and reconcile explicitly without resets or force-push.

`main` is the reviewed release snapshot. Use temporary branches
for review when appropriate; never rewrite or delete shared refs
without explicit owner approval. The private source mounts used
by the active lab must remain intact while reviewing a branch.
