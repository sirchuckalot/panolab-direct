#include "rescue_spi_nor.h"
#include "managed_stream.h"
#include "managed_wire_adapter.h"
#include "fixtures.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

enum {
    CAP = 16 * 1024 * 1024, SECTOR = 256 * 1024, PAGE = 256,
    A = 18 * SECTOR, B = 36 * SECTOR, APP_SIZE = 18 * SECTOR,
    J0 = 55 * SECTOR, J1 = 56 * SECTOR
};
enum {
    READ = 0x03, RDSR = 0x05, WREN = 0x06, ERASE = 0xd8,
    PROGRAM = 0x02, RDID = 0x9f, WIP = 1, WEL = 2
};

/* Same layout as the update-controller fixture. */
static const struct rescue_region map[] = {
    {RESCUE_REGION_BOOT, 0, SECTOR},
    {RESCUE_REGION_RESCUE, SECTOR, 17 * SECTOR},
    {RESCUE_REGION_APP_A, A, APP_SIZE},
    {RESCUE_REGION_APP_B, B, APP_SIZE},
    {RESCUE_REGION_IDENTITY, 54 * SECTOR, SECTOR},
    {RESCUE_REGION_STATE_0, J0, SECTOR},
    {RESCUE_REGION_STATE_1, J1, SECTOR},
    {RESCUE_REGION_RESERVED, 57 * SECTOR, 7 * SECTOR}
};

struct fake_nor {
    uint8_t bytes[CAP];
    uint8_t page[PAGE];
    uint8_t opcode, rx;
    uint32_t address;
    size_t frame_bytes;
    size_t journal_reads[2];
    unsigned busy_polls, busy_responses, write_enables, erases, programs;
    bool selected, rx_pending, wel, allow_journal;
};

static struct fake_nor fake;
static uint8_t before[CAP];

static bool within(uint32_t address, size_t size, uint32_t start, uint32_t end)
{
    return address >= start && address < end && size <= end - address;
}

static bool writable(const struct fake_nor *nor, uint32_t address, size_t size)
{
    return within(address, size, B, B + APP_SIZE) ||
           (nor->allow_journal &&
            within(address, size, J0, J1 + SECTOR));
}

static void select_chip(void *context, bool selected)
{
    struct fake_nor *nor = context;
    assert(!nor->rx_pending);
    if (selected) {
        assert(!nor->selected);
        nor->frame_bytes = 0;
        nor->address = 0;
    } else if (nor->selected) {
        const uint32_t address = nor->address;
        const size_t bytes = nor->frame_bytes;
        assert(bytes != 0);
        switch (nor->opcode) {
        case WREN:
            assert(bytes == 1 && !nor->wel && !nor->busy_polls);
            nor->wel = true;
            ++nor->write_enables;
            break;
        case ERASE:
            assert(nor->wel && !nor->busy_polls);
            assert(bytes == 4 && address % SECTOR == 0);
            assert(writable(nor, address, SECTOR));
            memset(nor->bytes + address, 0xff, SECTOR);
            ++nor->erases;
            break;
        case PROGRAM:
            assert(nor->wel && !nor->busy_polls);
            assert(bytes > 4 && bytes <= 4 + PAGE && address % PAGE == 0);
            assert(writable(nor, address, bytes - 4));
            for (size_t i = 0; i < bytes - 4; ++i) {
                assert((nor->bytes[address + i] & nor->page[i]) == nor->page[i]);
                nor->bytes[address + i] &= nor->page[i];
            }
            ++nor->programs;
            break;
        case READ:
            assert(bytes > 4);
            if (within(address, bytes - 4, J0, J0 + SECTOR))
                nor->journal_reads[0] += bytes - 4;
            if (within(address, bytes - 4, J1, J1 + SECTOR))
                nor->journal_reads[1] += bytes - 4;
            break;
        case RDID:
            assert(bytes == 4);
            break;
        case RDSR:
            assert(bytes == 2);
            break;
        default:
            assert(false);
        }
        if (nor->opcode == ERASE || nor->opcode == PROGRAM) {
            nor->wel = false;
            nor->busy_polls = 2;
        }
    }
    nor->selected = selected;
}

static bool tx_ready(void *context)
{
    return !((struct fake_nor *)context)->rx_pending;
}

static bool rx_ready(void *context)
{
    return ((struct fake_nor *)context)->rx_pending;
}

