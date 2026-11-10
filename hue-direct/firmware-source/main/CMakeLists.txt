set(network_deps "")
if(IDF_TARGET STREQUAL "esp32c6")
    list(APPEND network_deps esp_wifi esp_netif esp_event esp_https_server esp_http_client esp_partition spi_flash app_update mbedtls esp_coex bootloader_support)
endif()
idf_component_register(SRCS "main.c" "wire.c" "transfers.c" "network.c" "player.c" "direct.c" "direct_model.c" "direct_program.c" "direct_bridge.c" "direct_json.c" "direct_storage.c" INCLUDE_DIRS "."
    REQUIRES esp-zigbee-lib nvs_flash json esp_timer esp_app_format ${network_deps})
