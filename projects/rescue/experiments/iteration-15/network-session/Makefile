CC ?= cc
RV32_CC ?= riscv64-unknown-elf-gcc
RV32_FLAGS ?= -march=rv32imac -mabi=ilp32
STRICT_FLAGS := -std=c11 -Wall -Wextra -Werror -Wpedantic -Wconversion -Wsign-conversion -Wshadow -Wstrict-prototypes
WIRE := ../management-wire/management_wire

.PHONY: all check clean
all: network_session_test network_session.rv32.o management_wire.rv32.o

check: all
	./network_session_test

network_session_test: network_session_test.c network_session.c network_session.h $(WIRE).c $(WIRE).h
	$(CC) $(CPPFLAGS) $(CFLAGS) $(STRICT_FLAGS) $(LDFLAGS) -o $@ network_session_test.c network_session.c $(WIRE).c $(LDLIBS)

network_session.rv32.o: network_session.c network_session.h $(WIRE).h
	$(RV32_CC) $(CPPFLAGS) $(RV32_FLAGS) $(STRICT_FLAGS) -ffreestanding -c -o $@ $<

management_wire.rv32.o: $(WIRE).c $(WIRE).h
	$(RV32_CC) $(CPPFLAGS) $(RV32_FLAGS) $(STRICT_FLAGS) -ffreestanding -c -o $@ $<

clean:
	$(RM) network_session_test network_session.rv32.o management_wire.rv32.o
