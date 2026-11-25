/* PanoLab image integrity core. SPDX-License-Identifier: GPL-3.0-or-later */
#include "image_core.h"

#define SHA256_MAX_BYTES (UINT64_MAX / 8u)

static const uint32_t round_constants[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
    0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
    0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
    0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
    0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
    0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
};

static uint32_t rotate_right(uint32_t word, unsigned count)
{
    return (word >> count) | (word << (32u - count));
}

static void compress(struct pl_sha256 *ctx, const uint8_t *block)
{
    uint32_t words[64];
    uint32_t a = ctx->state[0], b = ctx->state[1];
    uint32_t c = ctx->state[2], d = ctx->state[3];
    uint32_t e = ctx->state[4], f = ctx->state[5];
    uint32_t g = ctx->state[6], h = ctx->state[7];

    for (size_t i = 0; i < 16; ++i) {
        const uint8_t *bytes = block + 4u * i;
        words[i] = ((uint32_t)bytes[0] << 24) | ((uint32_t)bytes[1] << 16)
                 | ((uint32_t)bytes[2] << 8) | (uint32_t)bytes[3];
    }
    for (size_t i = 16; i < 64; ++i) {
        uint32_t x = words[i - 15];
        uint32_t y = words[i - 2];
        uint32_t sigma0 = rotate_right(x, 7) ^ rotate_right(x, 18) ^ (x >> 3);
        uint32_t sigma1 = rotate_right(y, 17) ^ rotate_right(y, 19) ^ (y >> 10);
        words[i] = words[i - 16] + sigma0 + words[i - 7] + sigma1;
    }
    for (size_t i = 0; i < 64; ++i) {
        uint32_t sum1 = rotate_right(e, 6) ^ rotate_right(e, 11) ^ rotate_right(e, 25);
        uint32_t choose = (e & f) ^ (~e & g);
        uint32_t temp1 = h + sum1 + choose + round_constants[i] + words[i];
        uint32_t sum0 = rotate_right(a, 2) ^ rotate_right(a, 13) ^ rotate_right(a, 22);
        uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
        uint32_t temp2 = sum0 + majority;

        h = g;
        g = f;
        f = e;
        e = d + temp1;
        d = c;
        c = b;
        b = a;
        a = temp1 + temp2;
    }

    ctx->state[0] += a;
    ctx->state[1] += b;
    ctx->state[2] += c;
    ctx->state[3] += d;
    ctx->state[4] += e;
    ctx->state[5] += f;
    ctx->state[6] += g;
    ctx->state[7] += h;
}

void pl_sha256_init(struct pl_sha256 *ctx)
{
    ctx->state[0] = UINT32_C(0x6a09e667);
    ctx->state[1] = UINT32_C(0xbb67ae85);
    ctx->state[2] = UINT32_C(0x3c6ef372);
    ctx->state[3] = UINT32_C(0xa54ff53a);
    ctx->state[4] = UINT32_C(0x510e527f);
    ctx->state[5] = UINT32_C(0x9b05688c);
    ctx->state[6] = UINT32_C(0x1f83d9ab);
    ctx->state[7] = UINT32_C(0x5be0cd19);
    ctx->length = 0;
    ctx->used = 0;
}

int pl_sha256_update(struct pl_sha256 *ctx, const void *data, size_t length)
{
    const uint8_t *bytes = data;

    if (ctx->length > SHA256_MAX_BYTES || length > SHA256_MAX_BYTES - ctx->length)
        return -1;
    ctx->length += (uint64_t)length;

    while (length != 0) {
        size_t count = sizeof(ctx->block) - ctx->used;
        if (ctx->used == 0 && length >= sizeof(ctx->block)) {
            compress(ctx, bytes);
        } else {
            if (count > length)
                count = length;
            for (size_t i = 0; i < count; ++i)
                ctx->block[ctx->used + i] = bytes[i];
            ctx->used += count;
            if (ctx->used == sizeof(ctx->block)) {
                compress(ctx, ctx->block);
                ctx->used = 0;
            }
        }
        bytes += count;
        length -= count;
    }
    return 0;
}

