// SPDX-License-Identifier: MIT
#pragma once
#include <stdint.h>
typedef union { uint16_t addr_short; uint8_t addr_long[8]; } esp_zb_addr_u;
typedef struct {
    uint8_t status, dst_addr_mode;
    esp_zb_addr_u dst_addr;
    uint8_t dst_endpoint, src_endpoint;
    int tx_time;
    uint32_t asdu_length;
    uint8_t *asdu;
} esp_zb_apsde_data_confirm_t;
typedef struct {
    uint8_t status, dst_addr_mode;
    uint16_t dst_short_addr;
    uint8_t dst_endpoint, src_addr_mode;
    uint16_t src_short_addr;
    uint8_t src_endpoint;
    uint16_t profile_id, cluster_id;
    uint32_t asdu_length;
    uint8_t *asdu;
} esp_zb_apsde_data_ind_t;
