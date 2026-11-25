CC ?= cc
.PHONY: check
check:
	mkdir -p build
	$(CC) -std=c11 -Wall -Wextra -Werror -shared -fPIC ../bios-network-probe/firmware/rescue_diag.c -o build/diag.so
	PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_client
