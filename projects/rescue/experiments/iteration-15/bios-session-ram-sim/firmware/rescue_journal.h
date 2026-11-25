#ifndef RESCUE_JOURNAL_H
#define RESCUE_JOURNAL_H

#include <stddef.h>
#include <stdint.h>

#define RESCUE_JOURNAL_VERSION 1u
#define RESCUE_JOURNAL_RECORD_BYTES 151u
#define RESCUE_JOURNAL_DIGEST_BYTES 32u
#define RESCUE_JOURNAL_REASON_BYTES 32u

enum rescue_journal_slot {
    RESCUE_JOURNAL_NONE = 0,
    RESCUE_JOURNAL_A = 1,
    RESCUE_JOURNAL_B = 2
};

/* Callers integrating with boot policy translate states by name. */
enum rescue_record_state {
    RESCUE_RECORD_STABLE = 0x10,
    RESCUE_RECORD_TRIAL_PENDING = 0x11,
    RESCUE_RECORD_TRIAL_RUNNING = 0x12,
    RESCUE_RECORD_ROLLBACK_REQUIRED = 0x13,
    RESCUE_RECORD_RECOVERY_ONLY = 0x14
};

struct rescue_journal_binding {
    uint8_t slot;
    uint8_t digest[RESCUE_JOURNAL_DIGEST_BYTES];
};

struct rescue_journal_record {
    uint64_t sequence;
    struct rescue_journal_binding confirmed;
    struct rescue_journal_binding pending;
    struct rescue_journal_binding previous;
    uint8_t state;
    uint8_t attempts;
    char reason[RESCUE_JOURNAL_REASON_BYTES + 1u];
};

/*
 * Sector IDs 0 and 1 designate independent erase units of sector_bytes each.
 * Callbacks return zero on success, after completing the operation. Program
 * must support a separate final one-byte write and must preserve other bytes.
 * The caller serializes all journal operations and access to these sectors.
 */
struct rescue_journal_io {
    void *context;
    size_t sector_bytes;
    int (*read)(void *context, unsigned sector, size_t offset,
                uint8_t *data, size_t length);
    int (*erase)(void *context, unsigned sector);
    int (*program)(void *context, unsigned sector, size_t offset,
                   const uint8_t *data, size_t length);
};

enum rescue_journal_result {
    RESCUE_JOURNAL_OK = 0,
    RESCUE_JOURNAL_INVALID,
    RESCUE_JOURNAL_IO_ERROR,
    RESCUE_JOURNAL_NO_RECORD,
    RESCUE_JOURNAL_AMBIGUOUS,
    RESCUE_JOURNAL_STALE,
    RESCUE_JOURNAL_OVERFLOW,
    RESCUE_JOURNAL_VERIFY_ERROR
};

/*
 * Fixed frame: RSJ1 (4), version (1), sequence (8, big endian),
 * confirmed/pending/previous bindings (33 each, slot then raw digest),
 * state (1, codes 0 through 4 in enum declaration order), attempts (1),
 * lowercase ASCII reason (32, zero padded),
 * CRC-32/ISO-HDLC (4, big endian), commit marker (1, zero).
 * Bytes after the frame must be erased (0xff). An absent binding has a
 * zero slot and zero digest. CRC covers all bytes preceding the CRC.
 */
enum rescue_journal_result rescue_journal_encode(
    const struct rescue_journal_record *record,
    uint8_t frame[RESCUE_JOURNAL_RECORD_BYTES]);

/* On failure, output is unchanged. */
enum rescue_journal_result rescue_journal_read(
    const struct rescue_journal_io *io, struct rescue_journal_record *record);

/*
 * expected must match the entire selected record. next must have the next
 * sequence. Boot policy owns transition authorization and image verification.
 * After an I/O or verify error, reread before deciding whether to retry.
 * First initialization is pending a separate provisioning path. An empty
 * journal returns NO_RECORD and commit cannot provision it.
 */
enum rescue_journal_result rescue_journal_commit(
    const struct rescue_journal_io *io,
    const struct rescue_journal_record *expected,
    const struct rescue_journal_record *next);

#endif
