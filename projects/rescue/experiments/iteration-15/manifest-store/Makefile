CC ?= cc
RVCC ?= riscv64-unknown-elf-gcc
RVNM ?= riscv64-unknown-elf-nm
PYTHON ?= python3
CORE_FLAGS = -std=c11 -Wall -Wextra -Werror -Wpedantic -Wconversion -Wshadow -Wstrict-prototypes -ffreestanding -fno-builtin
RV_FLAGS = -march=rv32im -mabi=ilp32
SOURCES = manifest_store.c ../manifest-core/manifest_core.c ../image-core/image_core.c
HEADERS = manifest_store.h ../manifest-core/manifest_core.h ../image-core/image_core.h
RV_OBJECTS = build/manifest_store.rv32.o build/manifest_core.rv32.o build/image_core.rv32.o

.PHONY: check clean
check: build/test_store build/core.rv32.o
	$(RVNM) -u build/core.rv32.o > build/rv32-undefined.txt
	test ! -s build/rv32-undefined.txt
	./build/test_store

build:
	mkdir -p $@

build/fixtures.h: fixtures.py ../manifest-core/fixtures.py | build
	$(PYTHON) $< > $@

build/test_store: test_store.c $(SOURCES) $(HEADERS) build/fixtures.h
	$(CC) $(CPPFLAGS) $(CFLAGS) $(CORE_FLAGS) $(LDFLAGS) test_store.c $(SOURCES) -o $@

build/manifest_store.rv32.o: manifest_store.c
build/manifest_core.rv32.o: ../manifest-core/manifest_core.c
build/image_core.rv32.o: ../image-core/image_core.c
$(RV_OBJECTS): $(HEADERS) | build
	$(RVCC) $(CPPFLAGS) $(CFLAGS) $(CORE_FLAGS) $(RV_FLAGS) -c $(filter %.c,$^) -o $@

build/core.rv32.o: $(RV_OBJECTS)
	$(RVCC) $(RV_FLAGS) -nostdlib -r $^ -o $@

clean:
	rm -rf build
