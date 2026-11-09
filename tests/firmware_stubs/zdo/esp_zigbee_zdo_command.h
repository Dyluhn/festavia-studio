// SPDX-License-Identifier: MIT
#pragma once
#include <stdint.h>
typedef int esp_zb_zdp_status_t;
#define ESP_ZB_ZDP_STATUS_SUCCESS 0
typedef struct { uint8_t ieee_addr[8]; uint16_t nwk_addr; } esp_zb_zdo_nwk_addr_rsp_t;
typedef struct {
    uint16_t dst_nwk_addr;
    uint8_t request_type, ieee_addr_of_interest[8];
} esp_zb_zdo_nwk_addr_req_param_t;
void esp_zb_zdo_nwk_addr_req(esp_zb_zdo_nwk_addr_req_param_t *,
    void (*)(esp_zb_zdp_status_t, esp_zb_zdo_nwk_addr_rsp_t *, void *), void *);
