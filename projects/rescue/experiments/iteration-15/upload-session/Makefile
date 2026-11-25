CC ?= cc
RVCC ?= riscv64-unknown-elf-gcc
PYTHON ?= python3

WARNINGS = -std=c11 -Wall -Wextra -Wpedantic -Werror
SOURCES = upload_session.c ../manifest-core/manifest_core.c ../image-core/image_core.c

.PHONY: check
check:
	mkdir -p build
	$(PYTHON) -B ../update-controller/fixtures.py > build/fixtures.h
	$(CC) $(CPPFLAGS) $(CFLAGS) $(WARNINGS) -UNDEBUG -O2 $(SOURCES) test_upload_session.c -o build/test_upload_session
	./build/test_upload_session
	$(RVCC) $(WARNINGS) -ffreestanding -march=rv32im -mabi=ilp32 -c upload_session.c -o build/upload_session.rv32.o
