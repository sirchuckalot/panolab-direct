CC ?= cc
RV32_CC ?= riscv64-unknown-elf-gcc
STRICT_C11 = -std=c11 -Wall -Wextra -Wpedantic -Werror
JOURNAL = ../journal-core
SOURCES = rescue_trial.c $(JOURNAL)/rescue_journal.c
HEADERS = rescue_trial.h $(JOURNAL)/rescue_journal.h
RV32_FLAGS = -march=rv32i -mabi=ilp32 -ffreestanding

.PHONY: all check test rv32
all: check
check: test rv32

test: build/test_rescue_trial
	./build/test_rescue_trial

rv32: build/rescue_trial.rv32.o build/rescue_journal.rv32.o

build/test_rescue_trial: $(SOURCES) test_rescue_trial.c $(HEADERS) Makefile | build
	$(CC) $(CPPFLAGS) -I$(JOURNAL) $(CFLAGS) $(STRICT_C11) $(filter %.c,$^) -o $@

build/%.rv32.o: %.c $(HEADERS) Makefile | build
	$(RV32_CC) -I$(JOURNAL) $(STRICT_C11) $(RV32_FLAGS) -c $< -o $@

build/rescue_journal.rv32.o: $(JOURNAL)/rescue_journal.c $(HEADERS) Makefile | build
	$(RV32_CC) -I$(JOURNAL) $(STRICT_C11) $(RV32_FLAGS) -c $< -o $@

build:
	mkdir -p $@