void pl_sha256_final(struct pl_sha256 *ctx, uint8_t digest[PL_SHA256_SIZE])
{
    uint64_t bits = ctx->length * 8u;

    ctx->block[ctx->used++] = 0x80;
    if (ctx->used > 56) {
        while (ctx->used < sizeof(ctx->block))
            ctx->block[ctx->used++] = 0;
        compress(ctx, ctx->block);
        ctx->used = 0;
    }
    while (ctx->used < 56)
        ctx->block[ctx->used++] = 0;
    for (size_t i = sizeof(ctx->block); i > 56; --i) {
        ctx->block[i - 1] = (uint8_t)bits;
        bits >>= 8;
    }
    compress(ctx, ctx->block);

    for (size_t i = 0; i < 8; ++i) {
        uint32_t word = ctx->state[i];
        digest[4u * i] = (uint8_t)(word >> 24);
        digest[4u * i + 1] = (uint8_t)(word >> 16);
        digest[4u * i + 2] = (uint8_t)(word >> 8);
        digest[4u * i + 3] = (uint8_t)word;
    }
}

enum pl_image_result pl_image_verify(const struct pl_image_metadata *metadata,
                                     const struct pl_image_policy *policy,
                                     uint64_t raw_length,
                                     pl_image_read_fn read, void *context)
{
    struct pl_sha256 sha;
    uint8_t buffer[PL_IMAGE_READ_CHUNK];
    uint8_t digest[PL_SHA256_SIZE];
    unsigned difference = 0;

    if (metadata == NULL || policy == NULL || read == NULL)
        return PL_IMAGE_ARGUMENT;
    if (metadata->profile != PL_TRUSTED_LAN || policy->profile != PL_TRUSTED_LAN)
        return PL_IMAGE_PROFILE;
    if (metadata->manifest_version != 1)
        return PL_IMAGE_VERSION;
    if (metadata->role != PL_APPLICATION)
        return PL_IMAGE_ROLE;
    if (metadata->target.board != PL_PANO_G2 ||
        metadata->target.revision != PL_REV_B ||
        metadata->target.fpga != PL_XC6SLX150_2_FGG484 ||
        metadata->target.board != policy->detected_target.board ||
        metadata->target.revision != policy->detected_target.revision ||
        metadata->target.fpga != policy->detected_target.fpga ||
        metadata->target.bsp_version != policy->detected_target.bsp_version)
        return PL_IMAGE_TARGET;
    if (metadata->rescue_api_major != policy->rescue_api_major ||
        metadata->rescue_api_min_minor > policy->rescue_api_minor)
        return PL_IMAGE_API;
    if (metadata->format != PL_XILINX_SPARTAN6_SPI_V1)
        return PL_IMAGE_FORMAT;
    if ((metadata->required_features & ~PL_FEATURE_ICAP_RETURN_V1) != 0 ||
        (metadata->required_features & ~policy->supported_features) != 0)
        return PL_IMAGE_FEATURE;
    if (raw_length == 0 || raw_length != metadata->image_length ||
        raw_length > policy->max_image_length || raw_length > SHA256_MAX_BYTES)
        return PL_IMAGE_LENGTH;

    pl_sha256_init(&sha);
    for (uint64_t offset = 0; offset < raw_length;) {
        uint64_t remaining = raw_length - offset;
        size_t count = remaining < sizeof(buffer) ? (size_t)remaining : sizeof(buffer);
        if (read(context, offset, buffer, count) != count)
            return PL_IMAGE_READ;
        if (pl_sha256_update(&sha, buffer, count) != 0)
            return PL_IMAGE_LENGTH;
        offset += count;
    }
    pl_sha256_final(&sha, digest);
    for (size_t i = 0; i < sizeof(digest); ++i)
        difference |= (unsigned)(digest[i] ^ metadata->image_sha256[i]);
    return difference == 0 ? PL_IMAGE_OK : PL_IMAGE_DIGEST;
}