static void tx_byte(void *context, uint8_t byte)
{
    struct fake_nor *nor = context;
    static const uint8_t id[] = {0x20, 0x20, 0x18};
    assert(nor->selected && !nor->rx_pending);
    nor->rx_pending = true;
    nor->rx = 0xff;
    size_t index = nor->frame_bytes++;
    if (index == 0) {
        assert(!nor->busy_polls || byte == RDSR);
        nor->opcode = byte;
        return;
    }

    switch (nor->opcode) {
    case RDID:
        assert(index <= sizeof id && byte == 0);
        nor->rx = id[index - 1];
        break;
    case RDSR:
        assert(index == 1 && byte == 0);
        nor->rx = nor->wel ? WEL : 0;
        if (nor->busy_polls) {
            nor->rx |= WIP;
            --nor->busy_polls;
            ++nor->busy_responses;
        }
        break;
    case READ:
    case ERASE:
    case PROGRAM:
        if (index < 4) {
            nor->address = (nor->address << 8) | byte;
        } else if (nor->opcode == READ) {
            assert(nor->address + index - 4 < CAP && byte == 0);
            nor->rx = nor->bytes[nor->address + index - 4];
        } else {
            assert(nor->opcode == PROGRAM && index - 4 < PAGE);
            nor->page[index - 4] = byte;
        }
        break;
    default:
        assert(false);
    }
}

static uint8_t rx_byte(void *context)
{
    struct fake_nor *nor = context;
    assert(nor->selected && nor->rx_pending);
    nor->rx_pending = false;
    return nor->rx;
}

static int read_flash(void *ctx, uint32_t address, uint8_t *data, size_t size)
{
    return rescue_spi_nor_read(ctx, address, data, size) == RESCUE_SPI_NOR_OK ? 0 : -1;
}

static int erase_flash(void *ctx, uint32_t address)
{
    return rescue_spi_nor_erase_sector(ctx, address) == RESCUE_SPI_NOR_OK ? 0 : -1;
}

static int program_flash(void *ctx, uint32_t address, const uint8_t *data, size_t size)
{
    return rescue_spi_nor_program_page(ctx, address, data, size) == RESCUE_SPI_NOR_OK ? 0 : -1;
}

static void seed_old_image(uint32_t base)
{
    const size_t length = sizeof old_manifest;
    memset(fake.bytes + base, 0xff, APP_SIZE);
    memcpy(fake.bytes + base, old_raw, sizeof old_raw);
    uint8_t *metadata = fake.bytes + base + APP_SIZE - SECTOR;
    metadata[0] = 0;
    memcpy(metadata + 1, "PLM1", 4);
    metadata[5] = (uint8_t)(length >> 8);
    metadata[6] = (uint8_t)length;
    memcpy(metadata + 7, old_digest, sizeof old_digest);
    memcpy(metadata + 39, old_manifest, length);
}

static struct rescue_journal_record seed(void)
{
    memset(fake.bytes, 0x5a, CAP);
    memset(fake.bytes + J0, 0xff, 2 * SECTOR);
    seed_old_image(A);
    seed_old_image(B);
    struct rescue_journal_record head = {
        .sequence = 8, .state = RESCUE_RECORD_STABLE,
        .confirmed.slot = RESCUE_JOURNAL_A, .reason = "fixture"
    };
    memcpy(head.confirmed.digest, old_digest, sizeof old_digest);
    assert(rescue_journal_encode(&head, fake.bytes + J0) == RESCUE_JOURNAL_OK);
    memcpy(before, fake.bytes, CAP);
    return head;
}

static int read_journal(void *ctx, unsigned sector, size_t off, uint8_t *data, size_t size)
{
    assert(sector < 2 && off < SECTOR && size <= SECTOR - off);
    return read_flash(ctx, (sector ? J1 : J0) + (uint32_t)off, data, size);
}

static struct rescue_journal_record read_head(struct rescue_spi_nor *nor)
{
    const struct rescue_journal_io journal = {nor, SECTOR, read_journal, NULL, NULL};
    struct rescue_journal_record head;
    assert(rescue_journal_read(&journal, &head) == RESCUE_JOURNAL_OK);
    return head;
}

static bool return_ok(void *ctx, const void *evidence, const struct rescue_trial_launch *claim)
{
    return evidence == ctx && claim->sequence == 10 &&
           claim->image.slot == RESCUE_JOURNAL_B &&
           memcmp(claim->image.digest, digest, sizeof digest) == 0;
}

