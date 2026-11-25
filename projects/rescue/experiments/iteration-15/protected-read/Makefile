CC ?= cc
RV32_CC ?= riscv64-unknown-elf-gcc
STRICT_C11 = -std=c11 -Wall -Wextra -Wpedantic -Werror
SOURCES = rescue_protected_read.c ../storage-core/rescue_storage.c \
          ../identity-record/identity_record.c ../journal-core/rescue_journal.c
HEADERS = $(SOURCES:.c=.h)

.PHONY: all check test rv32
all: check
check: test rv32

test: build/test_rescue_protected_read
	./build/test_rescue_protected_read

rv32: build/rescue_protected_read.rv32.o

build/test_rescue_protected_read: $(SOURCES) $(HEADERS) test_rescue_protected_read.c Makefile | build
	TMPDIR=$(CURDIR)/build $(CC) $(CPPFLAGS) $(CFLAGS) $(STRICT_C11) $(SOURCES) test_rescue_protected_read.c -o $@

build/rescue_protected_read.rv32.o: $(SOURCES) $(HEADERS) Makefile | build
	TMPDIR=$(CURDIR)/build $(RV32_CC) $(STRICT_C11) -march=rv32i -mabi=ilp32 -ffreestanding -nostdlib -r $(SOURCES) -o $@

build:
	mkdir -p $@
