CC ?= cc
CROSS_CC ?= riscv64-unknown-elf-gcc
CPU_FLAGS ?= -march=rv32i2p0_m -mabi=ilp32
CHECK_FLAGS = -std=c11 -Wall -Wextra -Werror -pedantic -O2
PROBE = ../flash-probe/rescue_flash_probe
STORAGE = ../storage-core/rescue_storage
SOURCES = rescue_spi_nor.c $(PROBE).c $(STORAGE).c
HEADERS = rescue_spi_nor.h $(PROBE).h $(STORAGE).h
RV32_OBJECTS = $(addprefix build/rv32-,$(notdir $(SOURCES:.c=.o)))

vpath %.c ../flash-probe ../storage-core

.PHONY: check test freestanding clean
check: test freestanding

test: build/test_spi_nor
	./build/test_spi_nor

freestanding: $(RV32_OBJECTS)

build/test_spi_nor: test_spi_nor.c $(SOURCES) $(HEADERS) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(CHECK_FLAGS) -UNDEBUG $(filter %.c,$^) $(LDFLAGS) -o $@

build/rv32-%.o: %.c $(HEADERS) | build
	$(CROSS_CC) $(CPPFLAGS) $(CHECK_FLAGS) $(CPU_FLAGS) -ffreestanding -c $< -o $@

build:
	mkdir -p $@

clean:
	rm -f build/test_spi_nor $(RV32_OBJECTS)
