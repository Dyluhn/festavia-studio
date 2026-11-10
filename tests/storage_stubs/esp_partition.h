#pragma once
#include "esp_flash.h"
#include <stdbool.h>
#define ESP_PARTITION_TYPE_ANY 0xff
#define ESP_PARTITION_SUBTYPE_ANY 0xff
#define ESP_PARTITION_TYPE_DATA 1
#define ESP_PARTITION_SUBTYPE_DATA_NVS 2
typedef struct {unsigned address,size,type,subtype;esp_flash_t *flash_chip;bool encrypted;char label[17];} esp_partition_t;
typedef struct iterator *esp_partition_iterator_t;
const esp_partition_t *esp_partition_find_first(unsigned,unsigned,const char *);
esp_partition_iterator_t esp_partition_find(unsigned,unsigned,const char *);
const esp_partition_t *esp_partition_get(esp_partition_iterator_t);
esp_partition_iterator_t esp_partition_next(esp_partition_iterator_t);
void esp_partition_iterator_release(esp_partition_iterator_t);
esp_err_t esp_partition_register_external(esp_flash_t *,size_t,size_t,const char *,unsigned,unsigned,const esp_partition_t **);
