// SPDX-License-Identifier: MIT
#include "wire.h"
#include <string.h>

static int nibble(char ch)
{
    if (ch >= '0' && ch <= '9') return ch - '0';
    if (ch >= 'a' && ch <= 'f') return ch - 'a' + 10;
    if (ch >= 'A' && ch <= 'F') return ch - 'A' + 10;
    return -1;
}

int hm_unhex(const char *s, uint8_t *out, size_t capacity)
{
    if (!s) return -1;
    size_t length = strlen(s);
    if ((length & 1) || length / 2 > capacity) return -1;
    for (size_t i = 0; i < length / 2; i++) {
        int hi = nibble(s[2 * i]), lo = nibble(s[2 * i + 1]);
        if (hi < 0 || lo < 0) return -1;
        out[i] = (hi << 4) | lo;
    }
    return length / 2;
}

void hm_hex(const uint8_t *in, size_t size, char *out)
{
    static const char digits[] = "0123456789abcdef";
    for (size_t i = 0; i < size; i++) {
        out[i * 2] = digits[in[i] >> 4];
        out[i * 2 + 1] = digits[in[i] & 15];
    }
    out[size * 2] = 0;
}

bool hm_eui64(const char *s, uint8_t out[8])
{
    uint8_t bytes[8];
    if (!s || strlen(s) != 16 || hm_unhex(s, bytes, 8) != 8) return false;
    bool any = false, all_ff = true;
    for (int i = 0; i < 8; i++) {
        out[i] = bytes[7 - i];
        any |= bytes[i] != 0;
        all_ff &= bytes[i] == 255;
    }
    return any && !all_ff;
}

void hm_eui64_text(const uint8_t in[8], char out[17])
{
    uint8_t bytes[8];
    for (int i = 0; i < 8; i++) bytes[i] = in[7 - i];
    hm_hex(bytes, 8, out);
}

bool hm_unicast(uint16_t address, uint8_t endpoint)
{
    // Coordinator and Zigbee broadcast/reserved addresses are excluded.
    return address > 0 && address < 0xfff8 && endpoint > 0 && endpoint <= 240;
}

size_t hm_frame(uint8_t *out, bool specific, int manufacturer, uint8_t sequence,
                uint8_t command, const uint8_t *payload, size_t size)
{
    if (size > HM_MAX_PAYLOAD || manufacturer < -1 || manufacturer > 65535 ||
        (size && !payload)) return 0;
    size_t pos = 0;
    // Client -> server, default response enabled. Manufacturer flag is optional.
    out[pos++] = (specific ? 1 : 0) | (manufacturer >= 0 ? 4 : 0);
    if (manufacturer >= 0) {
        out[pos++] = manufacturer & 255;
        out[pos++] = manufacturer >> 8;
    }
    out[pos++] = sequence;
    out[pos++] = command;
    if (size) memcpy(out + pos, payload, size);
    return pos + size;
}

bool hm_zcl_header(const uint8_t *frame, size_t size, uint8_t *sequence,
                   uint8_t *command, size_t *header_size)
{
    if (!frame || size < 3 || (frame[0] & 3) > 1) return false;
    size_t header = (frame[0] & 4) ? 5 : 3;
    if (size < header) return false;
    *sequence = frame[header - 2];
    *command = frame[header - 1];
    *header_size = header;
    return true;
}

bool hm_palette_frame(const uint8_t *data, size_t size)
{
    // Restricted native repeat bank: brightness, fade, palette, params.
    // Power-on belongs to startup; frames must preserve an external off.
    // The tested fixture requires both the palette and parameters to activate
    // the native renderer. Offset zero preserves its calibrated permutation.
    if (!data || size < 18 || data[0] != 0x52 || data[1] != 1 ||
        data[2] < 1 || data[2] > 254) return false;
    unsigned count = data[6] >> 4;
    return count >= 2 && count <= 9 && !(data[6] & 15) &&
        size == 12 + 3 * count && data[5] == 4 + 3 * count &&
        data[7] == 2 && data[8] == 0 && data[9] == 0 &&
        (data[size-2] == 0 || data[size-2] == 216) && data[size-1] == 0;
}

bool hm_xy_restore_probe(uint16_t x, uint16_t y, unsigned trial,
                         uint16_t *requested_x, uint16_t *requested_y)
{
    // Search only a three-unit neighborhood of the captured 16-bit color.
    // Coordinate conversion near a gamut edge does not have a constant bias.
    static const int8_t first[9][2]={{0,0},{1,0},{0,1},{-1,0},{0,-1},
                                    {1,1},{-1,1},{1,-1},{-1,-1}};
    int dx=0,dy=0;
    if (trial < 9) { dx=first[trial][0];dy=first[trial][1]; }
    else {
        unsigned index=9;bool found=false;
        for (int r=2;r<=3 && !found;r++) for (int a=-r;a<=r && !found;a++) for (int b=-r;b<=r;b++) {
            if (a!=-r && a!=r && b!=-r && b!=r) continue;
            if (index++==trial) {dx=a;dy=b;found=true;break;}
        }
        if (!found) return false;
    }
    int a=(int)x+dx,b=(int)y+dy;
    if (a<0 || b<0 || a>65535 || b>65535 || a+b>65535) return false;
    *requested_x=a;*requested_y=b;return true;
}
