#!/usr/bin/env bash
# PanoLab host CLI Buildx bootstrap: ordinary owner, no sudo/host apt.
# Docker CLI plugin only; no new Docker images, services or daemon changes.
set -Eeuo pipefail
umask 077
die() { echo "PANOLAB BUILDX BLOCKED: $*" >&2; exit 9; }
say() { printf 'PanoLab Buildx: %s\n' "$*"; }
[[ "$(id -u)" != 0 && "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] ||
    die "requires ordinary Linux x86_64 owner"
command -v docker >/dev/null && command -v curl >/dev/null && command -v sha256sum >/dev/null ||
    die "requires Docker CLI, curl, sha256sum"
version="v0.36.1"
sha="48af8a397ebd60178778bf63611dbcebe5f5e7a9be90eb9147b24b9587455778"
source="https://github.com/docker/buildx/releases/download/$version/buildx-$version.linux-amd64"
# Preserve an already working system/user Buildx. Never replace unknown files.
if docker buildx version >/dev/null 2>&1; then
    say "Existing CLI plugin works: $(docker buildx version)"
else
    parent="$HOME/.docker/cli-plugins"
    target="$parent/docker-buildx"
    [[ ! -L "$parent" && ! -L "$target" ]] ||
        die "CLI plugin directory or executable is a symlink"
    mkdir -p "$parent"
    chmod 0700 "$parent"
    if [[ -e "$target" ]]; then
        [[ -f "$target" && "$(sha256sum "$target" | awk '{print $1}')" == "$sha" ]] ||
            die "Unrecognized Docker Buildx plugin already exists: $target"
        chmod 0755 "$target"
    else
        temp="$(mktemp "$parent/.docker-buildx.XXXXXXXX")"
        trap 'rm -f "$temp"' EXIT
        say "Installing checksum-pinned Docker CLI Buildx $version in owner home only."
        curl --fail --location --silent --show-error --retry 3 "$source" --output "$temp"
        echo "$sha  $temp" | sha256sum --check --status ||
            die "Official Buildx download SHA-256 mismatch"
        chmod 0755 "$temp"
        mv -n "$temp" "$target"
        trap - EXIT
        [[ -f "$target" && "$(sha256sum "$target" | awk '{print $1}')" == "$sha" ]] ||
            die "Buildx target was changed concurrently"
    fi
fi
docker buildx version >/dev/null || die "Buildx is not functional"
# The default 'docker' driver uses the existing rootless Engine's BuildKit.
# Do NOT create a docker-container BuildKit builder (extra daemon/image).
say "BUILDX_PLUGIN=PASS $(docker buildx version)"
