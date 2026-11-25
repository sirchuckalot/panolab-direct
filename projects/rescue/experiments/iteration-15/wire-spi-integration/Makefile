CC ?= cc
PYTHON ?= python3

SOURCES = test_managed_spi.c managed_wire_adapter.c ../management-wire/management_wire.c \
	../managed-stream/rescue_update.c ../upload-session/upload_session.c \
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
FIXTURES = fixtures.py ../manifest-core/fixtures.py

.PHONY: check test
check: test

test: build/test_managed_spi
	./build/test_managed_spi
	./build/test_managed_spi product-scale

build/test_managed_spi: $(SOURCES) $(HEADERS) build/fixtures.h
	$(CC) $(CPPFLAGS) $(CFLAGS) -O2 -std=c11 -Wall -Wextra -Wpedantic -Werror \
		-UNDEBUG -Ibuild -I../management-wire -I../spi-nor -I../managed-stream -I../journal-core \
		$(SOURCES) $(LDFLAGS) $(LDLIBS) -o $@

build/fixtures.h: $(FIXTURES) | build
	$(PYTHON) -B fixtures.py > $@.tmp
	mv $@.tmp $@

build:
	mkdir -p $@
