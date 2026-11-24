#!/usr/bin/env bash
# Safe one-shot bridge from the historically local development commit to
# the published GitHub development branch, then upgrade ONLY the dev image.
# Run through: git fetch origin development; bash <(git show FETCH_HEAD:host/reconcile-and-upgrade.sh)
set -Eeuo pipefail
umask 077
fail() { echo "PANOLAB SOURCE UPDATE BLOCKED: $*" >&2; exit 12; }
say() { echo "PanoLab source update: $*"; }
[[ "$(id -u)" != 0 ]] || fail "Run as ordinary laptop user (never sudo)."
root="$(pwd -P)"
[[ -d "$root/.git" && -f "$root/panolab-install.sh" ]] || fail "Run from the PanoLab checkout root."
[[ "$(git rev-parse --show-toplevel)" == "$root" ]] || fail "Not at the checkout root."
[[ "$(git branch --show-current)" == development ]] || fail "Active branch must be development."
[[ -z "$(git status --porcelain --untracked-files=all)" ]] || fail "Local source changes exist; refusing overwrite."
remote_url="$(git remote get-url origin)"
case "$remote_url" in
  https://github.com/sirchuckalot/panolab-direct|https://github.com/sirchuckalot/panolab-direct.git|git@github.com:sirchuckalot/panolab-direct.git) ;;
  *) fail "origin is not the expected PanoLab GitHub repository";;
esac
target="$(git rev-parse --verify 'FETCH_HEAD^{commit}')" || fail "Fetch GitHub development first."
if [[ -n "${PANOLAB_EXPECTED_DEV_SHA:-}" ]]; then
  [[ "$target" == "$PANOLAB_EXPECTED_DEV_SHA" ]] || fail "Fetched head differs from published expected commit."
fi
[[ "$(git rev-parse --verify "refs/remotes/origin/development^{commit}")" == "$target" ]] ||
  fail "FETCH_HEAD and origin/development disagree."
old="$(git rev-parse HEAD)"
if [[ "$old" == "$target" ]]; then
  say "Local development is already at the published commit."
elif git merge-base --is-ancestor "$old" "$target"; then
  say "Fast-forwarding clean local development."
  git merge --ff-only "$target"
else
  # This one historical local commit is not on GitHub, but its FILE TREE
  # was reported to match the corresponding GitHub development milestone.
  # Verify that equality from actual Git objects before any ref movement.
  expected_local=f1ca3a66e48aa9fc5acf4827d0bcb779143aae51
  equivalent_remote=863715050d1894320590b47a3607543f1cf0a8eb
  [[ "$old" == "$expected_local" ]] || fail "Unexpected local history; not rebasing/resetting."
  git cat-file -e "$equivalent_remote^{commit}" ||
    fail "Cannot prove known GitHub equivalent milestone."
  git merge-base --is-ancestor "$equivalent_remote" "$target" ||
    fail "Expected milestone is not an ancestor of fetched development."
  git diff --quiet --exit-code "$old" "$equivalent_remote" ||
    fail "Local commit has different file content; refusing reconciliation."
  backup=panolab/backup-development-f1ca3a66
  if git show-ref --verify --quiet "refs/heads/$backup"; then
    [[ "$(git rev-parse "$backup")" == "$old" ]] ||
      fail "Backup branch already exists with another commit."
  else
    git branch "$backup" "$old"
  fi
  [[ "$(git rev-parse "$backup")" == "$old" ]] || fail "Backup ref did not preserve local commit."
  say "Verified identical historical source; preserved local commit under $backup."
  # The index and working tree are empty of changes and the old commit
  # is fully recoverable from the backup branch. Only now advance the
  # checked-out local development branch.
  git reset --hard "$target"
fi
[[ "$(git rev-parse HEAD)" == "$target" ]] || fail "Checkout did not reach requested development."
[[ -z "$(git status --porcelain --untracked-files=all)" ]] || fail "Checkout not clean after update."
say "SOURCE_UPDATE=PASS commit=$target"
say "Starting the explicitly requested single-image development upgrade."
bash "$root/panolab-install.sh" --upgrade-dev
