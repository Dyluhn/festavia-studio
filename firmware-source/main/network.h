// SPDX-License-Identifier: MIT
#pragma once
#include <stdbool.h>
#include "cJSON.h"
#include "esp_err.h"

// USB provisioning, authenticated HTTPS commands/events and dual-slot OTA (C6).
esp_err_t hm_net_init(void);
esp_err_t hm_net_start(void);
esp_err_t hm_net_configure(const cJSON *request);
void hm_net_info(cJSON *object);
void hm_net_emit(const char *json, int id, bool is_event);
// Application bridge: executes the existing command handler under the ZB lock.
void hm_dispatch(cJSON *request);
