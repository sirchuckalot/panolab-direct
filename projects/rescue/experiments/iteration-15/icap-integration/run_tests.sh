#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
build_dir=$(mktemp -d ./.icap-tests.XXXXXX)
trap 'rm -rf -- "$build_dir"' EXIT
mkdir "$build_dir/tmp"
export TMPDIR="$PWD/$build_dir/tmp"
iverilog -g2012 -Wall -s tb_icap_launch_interlock -o "$build_dir/test.vvp" \
    ../icap/icap_spartan6_stub.v spartan6_icap.v icap_launch_interlock.v \
    tb_icap_launch_interlock.v
vvp "$build_dir/test.vvp"