static struct wire_session wire={.state=MW_STATE_IDLE};
static uint32_t request_id;
static void be32(uint8_t *p,uint32_t n) {p[0]=(uint8_t)(n>>24);p[1]=(uint8_t)(n>>16);p[2]=(uint8_t)(n>>8);p[3]=(uint8_t)n;}
static uint32_t from32(const uint8_t *p){return (uint32_t)p[0]<<24|(uint32_t)p[1]<<16|(uint32_t)p[2]<<8|p[3];}
static uint8_t reply[MW_RESPONSE_SIZE];
static enum mw_code request(uint8_t op,uint32_t id,uint32_t seq_or_offset,const uint8_t *data,size_t n) {
 uint8_t packet[MW_HEADER_SIZE+MW_MAX_PAYLOAD]={0}; size_t body=0;
 packet[0]=MW_VERSION;packet[1]=op;be32(packet+4,++request_id);
 if(op==MW_BEGIN || op==MW_CHUNK){assert(n<=1024);body=10+n;be32(packet+8,id);be32(packet+12,seq_or_offset);packet[16]=(uint8_t)(n>>8);packet[17]=(uint8_t)n;memcpy(packet+18,data,n);}
 else if(op==MW_SEAL || op==MW_CANCEL){body=4;be32(packet+8,id);}
 packet[2]=(uint8_t)(body>>8);packet[3]=(uint8_t)body;
 assert(mw_decode(&managed_wire_callbacks,&wire,packet,8+body,reply,sizeof reply)==sizeof reply);
 assert(reply[0]==1 && reply[1]==op && from32(reply+4)==request_id);
 return (enum mw_code)reply[9];
}

