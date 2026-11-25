/* PanoLab image integrity tests. SPDX-License-Identifier: GPL-3.0-or-later */
#include "image_core.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(condition) do { \
    if (!(condition)) { \
        fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition); \
        exit(EXIT_FAILURE); \
    } \
} while (0)

static void decode_digest(const char *hex, uint8_t digest[PL_SHA256_SIZE])
{
    for (size_t i = 0; i < PL_SHA256_SIZE; ++i) {
        unsigned byte;
        CHECK(sscanf(hex + 2u * i, "%2x", &byte) == 1);
        digest[i] = (uint8_t)byte;
    }
}

static void check_vector(const void *bytes, size_t length, const char *hex)
{
    const uint8_t *data = bytes;
    const size_t chunks[] = {1, 7, 55, 56, 63, 64, 65, 127, 256, 4096};
    uint8_t expected[PL_SHA256_SIZE];
    decode_digest(hex, expected);
    for (size_t i = 0; i < sizeof(chunks) / sizeof(chunks[0]); ++i) {
        struct pl_sha256 sha;
        uint8_t digest[PL_SHA256_SIZE];
        pl_sha256_init(&sha);
        CHECK(pl_sha256_update(&sha, NULL, 0) == 0);
        for (size_t offset = 0; offset < length;) {
            size_t count = length - offset;
            if (count > chunks[i])
                count = chunks[i];
            CHECK(pl_sha256_update(&sha, data + offset, count) == 0);
            offset += count;
        }
        pl_sha256_final(&sha, digest);
        CHECK(memcmp(digest, expected, sizeof(digest)) == 0);
    }
}

static uint8_t million_a[1000000];

