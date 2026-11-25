CC ?= cc
CROSS_CC ?= riscv64-unknown-elf-gcc
BIOS_BUILD ?= ../bios-integration/build-s5.oTprq0
LITEX_SOC ?= /repo/third_party/litex/afed6623/src/litex/soc
CPU_FLAGS ?= -march=rv32i2p0_m -mabi=ilp32 -D__vexriscv__
CHECK_FLAGS = -std=c11 -Wall -Wextra -Werror -O2
STORAGE = ../storage-core/rescue_storage
CORE_DEPS = rescue_flash_probe.h $(STORAGE).h
LITEX_CSR = $(BIOS_BUILD)/software/include/generated/csr.h

.PHONY: check test freestanding clean
check: test freestanding

test: build/test_rescue_flash_probe
	./build/test_rescue_flash_probe

freestanding: build/rescue_flash_probe.o build/rescue_flash_probe_litex.o

build/test_rescue_flash_probe: test_rescue_flash_probe.c rescue_flash_probe.c $(STORAGE).c $(CORE_DEPS) | build
	$(CC) $(CPPFLAGS) $(CHECK_FLAGS) $(CFLAGS) $(filter %.c,$^) -o $@

build/rescue_flash_probe.o: rescue_flash_probe.c $(CORE_DEPS) | build
	$(CROSS_CC) $(CHECK_FLAGS) $(CPU_FLAGS) -ffreestanding -c $< -o $@

build/rescue_flash_probe_litex.o: rescue_flash_probe_litex.c $(CORE_DEPS) $(LITEX_CSR) | build
	$(CROSS_CC) $(CHECK_FLAGS) -std=gnu11 $(CPU_FLAGS) -ffreestanding \
		-isystem $(BIOS_BUILD)/software/include -isystem $(LITEX_SOC)/software/include \
		-isystem $(LITEX_SOC)/cores/cpu/vexriscv -c $< -o $@

build:
	mkdir -p $@

clean:
	rm -f build/test_rescue_flash_probe build/rescue_flash_probe.o build/rescue_flash_probe_litex.o
