CC ?= cc
RV32_CC ?= riscv64-unknown-elf-gcc
STRICT_C11 = -std=c11 -Wall -Wextra -Wpedantic -Werror
vpath %.c ../storage-core:../journal-core:../image-core
vpath %.h ../storage-core:../journal-core:../image-core
SOURCES = rescue_flash_transaction.c rescue_storage.c rescue_journal.c image_core.c
HEADERS = $(SOURCES:.c=.h)
RV32_OBJECTS = $(SOURCES:%.c=build/%.rv32.o)

.PHONY: all check test rv32
all: check
check: test rv32

test: build/test_rescue_flash_transaction
	./build/test_rescue_flash_transaction

rv32: $(RV32_OBJECTS)

build/test_rescue_flash_transaction: $(SOURCES) test_rescue_flash_transaction.c $(HEADERS) Makefile | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(STRICT_C11) $(filter %.c,$^) -o $@

build/%.rv32.o: %.c $(HEADERS) Makefile | build
	$(RV32_CC) $(STRICT_C11) -march=rv32i -mabi=ilp32 -ffreestanding -c $< -o $@

build:
	mkdir -p $@
