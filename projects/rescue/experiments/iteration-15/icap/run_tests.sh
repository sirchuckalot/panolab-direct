#!/bin/sh
set -eu
cd "$(dirname "$0")"
build_dir=$(mktemp -d "$PWD/.icap-test.XXXXXX")
trap 'rm -rf "$build_dir"' EXIT
trap 'exit 1' HUP INT TERM

iverilog -g2012 -Wall -s tb_spartan6_icap -o "$build_dir/icap.vvp" \
    spartan6_icap.v icap_spartan6_stub.v tb_spartan6_icap.v
vvp "$build_dir/icap.vvp"

expect_parameter_failure() {
    if iverilog -g2012 -s spartan6_icap -o "$build_dir/invalid.vvp" \
        "$@" spartan6_icap.v icap_spartan6_stub.v >"$build_dir/invalid.log" 2>&1; then
        echo "FAIL: invalid parameter selection elaborated" >&2
        exit 1
    fi
    if ! rg -q 'Unknown module type: ICAP_requires_explicit_24_bit_addresses_and_8_bit_opcode' \
        "$build_dir/invalid.log"; then
        cat "$build_dir/invalid.log" >&2
        exit 1
    fi
}

expect_parameter_failure -Pspartan6_icap.FALLBACK=0 -Pspartan6_icap.READ_OPCODE=0
expect_parameter_failure -Pspartan6_icap.TARGET=0 -Pspartan6_icap.READ_OPCODE=0
expect_parameter_failure -Pspartan6_icap.TARGET=0 -Pspartan6_icap.FALLBACK=0
expect_parameter_failure -Pspartan6_icap.TARGET=16777216 -Pspartan6_icap.FALLBACK=0 \
    -Pspartan6_icap.READ_OPCODE=0
expect_parameter_failure -Pspartan6_icap.TARGET=0 -Pspartan6_icap.FALLBACK=0 \
    -Pspartan6_icap.READ_OPCODE=256
echo "PASS: missing and out-of-range parameters rejected at elaboration"
