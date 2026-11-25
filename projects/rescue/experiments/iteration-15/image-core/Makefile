CC ?= cc
RVCC ?= riscv64-unknown-elf-gcc
RVNM ?= riscv64-unknown-elf-nm
STRICT = -std=c11 -Wall -Wextra -Werror -Wpedantic -Wconversion -Wshadow -Wstrict-prototypes
CORE_FLAGS = $(STRICT) -ffreestanding -fno-builtin
RV_FLAGS = -march=rv32im -mabi=ilp32
BUILD = build

.PHONY: check clean
check: $(BUILD)/test_image_core $(BUILD)/image_core.rv32.o
	@test -z "$$($(RVNM) -u $(BUILD)/image_core.rv32.o)"
	./$(BUILD)/test_image_core

$(BUILD):
	mkdir -p $@

$(BUILD)/image_core.o: image_core.c image_core.h | $(BUILD)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(CORE_FLAGS) -c $< -o $@

$(BUILD)/image_core.rv32.o: image_core.c image_core.h | $(BUILD)
	$(RVCC) $(CPPFLAGS) $(CFLAGS) $(CORE_FLAGS) $(RV_FLAGS) -c $< -o $@

$(BUILD)/test_image_core: test_image_core.c image_core.h $(BUILD)/image_core.o | $(BUILD)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(STRICT) $(LDFLAGS) test_image_core.c $(BUILD)/image_core.o -o $@

clean:
	rm -rf $(BUILD)
