CC ?= cc
RVCC ?= riscv64-unknown-elf-gcc
FLAGS = -std=c11 -Wall -Wextra -Wpedantic -Werror -I../journal-core
SOURCES = rescue_update.c ../storage-core/rescue_storage.c ../journal-core/rescue_journal.c ../image-core/image_core.c ../manifest-core/manifest_core.c ../manifest-store/manifest_store.c ../flash-transaction/rescue_flash_transaction.c ../trial-core/rescue_trial.c
.PHONY: check
check:
	mkdir -p build
	python3 fixtures.py > build/fixtures.h
	$(CC) $(FLAGS) -O2 $(SOURCES) test_update.c -o build/test_update
	./build/test_update
	$(RVCC) $(FLAGS) -ffreestanding -march=rv32im -mabi=ilp32 -c rescue_update.c -o build/rescue_update.rv32.o
