CC ?= cc
PYTHON ?= python3
F = ../bios-session-ram-sim/firmware
MODULES = sim_upload network_session managed_wire_adapter management_wire rescue_update upload_session manifest_core manifest_store image_core rescue_flash_transaction rescue_trial rescue_storage rescue_journal identity_record rescue_protected_read
SOURCES = $(addprefix $(F)/,$(addsuffix .c,$(MODULES)))
.PHONY: check
check: build/bridge.so
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest -v
build/bridge.so: bridge.c $(SOURCES) $(wildcard $(F)/*.h)
	mkdir -p build
	$(CC) -std=c11 -Wall -Wextra -Werror -shared -fPIC -O2 bridge.c $(SOURCES) -o $@
