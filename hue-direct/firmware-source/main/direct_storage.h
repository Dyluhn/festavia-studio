// SPDX-License-Identifier: MIT
#pragma once
#include "nvs.h"
#include "cJSON.h"
// Separate settings from the recovery journal. Initializes/migrates once at boot.
esp_err_t hd_storage_init(void);
void hd_storage_details(cJSON *response);
esp_err_t hd_storage_open(int mode,nvs_handle_t *handle);
