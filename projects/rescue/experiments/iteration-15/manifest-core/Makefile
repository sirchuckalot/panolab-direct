CC ?= cc
RVCC ?= riscv64-unknown-elf-gcc
RVNM ?= riscv64-unknown-elf-nm
PYTHON ?= python3
STRICT = -std=c11 -Wall -Wextra -Werror -Wpedantic -Wconversion -Wshadow -Wstrict-prototypes
CORE_FLAGS = $(STRICT) -ffreestanding -fno-builtin
RV_FLAGS = -march=rv32im -mabi=ilp32
IMAGE_CORE = ../image-core
BUILD = build

.PHONY: check clean
check: $(BUILD)/test_manifest $(BUILD)/manifest.rv32.o
	$(RVNM) -u $(BUILD)/manifest.rv32.o > $(BUILD)/rv32-undefined.txt
	test ! -s $(BUILD)/rv32-undefined.txt
	./$(BUILD)/test_manifest

$(BUILD):
	mkdir -p $@

$(BUILD)/fixtures.h: fixtures.py | $(BUILD)
	$(PYTHON) $< > $@

$(BUILD)/test_manifest: test_manifest.c manifest_core.c manifest_core.h $(IMAGE_CORE)/image_core.c $(IMAGE_CORE)/image_core.h $(BUILD)/fixtures.h
	$(CC) $(CPPFLAGS) $(CFLAGS) $(CORE_FLAGS) $(LDFLAGS) test_manifest.c manifest_core.c $(IMAGE_CORE)/image_core.c -o $@

$(BUILD)/manifest.rv32.o: manifest_core.c manifest_core.h $(IMAGE_CORE)/image_core.c $(IMAGE_CORE)/image_core.h | $(BUILD)
	$(RVCC) $(CPPFLAGS) $(CFLAGS) $(CORE_FLAGS) $(RV_FLAGS) -c manifest_core.c -o $(BUILD)/manifest_core.rv32.o
	$(RVCC) $(CPPFLAGS) $(CFLAGS) $(CORE_FLAGS) $(RV_FLAGS) -c $(IMAGE_CORE)/image_core.c -o $(BUILD)/image_core.rv32.o
	$(RVCC) $(RV_FLAGS) -nostdlib -r $(BUILD)/manifest_core.rv32.o $(BUILD)/image_core.rv32.o -o $@

clean:
	rm -rf $(BUILD)
