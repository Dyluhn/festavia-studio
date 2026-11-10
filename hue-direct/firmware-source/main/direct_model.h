// SPDX-License-Identifier: MIT
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define HD_MAX_PUCKS 48
#define HD_PRESETS 16
#define HD_EFFECTS 10
typedef struct { uint16_t x, y; } hd_color_t;
typedef struct {
    uint32_t schema;
    hd_color_t background[HD_MAX_PUCKS], snake[9], pucks[HD_MAX_PUCKS];
    uint8_t background_count, snake_count, effect, brightness, speed, reverse;
    uint8_t width, span, phase, cap, smooth;
} hd_scene_t;
typedef struct {
    bool on;
    uint8_t level;
    uint16_t x, y, temperature;
} hd_control_t;

void hd_defaults(hd_scene_t *scene);
bool hd_scene_valid(const hd_scene_t *scene);
const char *hd_scene_error(const hd_scene_t *scene, unsigned positions);
unsigned hd_period(const hd_scene_t *scene, unsigned positions);
unsigned hd_frames(const hd_scene_t *scene);
unsigned hd_cycle(const hd_scene_t *scene);
unsigned hd_peak(const hd_scene_t *scene);
// Returns a single native FC03 sample, or zero when invalid/retained.
size_t hd_frame(const hd_scene_t *scene, unsigned positions, unsigned frame, uint8_t out[82]);
unsigned hd_percent(unsigned level);
unsigned hd_control_level(unsigned percent);
unsigned hd_level(unsigned percent);
unsigned hd_temperature_slot(unsigned temperature, unsigned count);
unsigned hd_slot_temperature(unsigned slot, unsigned count);
bool hd_color_valid(hd_color_t color);
void hd_pack_color(hd_color_t color, uint8_t out[3]);
const char *hd_effect_name(unsigned effect);
