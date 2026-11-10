// SPDX-License-Identifier: MIT
#pragma once
#include <stdbool.h>
#include <stdint.h>
uint32_t hm_tx_reserve(uint16_t address,uint8_t endpoint,uint8_t sequence,bool acknowledged,int64_t now_ms);
void hm_tx_cancel(uint32_t ticket);
void hm_tx_confirm(uint16_t address,uint8_t endpoint,uint8_t sequence,bool has_header,int64_t now_ms);
unsigned hm_tx_pending(int64_t now_ms);
