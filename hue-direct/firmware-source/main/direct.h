// SPDX-License-Identifier: MIT
#pragma once
#include "cJSON.h"
#include "esp_zigbee_core.h"
#include "esp_zigbee_endpoint.h"
#include "aps/esp_zigbee_aps.h"
#include "direct_model.h"
#define HD_HUE_SCENES 160

void hd_init(void);
void hd_register(esp_zb_ep_list_t *endpoints);
void hd_action(const esp_zb_zcl_set_attr_value_message_t *message);
bool hd_receive(esp_zb_apsde_data_ind_t indication);
void hd_tick(bool approved);
cJSON *hd_command(const cJSON *request, bool approved);
bool hd_enabled(void);
bool hd_owns_player(void);
bool hd_raw_allowed(const char *operation);
void hd_scene_store(const esp_zb_zcl_store_scene_message_t *message);
void hd_scene_recall(const esp_zb_zcl_recall_scene_message_t *message);
void hd_group_command(bool grouped);
void hd_bridge_start(void);
void hd_bridge_details(cJSON *response);
bool hd_bridge_configure(const cJSON *bridge);
void hd_bridge_observation(bool connected, bool entertainment, const cJSON *light);
cJSON *hd_bridge_replay(void);
void hd_bridge_replayed(bool success);
