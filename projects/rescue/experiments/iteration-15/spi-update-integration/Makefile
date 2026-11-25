CC ?= cc
PYTHON ?= python3

SOURCES = test_spi_update.c \
	../update-controller/rescue_update.c \
	../spi-nor/rescue_spi_nor.c \
	../flash-probe/rescue_flash_probe.c \
	../storage-core/rescue_storage.c \
	../journal-core/rescue_journal.c \
	../image-core/image_core.c \
	../manifest-core/manifest_core.c \
	../manifest-store/manifest_store.c \
	../flash-transaction/rescue_flash_transaction.c \
	../trial-core/rescue_trial.c
HEADERS = $(wildcard $(addsuffix /*.h,$(sort $(dir $(SOURCES)))))
FIXTURES = ../update-controller/fixtures.py ../manifest-core/fixtures.py

.PHONY: check test
check: test

test: build/test_spi_update
	./build/test_spi_update

build/test_spi_update: $(SOURCES) $(HEADERS) build/fixtures.h
	$(CC) $(CPPFLAGS) $(CFLAGS) -O2 -std=c11 -Wall -Wextra -Wpedantic -Werror \
		-UNDEBUG -Ibuild -I../spi-nor -I../update-controller -I../journal-core \
		$(SOURCES) $(LDFLAGS) $(LDLIBS) -o $@

build/fixtures.h: $(FIXTURES) | build
	cd ../update-controller && $(PYTHON) -B fixtures.py > ../spi-update-integration/$@.tmp
	mv $@.tmp $@

build:
	mkdir -p $@
