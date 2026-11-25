CC ?= cc
RVCC ?= riscv64-unknown-elf-gcc
FLAGS = -std=c11 -Wall -Wextra -Wpedantic -Werror
.PHONY: check
check:
	mkdir -p build
	$(CC) $(FLAGS) -O2 op_ledger.c test_ledger.c -o build/test_ledger
	./build/test_ledger
	$(RVCC) $(FLAGS) -ffreestanding -march=rv32im -mabi=ilp32 -c op_ledger.c -o build/op_ledger.rv32.o
