/* Original MIT tooling: bounded, immutable opt-in DDS storage. No GL calls. */
#include "texture_override.h"
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#ifdef TXO_GUEST_ABI
#include "posix.h"
#endif
#define TXO_INDEX_LIMIT 32768u
#define TXO_FILE_LIMIT (2u * 1024u * 1024u)
size_t txo_metadata_bytes(void) { return sizeof(struct txo_pack); }

static uint32_t txo_u32(const unsigned char *p) {
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static int txo_power(uint32_t n) { return n && n <= 1024 && !(n & (n - 1)); }
static int txo_hex(const char *s) {
    unsigned i;
    if (strlen(s) != 64) return 0;
    for (i = 0; i < 64; i++)
        if (!((s[i] >= '0' && s[i] <= '9') || (s[i] >= 'a' && s[i] <= 'f'))) return 0;
    return 1;
}
static unsigned txo_slot(const char *key) {
    uint32_t hash = UINT32_C(2166136261);
    unsigned i;
    for (i = 0; i < 64; i++) hash = (hash ^ (unsigned char)key[i]) * UINT32_C(16777619);
    return hash % (TXO_MAX_ENTRIES * 2);
}
static void txo_digest_hex(const unsigned char digest[32], char out[65]) {
    static const char hex[] = "0123456789abcdef";
    unsigned i;
    for (i = 0; i < 32; i++) { out[i * 2] = hex[digest[i] >> 4]; out[i * 2 + 1] = hex[digest[i] & 15]; }
    out[64] = 0;
}
static int txo_filename(const char *s) {
    size_t i, n = strlen(s);
    if (!n || n > 95 || s[0] == '.' || strstr(s, "..")) return 0;
    for (i = 0; i < n; i++)
        if (!((s[i] >= 'a' && s[i] <= 'z') || (s[i] >= 'A' && s[i] <= 'Z') ||
              (s[i] >= '0' && s[i] <= '9') || s[i] == '.' || s[i] == '_' || s[i] == '-')) return 0;
    return 1;
}
static int txo_file_size(int fd, size_t limit, size_t *length) {
#ifdef TXO_GUEST_ABI
    /* Existing 32-bit POSIX import avoids musl stat ABI/syscall expansion. */
    struct posix_file_information information;
    if (posix_fstat(fd, &information) || (information.flags & _posix_file_is_directory) ||
        information.size_high || !information.size_low || information.size_low > limit) return 0;
    *length = information.size_low;
#else
    struct stat st;
    if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_size <= 0 || (uint64_t)st.st_size > limit) return 0;
    *length = (size_t)st.st_size;
#endif
    return 1;
}
static unsigned char *txo_read(int dir, const char *name, size_t limit, size_t *length) {
    unsigned char *data;
    size_t used = 0;
    int fd;
    if (!txo_filename(name)) return NULL;
    fd = openat(dir, name, O_RDONLY | O_NOFOLLOW | O_NONBLOCK);
    if (fd < 0) return NULL;
    if (!txo_file_size(fd, limit, length)) {
        close(fd); return NULL;
    }
    data = malloc(*length + 1);
    if (!data) { close(fd); return NULL; }
    while (used < *length) {
        ssize_t count = read(fd, data + used, *length - used);
        if (count <= 0) { free(data); close(fd); return NULL; }
        used += (size_t)count;
    }
    /* A file changed during read is not a valid immutable pack entry. */
    { unsigned char extra; if (read(fd, &extra, 1) != 0) { free(data); close(fd); return NULL; } }
    close(fd);
    data[*length] = 0;
    return data;
}
int txo_describe_dds(const unsigned char *data, size_t length, struct txo_image *out) {
    uint32_t width, height, levels, expected = 0, flags, caps, block, format;
    size_t payload = 0;
    uint32_t w, h;
    if (!data || !out || length < 128 || memcmp(data, "DDS ", 4)) return 0;
    flags = txo_u32(data + 8); caps = txo_u32(data + 108);
    width = txo_u32(data + 16); height = txo_u32(data + 12); levels = txo_u32(data + 28);
    if (txo_u32(data + 4) != 124 || txo_u32(data + 76) != 32 ||
        !(txo_u32(data + 80) & 4) || (flags & 0x1007) != 0x1007 || !(caps & 0x1000) ||
        txo_u32(data + 112) || txo_u32(data + 24) > 1 || (flags & 0x800000) ||
        !txo_power(width) || !txo_power(height)) return 0;
    if (!memcmp(data + 84, "DXT1", 4)) { block = 8; format = 0x0c; }
    else if (!memcmp(data + 84, "DXT3", 4)) { block = 16; format = 0x0e; }
    else if (!memcmp(data + 84, "DXT5", 4)) { block = 16; format = 0x0f; }
    else return 0;
    w = width > height ? width : height;
    do { expected++; w >>= 1; } while (w);
    if (!levels) levels = 1;
    if (levels != expected || (levels > 1 && (!(flags & 0x20000) || (caps & 0x400008) != 0x400008))) return 0;
    w = width; h = height;
    for (expected = 0; expected < levels; expected++) {
        payload += ((w + 3) / 4) * ((h + 3) / 4) * block;
        w = w > 1 ? w / 2 : 1; h = h > 1 ? h / 2 : 1;
    }
    if (payload + 128 != length) return 0;
    memset(out, 0, sizeof(*out));
    out->width = width; out->height = height; out->levels = levels;
    out->xbox_format = format; out->payload_bytes = payload;
    return 1;
}
int txo_source_key(txo_sha256_fn sha, uint32_t fw, uint32_t sw, const void *texels, size_t bytes, char key[65]) {
    static const unsigned char domain[] = "HALO-XGPU-TEX-V1";
    unsigned char digest[32], *input;
    size_t header = sizeof(domain) + 8;
    unsigned i;
    if (!sha || !texels || !bytes || bytes > TXO_FILE_LIMIT || !key) return 0;
    input = malloc(header + bytes);
    if (!input) return 0;
    memcpy(input, domain, sizeof(domain));
    for (i = 0; i < 4; i++) { input[sizeof(domain) + i] = (unsigned char)(fw >> (i * 8));
        input[sizeof(domain) + 4 + i] = (unsigned char)(sw >> (i * 8)); }
    memcpy(input + header, texels, bytes);
    sha(input, (int)(header + bytes), digest); free(input); txo_digest_hex(digest, key);
    return 1;
}
void txo_close(struct txo_pack *pack) {
    unsigned i;
    for (i = 0; i < pack->count; i++) free(pack->entries[i].image.payload);
    if (pack->directory_fd >= 0) close(pack->directory_fd);
    memset(pack, 0, sizeof(*pack)); pack->directory_fd = -1;
}
int txo_open(struct txo_pack *pack, const char *directory, txo_sha256_fn sha) {
    unsigned char *data;
    size_t length;
    char *line, *end;
    memset(pack, 0, sizeof(*pack)); pack->directory_fd = -1;
    if (!directory || !*directory || !sha) return 0;
    pack->directory_fd = open(directory, O_RDONLY | O_DIRECTORY);
    if (pack->directory_fd < 0) return 0;
    data = txo_read(pack->directory_fd, "manifest.index", TXO_INDEX_LIMIT, &length);
    if (!data) { txo_close(pack); return 0; }
    if (memchr(data, 0, length) || length < 22 || memcmp(data, "HALO-XGPU-OVERRIDES-1\n", 22)) goto bad;
    line = (char *)data + 22;
    while (*line) {
        struct txo_entry *entry;
        char extra;
        unsigned slot, w, h;
        if (pack->count == TXO_MAX_ENTRIES || !(end = strchr(line, '\n'))) goto bad;
        *end = 0;
        entry = &pack->entries[pack->count];
        if (sscanf(line, "%64s %64s %u %u %95s %c", entry->source_key, entry->dds_hash,
                   &w, &h, entry->file, &extra) != 5 || !txo_hex(entry->source_key) ||
            !txo_hex(entry->dds_hash) || !txo_power(w) || !txo_power(h) || !txo_filename(entry->file)) goto bad;
        slot = txo_slot(entry->source_key);
        while (pack->slots[slot]) {
            if (!strcmp(pack->entries[pack->slots[slot] - 1].source_key, entry->source_key)) goto bad;
            slot = (slot + 1) % (TXO_MAX_ENTRIES * 2);
        }
        pack->slots[slot] = pack->count + 1;
        entry->source_width = w; entry->source_height = h;
        pack->count++; line = end + 1;
    }
    free(data);
    if (!pack->count) { txo_close(pack); return 0; }
    pack->sha256 = sha; pack->budget_bytes = TXO_BUDGET_BYTES;
    return 1;
bad:
    free(data); txo_close(pack); return 0;
}
const struct txo_image *txo_lookup(struct txo_pack *pack, const char key[65], uint32_t sw, uint32_t sh, uint32_t format) {
    unsigned slot, probes;
    if (pack->directory_fd < 0 || !key || !txo_hex(key)) return NULL;
    slot = txo_slot(key);
    for (probes = 0; probes < TXO_MAX_ENTRIES * 2 && pack->slots[slot];
         probes++, slot = (slot + 1) % (TXO_MAX_ENTRIES * 2)) {
        struct txo_entry *entry = &pack->entries[pack->slots[slot] - 1];
        unsigned char *data, digest[32];
        char hex[65];
        size_t length;
        struct txo_image image;
        if (strcmp(key, entry->source_key)) continue;
        if (entry->source_width != sw || entry->source_height != sh) return NULL;
        if (entry->attempted) return entry->image.payload && entry->image.xbox_format == format ? &entry->image : NULL;
        entry->attempted = 1;
        data = txo_read(pack->directory_fd, entry->file, TXO_FILE_LIMIT, &length);
        if (!data) return NULL;
        pack->sha256(data, (int)length, digest); txo_digest_hex(digest, hex);
        if (strcmp(hex, entry->dds_hash) || !txo_describe_dds(data, length, &image) ||
            image.xbox_format != format || image.width < sw || image.height < sh ||
            image.width > 2 * sw || image.height > 2 * sh || image.width * sh != image.height * sw ||
            image.payload_bytes > pack->budget_bytes || pack->resident_bytes > pack->budget_bytes - image.payload_bytes) {
            free(data); return NULL;
        }
        image.payload = malloc(image.payload_bytes);
        if (!image.payload) { free(data); return NULL; }
        memcpy(image.payload, data + 128, image.payload_bytes); free(data);
        entry->image = image; pack->resident_bytes += image.payload_bytes;
        return &entry->image;
    }
    return NULL;
}
