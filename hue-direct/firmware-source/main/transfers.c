// SPDX-License-Identifier: MIT
// Only current requests belong to the drain, never cumulative lost callbacks.
#include "transfers.h"
#define SLOTS 64
typedef struct {uint32_t ticket;uint16_t address;uint8_t endpoint,sequence;int64_t deadline;} transfer_t;
static transfer_t transfers[SLOTS];
static uint32_t next_ticket;
unsigned hm_tx_pending(int64_t now_ms) {
    unsigned count=0;
    for(unsigned i=0;i<SLOTS;i++) {
        if(transfers[i].ticket && now_ms>=transfers[i].deadline)transfers[i].ticket=0;
        if(transfers[i].ticket)count++;
    }
    return count;
}
uint32_t hm_tx_reserve(uint16_t address,uint8_t endpoint,uint8_t sequence,bool acknowledged,int64_t now_ms) {
    hm_tx_pending(now_ms);
    for(unsigned i=0;i<SLOTS;i++)if(!transfers[i].ticket) {
        if(!++next_ticket)++next_ticket;
        // Native animation explicitly disables APS retries. Its two-second
        // drain is separate from acknowledged setup/recovery requests.
        transfers[i]=(transfer_t){next_ticket,address,endpoint,sequence,now_ms+(acknowledged?30000:2000)};
        return next_ticket;
    }
    return 0;
}
void hm_tx_cancel(uint32_t ticket) {
    for(unsigned i=0;i<SLOTS;i++)if(transfers[i].ticket==ticket) {transfers[i].ticket=0;return;}
}
void hm_tx_confirm(uint16_t address,uint8_t endpoint,uint8_t sequence,bool has_header,int64_t now_ms) {
    hm_tx_pending(now_ms);
    // A headerless/late callback cannot retire an unrelated newer request.
    if(!has_header)return;
    for(unsigned i=0;i<SLOTS;i++)if(transfers[i].ticket && transfers[i].address==address && transfers[i].endpoint==endpoint && transfers[i].sequence==sequence) {transfers[i].ticket=0;return;}
}
