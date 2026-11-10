// SPDX-License-Identifier: MIT
#pragma once
#include <stdbool.h>
#include <stddef.h>
// Validate the whole Hue entertainment response without allocating a JSON tree.
bool hd_entertainment(const char *data,size_t size,bool *active);
