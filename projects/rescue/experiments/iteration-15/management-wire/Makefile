CC ?= cc
RV32_CC ?= riscv64-unknown-elf-gcc
RV32_FLAGS ?= -march=rv32imac -mabi=ilp32
STRICT_FLAGS := -std=c11 -Wall -Wextra -Werror -Wpedantic -Wconversion -Wsign-conversion -Wshadow -Wstrict-prototypes

.PHONY: all check clean
all: management_wire_test management_wire.rv32.o

check: all
	./management_wire_test

management_wire_test: management_wire.c management_wire_test.c management_wire.h
	$(CC) $(CPPFLAGS) $(CFLAGS) $(STRICT_FLAGS) $(LDFLAGS) -o $@ management_wire.c management_wire_test.c $(LDLIBS)

management_wire.rv32.o: management_wire.c management_wire.h
	$(RV32_CC) $(CPPFLAGS) $(RV32_FLAGS) $(STRICT_FLAGS) -ffreestanding -c -o $@ $<

clean:
	$(RM) management_wire_test management_wire.rv32.o
