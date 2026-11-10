// SPDX-License-Identifier: MIT
#pragma once
#include "direct_model.h"
#include "cJSON.h"
typedef struct {
    bool on;
    uint8_t level,mode,capacity,regions;
    uint16_t x,y,temperature,aliases[10];
    uint8_t starts[10],lengths[10],fc03[128];
    unsigned fc03_length;
} hd_snapshot_t;
cJSON *hd_prepare_program(const hd_scene_t *,const hd_snapshot_t *,const char *target,const char *pan,unsigned address,unsigned endpoint,bool takeover);
cJSON *hd_load_program(const hd_scene_t *,unsigned positions,const hd_snapshot_t *);
