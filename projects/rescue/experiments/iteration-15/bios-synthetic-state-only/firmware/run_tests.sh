#!/bin/sh
set -eu

cd "$(dirname "$0")"
build_dir=$(mktemp -d ./.boot-policy-build.XXXXXX)
trap 'rm -rf "$build_dir"' EXIT
trap 'exit 1' HUP INT TERM

build_strict() {
    "$@" -std=c99 -pedantic-errors -Wall -Wextra -Werror -Wconversion \
        -Wshadow -Wstrict-prototypes -Wmissing-prototypes
}

build_strict "${CC:-cc}" -ffreestanding -c rescue_boot_policy.c \
    -o "$build_dir/native.o"
build_strict "${CC:-cc}" test_rescue_boot_policy.c "$build_dir/native.o" \
    -o "$build_dir/test"
"$build_dir/test"

build_strict "${CC:-cc}" test_rescue_diag.c rescue_diag.c -o "$build_dir/test_diag"
"$build_dir/test_diag"

riscv_cc=${RISCV_CC:-}
if [ -z "$riscv_cc" ]; then
    for candidate in riscv64-unknown-elf-gcc riscv32-unknown-elf-gcc riscv64-linux-gnu-gcc; do
        if command -v "$candidate" >/dev/null 2>&1; then
            riscv_cc=$candidate
            break
        fi
    done
fi
if [ -n "$riscv_cc" ]; then
    build_strict "$riscv_cc" -march=rv32im -mabi=ilp32 -ffreestanding \
        -c rescue_boot_policy.c -o "$build_dir/rv32.o"
    printf 'RV32 freestanding object compiled with %s\n' "$riscv_cc"
else
    printf 'RV32 freestanding compile skipped (no RISC-V compiler found)\n'
fi
