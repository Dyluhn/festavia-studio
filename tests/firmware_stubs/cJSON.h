// SPDX-License-Identifier: MIT
#pragma once
// Declarations only: JSON command paths are discarded by --gc-sections. The
// native harness exercises the production player state machine, not JSON.
typedef struct cJSON { double valuedouble; int valueint; char *valuestring; } cJSON;
cJSON *cJSON_GetObjectItemCaseSensitive(const cJSON *, const char *);
int cJSON_IsNumber(const cJSON *);
int cJSON_IsString(const cJSON *);
int cJSON_IsArray(const cJSON *);
int cJSON_IsBool(const cJSON *);
int cJSON_IsTrue(const cJSON *);
int cJSON_HasObjectItem(const cJSON *, const char *);
int cJSON_GetArraySize(const cJSON *);
cJSON *cJSON_GetArrayItem(const cJSON *, int);
double cJSON_GetNumberValue(const cJSON *);
cJSON *cJSON_CreateObject(void);
void cJSON_AddBoolToObject(cJSON *, const char *, int);
void cJSON_AddStringToObject(cJSON *, const char *, const char *);
void cJSON_AddNumberToObject(cJSON *, const char *, double);
cJSON *cJSON_Parse(const char *);
void cJSON_Delete(cJSON *);
char *cJSON_PrintUnformatted(const cJSON *);
