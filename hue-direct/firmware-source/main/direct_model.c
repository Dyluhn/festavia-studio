// SPDX-License-Identifier: MIT
#include "direct_model.h"
#include <math.h>
#include <string.h>

static unsigned bound(unsigned v, unsigned low, unsigned high) { return v<low?low:v>high?high:v; }
// Hue v2 maps brightness to ZCL as 1 + round(percent * 253 / 100).
// Fixture packet levels use a separate 0..254 scale below.
unsigned hd_percent(unsigned level) { return bound((unsigned)lround((level>1?level-1:0)*100.0/253.0),1,100); }
unsigned hd_control_level(unsigned percent) { return bound(1+(unsigned)lround(percent*253.0/100.0),1,254); }
unsigned hd_level(unsigned percent) { return bound((unsigned)lround(percent*254.0/100.0),1,254); }
unsigned hd_temperature_slot(unsigned value, unsigned count) {
    return bound((unsigned)lround((bound(value,153,500)-153)*(count-1)/347.0),0,count-1);
}
unsigned hd_slot_temperature(unsigned slot, unsigned count) {
    return 153+(unsigned)lround(bound(slot,0,count-1)*347.0/(count-1));
}
bool hd_color_valid(hd_color_t c) { return c.x && c.y && (uint32_t)c.x+c.y<=65535; }
static void pack(double x, double y, uint8_t out[3]) {
    unsigned a=bound((unsigned)lround(x*4095.0/0.7347),0,4095);
    unsigned b=bound((unsigned)lround(y*4095.0/0.8264),0,4095);
    out[0]=a; out[1]=(a>>8)|((b&15)<<4); out[2]=b>>4;
}
void hd_pack_color(hd_color_t c, uint8_t out[3]) { pack(c.x/65535.0,c.y/65535.0,out); }
const char *hd_effect_name(unsigned v) {
    static const char *names[]={"static","flow","chase","bounce","color_fade","wave","breathe","heartbeat","snake","individual"};
    return v<HD_EFFECTS?names[v]:"invalid";
}
void hd_defaults(hd_scene_t *s) {
    memset(s,0,sizeof(*s));s->schema=1;s->background_count=3;s->snake_count=2;
    s->brightness=9;s->speed=5;s->width=2;s->cap=19;s->smooth=64;
    // Hue/ZCL xy, with all output brightness owned by the master.
    const hd_color_t palette[]={{44695,19005},{11141,45875},{9830,3932}};
    for(unsigned i=0;i<HD_MAX_PUCKS;i++)s->background[i]=s->pucks[i]=palette[i%3];
    for(unsigned i=0;i<9;i++)s->snake[i]=(hd_color_t){20495,21561};
}
bool hd_scene_valid(const hd_scene_t *s) {
    if(s->schema!=1 || s->background_count<1 || s->background_count>48 || s->snake_count<1 || s->snake_count>8 ||
       s->effect>=HD_EFFECTS || s->brightness<1 || s->brightness>100 || s->speed<1 || s->speed>100 ||
       s->reverse>1 || s->width<1 || s->width>8 || s->span>9 || s->phase>100 || s->cap<1 || s->cap>100 ||
       s->smooth>100)return false;
    for(unsigned i=0;i<48;i++)if(!hd_color_valid(s->background[i]) || !hd_color_valid(s->pucks[i]))return false;
    for(unsigned i=0;i<9;i++)if(!hd_color_valid(s->snake[i]))return false;
    return true;
}
unsigned hd_period(const hd_scene_t *s,unsigned positions) {
    unsigned capacity=positions<9?positions:9;
    if(s->span && s->span<capacity)capacity=s->span;
    return s->background_count<=capacity ? capacity/s->background_count*s->background_count : 0;
}
const char *hd_scene_error(const hd_scene_t *s,unsigned positions) {
    if(!hd_scene_valid(s))return "invalid_saved_configuration";
    if(positions<1 || positions>48)return "fixture_count_outside_1_to_48";
    if(s->effect!=9 && s->background_count>positions)return "palette_exceeds_fixture_count";
    if(s->effect>0 && s->effect<9 && s->background_count>9)return "animation_requires_at_most_9_colors";
    if(s->effect==8 && (hd_period(s,positions)<2 || s->width>=hd_period(s,positions)))return "snake_requires_background_gap";
    return NULL;
}
static double speed(const hd_scene_t *s) { return s->speed/5.0; }
unsigned hd_frames(const hd_scene_t *s) {
    return s->effect==0 || s->effect==9 ? 1 : bound((unsigned)lround(40.0/speed(s)),2,64);
}
unsigned hd_cycle(const hd_scene_t *s) { return bound((unsigned)lround(4000.0/speed(s)),80,600000); }
unsigned hd_peak(const hd_scene_t *s) { return hd_level(s->brightness<s->cap?s->brightness:s->cap); }
static unsigned permute(unsigned i,unsigned count) { return !(i&1)?i:1+2*((i/2+1)%(count/2)); }
static double wrap(double v,double n) { return v-floor(v/n)*n; }
size_t hd_frame(const hd_scene_t *s,unsigned positions,unsigned frame,uint8_t out[82]) {
    if(hd_scene_error(s,positions) || s->effect==9 || s->background_count>9)return 0;
    unsigned n=s->effect==8?hd_period(s,positions):s->background_count, count=hd_frames(s);
    if(frame>=count)return 0;
    double t=frame/(double)count+s->phase/100.0, level=s->brightness<s->cap?s->brightness:s->cap;
    const double tau=6.2831853071795864769;
    if(s->effect==6)level*=0.03+0.97*(sin(tau*t)+1)/2;
    if(s->effect==7) {
        double b=wrap(t,1),a=(b-0.2)/0.065,c=(b-0.4)/0.085;
        level*=0.06+0.94*fmax(exp(-a*a),0.75*exp(-c*c));
    }
    unsigned fade=bound((unsigned)lround((0x400+s->smooth*(0x4000-0x400)/100.0)*2560/65536/100),0,65535);
    if(s->effect==8)fade=bound((unsigned)lround(40.0/speed(s)/count),1,65535);
    if(s->effect==2)fade=0;
    if(s->effect==7 && fade>1)fade=1;
    unsigned wire_count=n==1?2:n;
    memset(out,0,82);out[0]=0x52;out[1]=1;out[2]=bound((unsigned)lround(level*254/100),1,254);
    out[3]=fade;out[4]=fade>>8;out[5]=4+3*wire_count;out[6]=wire_count<<4;out[7]=2;
    for(unsigned r=0;r<n;r++) {
        double x,y;int direction=s->reverse?1:-1;
        if(s->effect==8) {
            double shift=wrap(t,1)*n,whole=floor(shift),fraction=shift-whole;
            unsigned a=(unsigned)wrap(r+direction*whole,n),b=(unsigned)wrap(r+direction*(whole+1),n);
            hd_color_t under=s->background[r%s->background_count];
            hd_color_t ca=a<s->width?s->snake[a%s->snake_count]:under;
            hd_color_t cb=b<s->width?s->snake[b%s->snake_count]:under;
            x=(ca.x+(cb.x-ca.x)*fraction)/65535.0;y=(ca.y+(cb.y-ca.y)*fraction)/65535.0;
        } else {
            bool moving=s->effect>=1 && s->effect<=5;
            double p=s->reverse && !moving?positions-1-r:r;
            if(s->effect==1 || s->effect==2)p+=direction*(s->effect==1?t*n:floor(t*n));
            if(s->effect==3)p+=direction*(double)n*(1-fabs(2*wrap(t,1)-1));
            if(s->effect==4)p=direction*t*n;
            if(s->effect==5)p+=n/3.0*sin(tau*(t+direction*(double)r/n));
            p=wrap(p,n);unsigned a=(unsigned)p%n,b=(a+1)%n;double q=p-floor(p);
            x=(s->background[a].x+(s->background[b].x-s->background[a].x)*q)/65535.0;
            y=(s->background[a].y+(s->background[b].y-s->background[a].y)*q)/65535.0;
        }
        pack(x,y,out+10+3*permute(r,n));
    }
    if(n==1)memcpy(out+13,out+10,3);
    return 12+3*wire_count;
}
