# Flash transaction tests

Run `make check` from this directory. It runs the native test executable and
cross-compiles the transaction and its dependencies as freestanding RV32I
objects using `riscv64-unknown-elf-gcc` by default. The RV32 step is a compile
check.

The native tests use a 16 MiB simulated NOR with the storage profile's 256 KiB
erase sectors and 256-byte program pages. The erase-aligned partition map is
synthetic. Both journal sectors are checked byte for byte, and nonzero sentinel
bytes expose writes beyond the requested erase span. The suite checks stage
validation, first staging from an initialized journal, every erase and program
callback failure, partial programming, and readback failure.

The transaction has no physical flash backend. It consumes caller-supplied
manifest metadata in memory and does not persist a manifest or issue a trial
token. Successful staging returns the verified slot, raw image length, and
digest. Staging leaves the journal unchanged, and a failure can leave the target
incomplete while preserving the caller's verified output.
