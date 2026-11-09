set(network_deps "")
if(IDF_TARGET STREQUAL "esp32c6")
    list(APPEND network_deps esp_wifi esp_netif esp_event esp_https_server app_update mbedtls esp_coex bootloader_support)
endif()
idf_component_register(SRCS "main.c" "wire.c" "network.c" "player.c" INCLUDE_DIRS "."
    REQUIRES esp-zigbee-lib nvs_flash json esp_timer esp_app_format ${network_deps})
