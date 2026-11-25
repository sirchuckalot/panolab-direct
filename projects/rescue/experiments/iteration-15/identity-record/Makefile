CC ?= cc
RVCC ?= riscv64-unknown-elf-gcc
FLAGS = -std=c11 -Wall -Wextra -Wpedantic -Werror
.PHONY: check
check:
	mkdir -p build
	$(CC) $(FLAGS) identity_record.c ../storage-core/rescue_storage.c test_identity.c -o build/test_identity
	./build/test_identity
	$(RVCC) $(FLAGS) -march=rv32im -mabi=ilp32 -ffreestanding -c identity_record.c -o build/identity_record.rv32.o