int main(int argc,char **argv)
{
    (void)argv;
    const struct rescue_journal_record initial = seed();
    const struct rescue_flash_bus bus = {
        &fake, select_chip, tx_ready, rx_ready, tx_byte, rx_byte
    };
    struct rescue_spi_nor nor = {0};
    assert(rescue_spi_nor_init(&nor, &bus, 4, 4) == RESCUE_SPI_NOR_OK);
    assert(nor.geometry.capacity == CAP && nor.geometry.erase_size == SECTOR &&
           nor.geometry.page_size == PAGE);
    const struct rescue_flash_io flash = {&nor, read_flash, erase_flash, program_flash};
    const struct pl_image_policy policy = {
        .profile = PL_TRUSTED_LAN,
        .detected_target = {PL_PANO_G2, PL_REV_B, PL_XC6SLX150_2_FGG484, 1},
        .rescue_api_major = 1,
        .max_image_length = 17 * SECTOR
    };
    struct rescue_update update = {
        &flash, &nor.geometry, map, sizeof map / sizeof map[0], &policy, true, true
    };

    if(argc>1){
        enum { LENGTH=4221965 }; uint8_t chunk[1024];
        struct rescue_journal_binding binding={0};
        assert(pl_managed_init(&update,RESCUE_SLOT_B,0)==PL_UPLOAD_OK);
        assert(request(MW_BEGIN,1,8,product_manifest,sizeof product_manifest)==MW_OK);
        fake.journal_reads[0]=fake.journal_reads[1]=0;
        unsigned count=0;
        for(size_t off=0;off<LENGTH;){
            size_t n=LENGTH-off; if(n>sizeof chunk)n=sizeof chunk;
            for(size_t i=0;i<n;i++)chunk[i]=(uint8_t)((off+i)*19+53);
            assert(request(MW_CHUNK,1,(uint32_t)off,chunk,n)==MW_OK);off+=n;++count;
        }
        assert(fake.journal_reads[0]==(size_t)count*RESCUE_JOURNAL_RECORD_BYTES && fake.journal_reads[1]==(size_t)count*RESCUE_JOURNAL_RECORD_BYTES);
        assert(request(MW_SEAL,1,0,NULL,0)==MW_OK);
        assert(pl_managed_binding(1,&binding) && memcmp(binding.digest,product_digest,32)==0);
        assert(pl_managed_verify(&binding));
        for(size_t i=0;i<LENGTH;i++)assert(fake.bytes[B+i]==(uint8_t)(i*19+53));
        for(size_t i=LENGTH;i<APP_SIZE-SECTOR;i++)assert(fake.bytes[B+i]==0xff);
        assert(memcmp(fake.bytes,before,B)==0);
        assert(memcmp(fake.bytes+B+APP_SIZE,before+B+APP_SIZE,CAP-B-APP_SIZE)==0);
        printf("PASS: %u-byte synthetic image, %u encoded chunks, full SPI transport and independent readback; protected bytes intact\n",LENGTH,count);
        return 0;
    }
    struct rescue_journal_binding staged = {0};
    assert(pl_managed_init(&update,RESCUE_SLOT_B,0)==PL_UPLOAD_OK);
    assert(request(MW_BEGIN,1,(uint32_t)initial.sequence,manifest,sizeof manifest-1)==MW_REJECTED);
    assert(fake.write_enables==0 && fake.erases==0 && fake.programs==0);
    assert(memcmp(fake.bytes,before,CAP)==0);
    assert(request(MW_BEGIN,2,(uint32_t)initial.sequence,manifest,sizeof manifest)==MW_OK);
    assert(request(MW_BEGIN,3,8,manifest,sizeof manifest)==MW_CONFLICT);
    assert(request(MW_STATUS,0,0,NULL,0)==MW_OK && reply[10]==MW_STATE_OPEN && from32(reply+12)==0);
    assert(pl_managed_prepare(8,&staged)==RESCUE_TRIAL_INVALID);
    assert(!pl_managed_verify(&staged));
    fake.journal_reads[0]=fake.journal_reads[1]=0;
    assert(request(MW_CHUNK,2,0,raw,197)==MW_OK);
    assert(reply[10]==MW_STATE_OPEN && from32(reply+12)==197);
    assert(fake.journal_reads[0]==RESCUE_JOURNAL_RECORD_BYTES && fake.journal_reads[1]==RESCUE_JOURNAL_RECORD_BYTES);
    unsigned writes=fake.write_enables;
    assert(request(MW_CHUNK,2,0,raw,197)==MW_CONFLICT && from32(reply+12)==197);
    assert(request(MW_CHUNK,2,198,raw+198,1)==MW_CONFLICT && from32(reply+12)==197);
    assert(request(MW_CHUNK,1,197,raw+197,1)==MW_NOT_FOUND);
    assert(fake.write_enables==writes);
    assert(request(MW_CHUNK,2,197,raw+197,sizeof raw-197)==MW_OK);
    assert(request(MW_SEAL,2,0,NULL,0)==MW_OK && reply[10]==MW_STATE_SEALED);
    assert(request(MW_SEAL,2,0,NULL,0)==MW_NOT_FOUND);
    assert(request(MW_STATUS,0,0,NULL,0)==MW_OK && reply[10]==MW_STATE_SEALED && from32(reply+12)==sizeof raw);
    assert(pl_managed_binding(2,&staged));
    assert(staged.slot==RESCUE_JOURNAL_B);
    assert(memcmp(staged.digest,digest,sizeof digest)==0);
    assert(pl_managed_verify(&staged));
    uint8_t readback[sizeof raw];
    assert(read_flash(&nor, B, readback, sizeof readback) == 0);
    assert(memcmp(readback, raw, sizeof raw) == 0);
    assert(memcmp(fake.bytes, before, B) == 0);
    assert(memcmp(fake.bytes + B + APP_SIZE, before + B + APP_SIZE,
                  CAP - B - APP_SIZE) == 0);

    fake.allow_journal = true;
    assert(pl_managed_prepare( 8, &staged) == RESCUE_TRIAL_OK);
    struct rescue_trial_launch launch = {0};
    assert(pl_managed_start( 9, &launch) == RESCUE_TRIAL_OK);
    assert(launch.sequence == 10 && launch.image.slot == RESCUE_JOURNAL_B);
    int evidence = 1;
    assert(pl_managed_confirm( &launch, NULL, true, return_ok,
                                 &evidence) == RESCUE_TRIAL_CONFIRM_REJECTED);
    assert(pl_managed_confirm( &launch, &evidence, true, return_ok,
                                 &evidence) == RESCUE_TRIAL_OK);
    struct rescue_journal_record head = read_head(&nor);
    assert(head.sequence == 11 && head.confirmed.slot == RESCUE_JOURNAL_B &&
           head.previous.slot == RESCUE_JOURNAL_A);

    assert(pl_managed_rollback( 11) == RESCUE_TRIAL_OK);
    fake.journal_reads[0] = fake.journal_reads[1] = 0;
    head = read_head(&nor);
    assert(fake.journal_reads[0] == SECTOR && fake.journal_reads[1] == SECTOR);
    assert(head.sequence == 12 && head.confirmed.slot == RESCUE_JOURNAL_A &&
           head.previous.slot == RESCUE_JOURNAL_B);
    assert(pl_managed_verify( &head.confirmed));
    assert(pl_managed_verify( &head.previous));

    assert(memcmp(fake.bytes, before, B) == 0);
    assert(memcmp(fake.bytes + B + APP_SIZE, before + B + APP_SIZE,
                  J0 - (B + APP_SIZE)) == 0);
    assert(memcmp(fake.bytes + J1 + SECTOR, before + J1 + SECTOR,
                  CAP - (J1 + SECTOR)) == 0);
    assert(fake.erases > 0 && fake.programs > 0);
    assert(fake.write_enables == fake.erases + fake.programs);
    assert(fake.busy_responses == 2 * fake.write_enables);
    assert(!fake.wel && !fake.busy_polls && !fake.selected && !fake.rx_pending);
    puts("PASS: encoded management requests -> managed streaming -> SPI NOR, replay/offset rejection, 302 journal bytes/chunk, protected bytes, "
         "full journal scans, trial confirmation and rollback");
    return 0;
}
