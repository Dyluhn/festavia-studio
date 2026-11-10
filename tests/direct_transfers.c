// SPDX-License-Identifier: MIT
#include <assert.h>
#include <stdio.h>
#include "../hue-direct/firmware-source/main/transfers.c"
int main(void) {
    uint32_t first=hm_tx_reserve(1,11,7,true,0);assert(first && hm_tx_pending(0)==1);
    hm_tx_confirm(2,11,7,true,1);hm_tx_confirm(1,12,7,true,1);hm_tx_confirm(1,11,8,true,1);assert(hm_tx_pending(1)==1);
    hm_tx_confirm(1,11,7,true,2);assert(!hm_tx_pending(2));puts("PASS only the correlated destination/endpoint/sequence retires a request");
    first=hm_tx_reserve(1,11,8,true,10);hm_tx_confirm(1,11,8,true,10);hm_tx_cancel(first);assert(!hm_tx_pending(10));puts("PASS synchronous confirmation before send returns is safe");
    first=hm_tx_reserve(1,11,9,true,20);hm_tx_cancel(first);assert(!hm_tx_pending(20));puts("PASS locally rejected sends leave no phantom backlog");
    hm_tx_reserve(1,11,10,false,100);assert(hm_tx_pending(2099)==1 && !hm_tx_pending(2100));puts("PASS unacknowledged native frames have a bounded two-second drain");
    hm_tx_reserve(1,11,11,true,100);hm_tx_confirm(1,11,11,false,101);assert(hm_tx_pending(30099)==1 && !hm_tx_pending(30100));puts("PASS missing/headerless confirmations expire and cannot accumulate across sessions");
    for(unsigned i=0;i<SLOTS;i++) {assert(hm_tx_reserve(1,11,i,true,40000));}
    assert(!hm_tx_reserve(1,11,99,true,40000));assert(!hm_tx_pending(70000));puts("PASS saturation rejects before transmission and recovers after expiration");
    first=hm_tx_reserve(1,11,1,true,80000);hm_tx_cancel(first);uint32_t newer=hm_tx_reserve(1,11,2,true,80000);hm_tx_cancel(first);assert(newer!=first && hm_tx_pending(80000)==1);puts("PASS a stale cancellation cannot retire a reused slot");
    return 0;
}
