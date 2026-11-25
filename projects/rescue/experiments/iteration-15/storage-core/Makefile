CC ?= cc
RV32_CC ?= riscv64-unknown-elf-gcc
CHECK_FLAGS = -std=c11 -Wall -Wextra -Werror -pedantic

.PHONY: test rv32
test: build/test_rescue_storage rv32
	./build/test_rescue_storage

rv32: build/rescue_storage.rv32.o

build/test_rescue_storage: rescue_storage.c rescue_storage.h test_rescue_storage.c Makefile
	mkdir -p build
	$(CC) $(CFLAGS) $(CHECK_FLAGS) -UNDEBUG rescue_storage.c test_rescue_storage.c -o $@

build/rescue_storage.rv32.o: rescue_storage.c rescue_storage.h Makefile
	mkdir -p build
	$(RV32_CC) $(CHECK_FLAGS) -ffreestanding -march=rv32im -mabi=ilp32 -c rescue_storage.c -o $@
