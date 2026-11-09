// SPDX-License-Identifier: MIT
// Exercise the production renderer at its clock/NVS/radio boundaries.
#include <assert.h>
#include <stdio.h>
#include "../firmware-source/main/player.c"
#include "retained_fixture.h"
static int64_t clock_ms;
static uint8_t sequence;
static unsigned writes,colors,power_queries,dirty_commits;
static bool drop_reply,reject_reply;
unsigned hm_pending_transfers(void) {return 0;}
int64_t esp_timer_get_time(void) {return clock_ms*1000;}
void esp_zb_get_extended_pan_id(uint8_t *out) {memcpy(out,plan_pan,8);}
esp_err_t nvs_set_u8(nvs_handle_t h,const char *key,uint8_t value)
{(void)h;if (!strcmp(key,"paint") && !value) dirty_commits++;return ESP_OK;}
esp_err_t nvs_commit(nvs_handle_t h) {(void)h;return ESP_OK;}
esp_err_t nvs_erase_key(nvs_handle_t h,const char *k) {(void)h;(void)k;return ESP_OK;}
void esp_zb_zdo_nwk_addr_req(esp_zb_zdo_nwk_addr_req_param_t *req,
 void (*cb)(esp_zb_zdp_status_t,esp_zb_zdo_nwk_addr_rsp_t *,void *),void *ctx)
{(void)req;(void)cb;(void)ctx;assert(!"unexpected resolve");}
static void receive(uint8_t cmd,bool specific,const uint8_t *payload,size_t length)
{
 uint8_t frame[HM_MAX_FRAME];size_t n=hm_frame(frame,specific,0x100b,pending_tsn,cmd,payload,length);frame[0]|=8;
 esp_zb_apsde_data_ind_t ind={.src_short_addr=address,.src_endpoint=endpoint,.dst_endpoint=20,.cluster_id=0xfc01,.asdu=frame,.asdu_length=n};
 assert(hm_player_receive(ind));
}
esp_err_t hm_send(uint16_t dst,uint8_t ep,uint16_t cluster,bool specific,int mfg,uint8_t cmd,
 const uint8_t *payload,size_t length,bool quiet,uint8_t *tsn)
{
 (void)quiet;*tsn=++sequence;uint8_t frame[HM_MAX_FRAME];size_t n=hm_frame(frame,specific,mfg,*tsn,cmd,payload,length);
 esp_zb_apsde_data_confirm_t c={.dst_addr.addr_short=dst,.dst_endpoint=ep,.src_endpoint=20,.asdu=frame,.asdu_length=n,.status=0};
 size_t previous=paint_step;
 assert(hm_player_confirm(c));
 if (cluster==6) {assert(cmd==0);power_queries++;return ESP_OK;}
 assert(cluster==0xfc01);
 if (cmd==1 || cmd==3 || cmd==5 || cmd==7) {
  writes++;if (cmd==1) colors++;
  if (pending_paint) assert(paint_step==previous);
  if (drop_reply) return ESP_OK;
  if (!pending_paint) return ESP_OK; // normal geometry-only recovery advances on ACK
  if (cmd==1 || cmd==3) {uint8_t p[]={cmd,reject_reply ? 0x87 : 0};receive(11,false,p,2);}
  else {uint8_t p[]={reject_reply ? 0x87 : 0,0};receive(cmd,true,p,2);}
 } else {
  assert(cmd==4 || cmd==6);
  const packet_t *p=&fixture_checks[cmd==6];
  receive(cmd,true,p->expected,p->expected_length);
 }
 return ESP_OK;
}
esp_err_t hm_send_animation(uint16_t a,uint8_t e,const uint8_t *p,size_t n,uint8_t *t)
{(void)a;(void)e;(void)p;(void)n;(void)t;assert(!"retained scenes cannot stream native palettes");return 1;}
static void reset(void)
{
 free(samples);samples=calloc(1,sizeof(sample_t));assert(samples);sample_count=1;
 memcpy(paint,fixture_paint,sizeof(fixture_paint));paint_count=sizeof(fixture_paint)/sizeof(*fixture_paint);
 memcpy(ready_checks,fixture_checks,sizeof(fixture_checks));ready_count=2;
 cleanup_count=2;cleanup[0]=paint[paint_count-2];cleanup[1]=paint[paint_count-1];
 check_count=2;memcpy(checks,fixture_checks,sizeof(fixture_checks));
 retained_mode=geometry_dirty=durable=playing=resolved=true;
 palette_mode=bank_acked=pending=pending_paint=pending_paint_check=false;
 releasing=restoring=configuring=checking=power_pending=geometry_release=hue_takeover=preserve_off=false;
 pending_sync=sync_requested=resolving=false;
 paint_step=paint_check_step=step=retries=0;clock_ms=started=last_power_reply=last_target_ack=1000;
 last_power=next_due=first_frame=ended=expires=0;
 address=0x1234;endpoint=11;state="playing";reason="requested_start";
 writes=colors=power_queries=dirty_commits=frames_acked=frames_sent=0;drop_reply=reject_reply=false;
}
int main(void)
{
 reset();assert(retained_program(paint,paint_count,27));
 uint8_t saved=paint[2].payload[2];paint[2].payload[2]=1;assert(!retained_program(paint,paint_count,27));paint[2].payload[2]=saved;
 paint[3].payload[6]=0;assert(!retained_program(paint,paint_count,27));
 puts("PASS malformed coverage and unknown record addresses rejected before writes");
 reset();for(clock_ms=1100;clock_ms<=6000;clock_ms+=50)hm_player_tick(true);
 assert(bank_acked && !geometry_dirty && paint_step==paint_count && frames_acked==1 && dirty_commits==1);
 unsigned done=writes;for(clock_ms=6100;clock_ms<=66000;clock_ms+=100)hm_player_tick(true);
 assert(writes==done && power_queries>15 && playing);
 puts("PASS finite27-puck paint waits for ZCL replies then holds without repeated writes");
 reset();drop_reply=true;
 for(clock_ms=1100;clock_ms<16000 && playing;clock_ms+=100)hm_player_tick(true);
 assert(!playing && restoring && !bank_acked && !frames_acked && !strcmp(reason,"delivery_failed"));
 puts("PASS APS success without application replies cannot falsely complete painting");
 reset();reject_reply=true;
 for(clock_ms=1100;clock_ms<6000 && playing;clock_ms+=100)hm_player_tick(true);
 assert(!playing && restoring && !bank_acked && !strcmp(failure_cause,"paint_fixture_rejected"));
 puts("PASS fixture rejection stops painting and retains recovery ownership");
 reset();hue_takeover=true;hue_deadline=30000;
 for(clock_ms=1100;paint_step<4;clock_ms+=50)hm_player_tick(true);
 unsigned oldcolors=colors;assert(geometry_dirty && release_begin("hue_takeover"));
 clock_ms+=2100;hm_player_tick(true);assert(geometry_release && restoring);
 for(unsigned i=0;i<100 && durable;i++){clock_ms+=100;hm_player_tick(true);}
 assert(!durable && !strcmp(state,"released") && colors==oldcolors && !geometry_dirty);
 puts("PASS mid-paint handoff repairs geometry without replaying colors or power");
 reset();geometry_only();assert(geometry_release && restore_power_checked && cleanup_count==2 && check_count==2);
 for(unsigned i=0;i<100 && durable;i++){clock_ms+=100;hm_player_tick(true);}
 assert(!durable && !strcmp(state,"released") && colors==0 && power_queries==0);
 puts("PASS interrupted-handoff geometry recovery emits no color or power commands");
 free(samples);return 0;
}
