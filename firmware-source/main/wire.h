// SPDX-License-Identifier: MIT
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define HM_MAX_PAYLOAD 256
#define HM_MAX_FRAME (HM_MAX_PAYLOAD + 5)

// Text EUI-64 is conventional most-significant-byte first. Stack bytes are LE.
bool hm_eui64(const char *s, uint8_t out[8]);
void hm_eui64_text(const uint8_t in[8], char out[17]);
int hm_unhex(const char *s, uint8_t *out, size_t capacity);
void hm_hex(const uint8_t *in, size_t size, char *out);
bool hm_unicast(uint16_t address, uint8_t endpoint);
size_t hm_frame(uint8_t *out, bool specific, int manufacturer, uint8_t sequence,
                uint8_t command, const uint8_t *payload, size_t size);
bool hm_zcl_header(const uint8_t *frame, size_t size, uint8_t *sequence,
                   uint8_t *command, size_t *header_size);
bool hm_palette_frame(const uint8_t *data, size_t size);
bool hm_xy_restore_probe(uint16_t x, uint16_t y, unsigned trial,
                         uint16_t *requested_x, uint16_t *requested_y);
