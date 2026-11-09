// SPDX-License-Identifier: MIT
#pragma once
#include <stdbool.h>
#include "cJSON.h"
#include "esp_err.h"
#include "aps/esp_zigbee_aps.h"
// All entry points except init run under the Zigbee lock.
void hm_player_init(void);
cJSON *hm_player_command(const cJSON *request, bool approved);
void hm_player_tick(bool approved);
bool hm_player_confirm(esp_zb_apsde_data_confirm_t confirm);
bool hm_player_receive(esp_zb_apsde_data_ind_t ind);
bool hm_player_busy(void);
unsigned hm_pending_transfers(void);
// Shared sender supplies one sequence namespace for console, HTTP and playback.
esp_err_t hm_send(uint16_t address, uint8_t endpoint, uint16_t cluster,
                  bool specific, int manufacturer, uint8_t command,
                  const uint8_t *payload, size_t size, bool quiet, uint8_t *tsn);
esp_err_t hm_send_animation(uint16_t address, uint8_t endpoint,
                           const uint8_t *payload, size_t size, uint8_t *tsn);
