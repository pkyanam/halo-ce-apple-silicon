/* Original MIT tooling. Single render-thread use; disabled unless explicitly opened. */
#ifndef HALO_TEXTURE_OVERRIDE_H
#define HALO_TEXTURE_OVERRIDE_H
#include <stddef.h>
#include <stdint.h>
#define TXO_MAX_ENTRIES 128
#define TXO_BUDGET_BYTES (64u * 1024u * 1024u)
typedef void (*txo_sha256_fn)(const void *, int, unsigned char *);
struct txo_image {
    uint32_t width, height, levels, xbox_format;
    size_t payload_bytes;
    unsigned char *payload;
};
struct txo_entry {
    char source_key[65], dds_hash[65], file[96];
    uint32_t source_width, source_height;
    int attempted;
    struct txo_image image;
};
struct txo_pack {
    int directory_fd;
    unsigned count;
    size_t resident_bytes, budget_bytes;
    txo_sha256_fn sha256;
    unsigned slots[TXO_MAX_ENTRIES * 2];
    struct txo_entry entries[TXO_MAX_ENTRIES];
};
/* Call on a fresh pack or after txo_close. Returns 1 on success; invalid packs
   return 0 and retain no resources. The caller serializes all operations. */
int txo_open(struct txo_pack *, const char *directory, txo_sha256_fn);
void txo_close(struct txo_pack *);
/* Exact source-storage identity, only on upload/invalidation, never per draw. */
int txo_source_key(txo_sha256_fn, uint32_t format_word, uint32_t size_word,
                   const void *texels, size_t bytes, char key[65]);
/* NULL means use the original. Failed files are cached as misses until restart. */
const struct txo_image *txo_lookup(struct txo_pack *, const char key[65],
    uint32_t source_width, uint32_t source_height, uint32_t xbox_format);
/* Pure decoder: does not allocate or retain data. Exposed for independent fixtures. */
int txo_describe_dds(const unsigned char *, size_t, struct txo_image *);
size_t txo_metadata_bytes(void);
#endif
