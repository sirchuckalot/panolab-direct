#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
here="$PWD"
repo=${PANOLAB_REPO:-/repo}
prefix=${PANOLAB_TOOLCHAIN_PREFIX:-/opt/panolab/litex}
window=${1:-60}
if [[ ! "$window" =~ ^([1-9]|[1-5][0-9]|60)$ ]]; then
    echo "Usage: ./build.sh [1..60]" >&2
    exit 2
fi
mkdir -p "$here/evidence"
out=$(mktemp -d "$here/build-s${window}.XXXXXX")
mkdir "$out/tmp"
export TMPDIR="$out/tmp"
export PANOLAB_RESCUE_OUT="$out"
export PYTHONDONTWRITEBYTECODE=1
python3 "$repo/shared/source_registry.py" run --project projects/rescue/project.toml -- \
    bash -c 'cd -- "$1"; exec "$2" "$1/rescue_soc.py" --lab-mac 02:00:00:00:00:01 --autoboot-seconds "$3" --generate --out "$4"' \
    _ "$here" "$prefix/venv/bin/python3" "$window" "$out" 2>&1 | tee "$out/build.log"
python3 "$here/verify_build.py" "$out" "$window" | tee "$out/verification.log"
printf 'Build output %s\n' "$out"
