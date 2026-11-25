CC ?= cc
RV32_CC ?= riscv64-unknown-elf-gcc
STRICT_C11 = -std=c11 -Wall -Wextra -Wpedantic -Werror
BOOT_POLICY_HEADER = ../bios-integration/firmware/rescue_boot_policy.h

.PHONY: all check test rv32
all: check
check: test rv32

test: build/test_rescue_journal
	./build/test_rescue_journal

rv32: build/rescue_journal.rv32.o

build/test_rescue_journal: rescue_journal.c rescue_journal.h test_rescue_journal.c $(BOOT_POLICY_HEADER) Makefile | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(STRICT_C11) rescue_journal.c test_rescue_journal.c -o $@

build/rescue_journal.rv32.o: rescue_journal.c rescue_journal.h Makefile | build
	$(RV32_CC) $(STRICT_C11) -march=rv32i -mabi=ilp32 -ffreestanding -c rescue_journal.c -o $@

build:
	mkdir -p $@
