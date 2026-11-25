#ifndef OP_LEDGER_H
#define OP_LEDGER_H

#include <stdbool.h>
#include <stdint.h>

#define OL_DIGEST_SIZE 32u
#define OL_FRAME_SIZE 75u
#define OL_BODY_SIZE (OL_FRAME_SIZE - 1u)
#define OL_UNCOMMITTED_MARKER UINT8_C(0xff)
#define OL_COMMITTED_MARKER UINT8_C(0xa5)

typedef enum {
    OL_OK, OL_IO, OL_CORRUPT, OL_UNPROVISIONED, OL_NOT_EMPTY,
    OL_OVERFLOW, OL_STATE, OL_MISMATCH, OL_ARGUMENT
} ol_result;

typedef enum {
    OL_NONE, OL_RESERVED, OL_SEALED, OL_CANCELLED, OL_INTERRUPTED
} ol_state;

typedef enum { OL_READ_EMPTY, OL_READ_FRAME, OL_READ_ERROR } ol_read_result;

/*
 * Each store owns one synthetic record. EMPTY means the entire store is
 * verified blank. FRAME must initialize all bytes, including the marker.
 * Mutators return true only when durable. Erase clears the whole record,
 * write_body leaves the marker erased, and commit writes only the marker.
 * Failed writes may leave partial data. Read must report uncertain I/O as ERROR.
 */
typedef struct {
    void *context;
    ol_read_result (*read)(void *context, uint8_t frame[OL_FRAME_SIZE]);
    bool (*erase)(void *context);
    bool (*write_body)(void *context, const uint8_t body[OL_BODY_SIZE]);
    bool (*commit)(void *context, uint8_t marker);
} ol_store;

typedef struct {
    uint64_t generation;
    uint64_t boot_epoch;
    uint64_t operation_id;
    uint64_t journal_sequence;
    ol_state state;
    uint8_t digest[OL_DIGEST_SIZE];
} ol_record;

/* Fields are private to the implementation. Serialize all access and use
 * one live handle per pair of independent stores. */
typedef struct {
    ol_store stores[2];
    ol_record current;
    unsigned active;
    bool initialized;
    bool ready;
} ol_ledger;

ol_result ol_init(ol_ledger *ledger, ol_store first, ol_store second);
ol_result ol_provision(ol_ledger *ledger);
ol_result ol_boot(ol_ledger *ledger);
ol_result ol_snapshot(const ol_ledger *ledger, ol_record *record);

/* A successful reserve publishes the new ID. Update mutation must wait for
 * this success. Journal sequences are stored verbatim as caller metadata. */
ol_result ol_reserve(ol_ledger *ledger, const uint8_t digest[OL_DIGEST_SIZE],
                     uint64_t journal_sequence, uint64_t *operation_id);
ol_result ol_finish(ol_ledger *ledger, uint64_t operation_id,
                    const uint8_t digest[OL_DIGEST_SIZE],
                    uint64_t journal_sequence, ol_state terminal);

#endif
