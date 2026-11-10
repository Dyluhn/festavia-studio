#pragma once
#include "../firmware_stubs/nvs.h"
#define NVS_READONLY 0
typedef struct {size_t free_entries;} nvs_stats_t;
esp_err_t nvs_open_from_partition(const char *,const char *,int,nvs_handle_t *);
esp_err_t nvs_get_blob(nvs_handle_t,const char *,void *,size_t *);
esp_err_t nvs_set_blob(nvs_handle_t,const char *,const void *,size_t);
esp_err_t nvs_erase_all(nvs_handle_t);
esp_err_t nvs_get_stats(const char *,nvs_stats_t *);
void nvs_close(nvs_handle_t);
