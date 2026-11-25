CC ?= cc
RVCC ?= riscv64-unknown-elf-gcc
PYTHON ?= python3

STRICT = -std=c11 -Wall -Wextra -Wpedantic -Werror
INCLUDES = -I../managed-stream -Ibuild -I../journal-core
SOURCES = ../operation-ledger/op_ledger.c ../managed-stream/rescue_update.c ../upload-session/upload_session.c \
          ../storage-core/rescue_storage.c ../journal-core/rescue_journal.c \
          ../image-core/image_core.c ../manifest-core/manifest_core.c \
          ../manifest-store/manifest_store.c \
          ../flash-transaction/rescue_flash_transaction.c ../trial-core/rescue_trial.c
HEADERS = $(wildcard *.h $(addsuffix /*.h,$(sort $(dir $(SOURCES)))))

.PHONY: check
check: build/test_stream_slot build/rescue_update.rv32.o build/upload_session.rv32.o
	./build/test_stream_slot

build:
	mkdir -p $@

build/fixtures.h: fixtures.py ../manifest-core/fixtures.py | build
	$(PYTHON) -B fixtures.py > $@.tmp
	mv $@.tmp $@

build/test_stream_slot: test_stream_slot.c $(SOURCES) $(HEADERS) build/fixtures.h
	$(CC) $(STRICT) $(INCLUDES) -O2 $(CFLAGS) -UNDEBUG $(SOURCES) test_stream_slot.c -o $@

build/rescue_update.rv32.o: ../managed-stream/rescue_update.c $(HEADERS) | build
	$(RVCC) $(STRICT) $(INCLUDES) -ffreestanding -march=rv32im -mabi=ilp32 -c $< -o $@

build/upload_session.rv32.o: ../upload-session/upload_session.c $(HEADERS) | build
	$(RVCC) $(STRICT) $(INCLUDES) -ffreestanding -march=rv32im -mabi=ilp32 -c $< -o $@