static void test_sha256(void)
{
    struct pl_sha256 sha;
    const char message[] = "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq";

    check_vector(NULL, 0, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
    check_vector("abc", 3, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    check_vector(message, sizeof(message) - 1,
                 "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1");
    memset(million_a, 'a', sizeof(million_a));
    check_vector(million_a, sizeof(million_a),
                 "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0");
    pl_sha256_init(&sha);
    sha.length = UINT64_MAX / 8u;
    CHECK(pl_sha256_update(&sha, "x", 1) == -1);
    CHECK(sha.length == UINT64_MAX / 8u && sha.used == 0);
}

struct reader {
    const uint8_t *data;
    size_t length;
    size_t next;
    unsigned calls;
    unsigned fail_at;
    size_t failure_result;
};

static size_t read_image(void *context, uint64_t offset, uint8_t *buffer, size_t count)
{
    struct reader *reader = context;
    CHECK(offset == reader->next && offset <= reader->length);
    CHECK(count > 0 && count <= PL_IMAGE_READ_CHUNK);
    CHECK(count <= reader->length - reader->next);
    ++reader->calls;
    if (reader->calls == reader->fail_at)
        return reader->failure_result;
    memcpy(buffer, reader->data + reader->next, count);
    reader->next += count;
    return count;
}

static void test_image(void)
{
    uint8_t raw[sizeof(million_a) + 1];
    const struct pl_target target = {PL_PANO_G2, PL_REV_B, PL_XC6SLX150_2_FGG484, 1};
    const struct pl_image_policy policy = {PL_TRUSTED_LAN, target, 1, 2,
                                          PL_FEATURE_ICAP_RETURN_V1, sizeof(raw)};
    struct pl_image_metadata image = {
        .profile = PL_TRUSTED_LAN, .manifest_version = 1, .role = PL_APPLICATION,
        .target = target, .rescue_api_major = 1, .rescue_api_min_minor = 2,
        .format = PL_XILINX_SPARTAN6_SPI_V1,
        .required_features = PL_FEATURE_ICAP_RETURN_V1, .image_length = sizeof(raw) - 1
    };
    struct reader reader = {.data = raw, .length = sizeof(raw) - 1};
    struct pl_image_metadata changed;
    struct pl_image_policy environment;

    memcpy(raw, million_a, sizeof(million_a));
    raw[sizeof(raw) - 1] = 0xff;
    decode_digest("cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0",
                  image.image_sha256);
    CHECK(pl_image_verify(&image, &policy, reader.length, read_image, &reader) == PL_IMAGE_OK);
    CHECK(reader.next == reader.length && reader.calls > 1);
    reader.next = 0;
    reader.calls = 0;
    raw[reader.length - 1] ^= 1u;
    CHECK(pl_image_verify(&image, &policy, reader.length, read_image, &reader) == PL_IMAGE_DIGEST);
    raw[reader.length - 1] ^= 1u;
    for (size_t failure = 0; failure < 2; ++failure) {
        reader.next = 0;
        reader.calls = 0;
        reader.fail_at = 2;
        reader.failure_result = failure ? PL_IMAGE_READ_CHUNK - 1u : 0;
        CHECK(pl_image_verify(&image, &policy, reader.length, read_image, &reader) == PL_IMAGE_READ);
        CHECK(reader.calls == 2);
    }
    reader.calls = 0;
    reader.next = 0;

#define REJECT(field, value, result) do { \
    changed = image; \
    changed.field = (value); \
    CHECK(pl_image_verify(&changed, &policy, reader.length, read_image, &reader) == (result)); \
    CHECK(reader.calls == 0); \
} while (0)
    REJECT(profile, PL_PRODUCTION, PL_IMAGE_PROFILE);
    REJECT(profile, PL_DEVELOPER, PL_IMAGE_PROFILE);
    REJECT(profile, 0, PL_IMAGE_PROFILE);
    REJECT(manifest_version, 2, PL_IMAGE_VERSION);
    REJECT(role, PL_RESCUE, PL_IMAGE_ROLE);
    REJECT(target.board, 0, PL_IMAGE_TARGET);
    REJECT(target.revision, 0, PL_IMAGE_TARGET);
    REJECT(target.fpga, 0, PL_IMAGE_TARGET);
    REJECT(target.bsp_version, 2, PL_IMAGE_TARGET);
    REJECT(rescue_api_major, 2, PL_IMAGE_API);
    REJECT(rescue_api_min_minor, 3, PL_IMAGE_API);
    REJECT(format, 0, PL_IMAGE_FORMAT);
    REJECT(required_features, UINT32_C(1) << 31, PL_IMAGE_FEATURE);
    REJECT(image_length, reader.length - 1, PL_IMAGE_LENGTH);
#undef REJECT

    environment = policy;
    environment.profile = PL_PRODUCTION;
    CHECK(pl_image_verify(&image, &environment, reader.length, read_image, &reader) == PL_IMAGE_PROFILE);
    environment = policy;
    environment.detected_target.revision = 0;
    CHECK(pl_image_verify(&image, &environment, reader.length, read_image, &reader) == PL_IMAGE_TARGET);
    environment = policy;
    environment.supported_features = 0;
    CHECK(pl_image_verify(&image, &environment, reader.length, read_image, &reader) == PL_IMAGE_FEATURE);
    environment = policy;
    environment.supported_features = UINT32_MAX;
    changed = image;
    changed.required_features = UINT32_C(1) << 31;
    CHECK(pl_image_verify(&changed, &environment, reader.length, read_image, &reader) == PL_IMAGE_FEATURE);
    environment = policy;
    environment.max_image_length = reader.length - 1;
    CHECK(pl_image_verify(&image, &environment, reader.length, read_image, &reader) == PL_IMAGE_LENGTH);
    CHECK(pl_image_verify(&image, &policy, sizeof(raw), read_image, &reader) == PL_IMAGE_LENGTH);
    changed = image;
    changed.image_length = 0;
    CHECK(pl_image_verify(&changed, &policy, 0, read_image, &reader) == PL_IMAGE_LENGTH);
    environment.max_image_length = UINT64_MAX;
    changed.image_length = UINT64_MAX / 8u + 1u;
    CHECK(pl_image_verify(&changed, &environment, changed.image_length, read_image, &reader) == PL_IMAGE_LENGTH);
    CHECK(pl_image_verify(&image, &policy, reader.length, NULL, &reader) == PL_IMAGE_ARGUMENT);
    CHECK(reader.calls == 0);
}

int main(void)
{
    test_sha256();
    test_image();
    puts("image core tests passed");
    return 0;
}
