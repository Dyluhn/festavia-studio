// SPDX-License-Identifier: MIT
#include "direct_program.h"
#include "wire.h"
#include <math.h>
#include <string.h>
#define MFG 0x100b
static unsigned min(unsigned a,unsigned b) {return a<b?a:b;}
static void put16(uint8_t *p,unsigned v) {p[0]=v;p[1]=v>>8;}
static cJSON *packet(unsigned cluster,unsigned command,const uint8_t *payload,size_t size,int manufacturer,bool specific) {
    char text[165];if(size>82)return NULL;hm_hex(payload,size,text);
    cJSON *p=cJSON_CreateObject();cJSON_AddNumberToObject(p,"cluster",cluster);cJSON_AddNumberToObject(p,"command",command);
    cJSON_AddNumberToObject(p,"manufacturer",manufacturer);cJSON_AddNumberToObject(p,"frame_type",specific?1:0);cJSON_AddStringToObject(p,"payload",text);return p;
}
static void add(cJSON *array,unsigned cluster,unsigned cmd,const uint8_t *p,size_t n,int mfg) {cJSON_AddItemToArray(array,packet(cluster,cmd,p,n,mfg,true));}
static void check(cJSON *array,unsigned cluster,unsigned cmd,const uint8_t *p,size_t n,int mfg,bool specific,unsigned response,const uint8_t *expected,size_t expected_length) {
    cJSON *v=packet(cluster,cmd,p,n,mfg,specific);char text[165];hm_hex(expected,expected_length,text);
    cJSON_AddNumberToObject(v,"response_command",response);cJSON_AddStringToObject(v,"expect",text);cJSON_AddItemToArray(array,v);
}
static void geometry(cJSON *array,bool verify,const hd_snapshot_t *snapshot) {
    const hd_snapshot_t before=*snapshot;
    uint8_t map[22]={0,before.regions},aliases[22]={0,before.regions};
    for(unsigned i=0;i<before.regions;i++) {map[2+2*i]=before.starts[i];map[3+2*i]=before.lengths[i];put16(aliases+2+2*i,before.aliases[i]);}
    if(!verify) {add(array,0xfc01,5,map,2+2*before.regions,MFG);add(array,0xfc01,7,aliases,2+2*before.regions,MFG);}
    else {
        uint8_t response[24]={0};memcpy(response+1,map,2+2*before.regions);uint8_t zero=0;
        check(array,0xfc01,4,&zero,1,MFG,true,4,response,3+2*before.regions);
        memcpy(response+1,aliases,2+2*before.regions);check(array,0xfc01,6,&zero,1,MFG,true,6,response,3+2*before.regions);
    }
}
static void read_check(cJSON *array,unsigned cluster,const uint16_t *attrs,const uint16_t *values,const uint8_t *types,unsigned count) {
    uint8_t request[16],response[48];unsigned size=0;
    for(unsigned i=0;i<count;i++) {
        put16(request+2*i,attrs[i]);put16(response+size,attrs[i]);response[size+2]=0;response[size+3]=types[i];size+=4;
        response[size++]=values[i];if(types[i]==0x21)response[size++]=values[i]>>8;
    }
    check(array,cluster,0,request,2*count,-1,false,1,response,size);
}
cJSON *hd_prepare_program(const hd_scene_t *input,const hd_snapshot_t *snapshot,const char *target,const char *pan,unsigned target_address,unsigned target_endpoint,bool takeover) {
    const hd_scene_t scene=*input;const hd_snapshot_t before=*snapshot;
    cJSON *q=cJSON_CreateObject();cJSON_AddStringToObject(q,"op","player_prepare");
    cJSON_AddStringToObject(q,"ieee",target);cJSON_AddStringToObject(q,"extpan",pan);
    cJSON_AddNumberToObject(q,"address",target_address);cJSON_AddNumberToObject(q,"endpoint",target_endpoint);
    cJSON_AddBoolToObject(q,"hue_takeover",takeover);
    cJSON *restore=cJSON_AddArrayToObject(q,"restore"),*verify=cJSON_AddArrayToObject(q,"verify"),*setup=cJSON_AddArrayToObject(q,"setup"),*ready=cJSON_AddArrayToObject(q,"ready");
    uint8_t sync[]={0,1,0,0,0,0},effect[]={0x20,0,0},level[5],color[8];
    add(restore,6,0,NULL,0,-1);add(restore,0xfc01,3,sync,sizeof(sync),MFG);geometry(restore,false,snapshot);add(restore,0xfc03,0,effect,3,MFG);
    if(before.mode==2) {put16(color,before.temperature);put16(color+2,10);color[4]=color[5]=1;add(restore,0x300,10,color,6,-1);}
    else {put16(color,min(65535,before.x+1));put16(color+2,min(65535,before.y+1));put16(color+4,10);color[6]=color[7]=1;add(restore,0x300,7,color,8,-1);}
    level[0]=before.level;put16(level+1,10);level[3]=level[4]=1;add(restore,8,0,level,5,-1);add(restore,6,before.on?1:0,NULL,0,-1);
    geometry(verify,true,snapshot);uint16_t attrs[]={0},values[]={before.on};uint8_t types[]={0x10};read_check(verify,6,attrs,values,types,1);
    values[0]=before.level;types[0]=0x20;read_check(verify,8,attrs,values,types,1);
    uint16_t ca[]={3,4,7,8},cv[]={before.x,before.y,before.temperature,before.mode};uint8_t ct[]={0x21,0x21,0x21,0x30};read_check(verify,0x300,ca,cv,ct,4);
    add(setup,6,0,NULL,0,-1);add(setup,0xfc01,3,sync,6,MFG);add(setup,0xfc03,0,effect,3,MFG);
    level[0]=hd_peak(&scene);put16(level+1,0);level[3]=level[4]=1;add(setup,8,0,level,5,-1);add(setup,6,1,NULL,0,-1);
    geometry(ready,true,snapshot);values[0]=1;types[0]=0x10;read_check(ready,6,attrs,values,types,1);
    return q;
}
cJSON *hd_load_program(const hd_scene_t *input,unsigned positions,const hd_snapshot_t *snapshot) {
    const hd_scene_t scene=*input;const hd_snapshot_t before=*snapshot;
    const char *invalid=hd_scene_error(&scene,positions);if(invalid)return NULL;
    bool retained=scene.effect==9 || scene.background_count>9;
    cJSON *q=cJSON_CreateObject();cJSON_AddStringToObject(q,"op","player_load");cJSON_AddStringToObject(q,"transport",retained?"retained":"palette");
    cJSON_AddNumberToObject(q,"fps",retained?1:10);cJSON_AddNumberToObject(q,"cycle_ms",hd_cycle(&scene));cJSON *samples=cJSON_AddArrayToObject(q,"samples");
    if(retained) {
        cJSON_AddItemToArray(samples,cJSON_CreateString("000000000004"));cJSON_AddNumberToObject(q,"positions",positions);
        cJSON *paint=cJSON_AddArrayToObject(q,"paint");uint8_t sync[]={0,1,0,0,0,0},aliases[22]={0,before.regions};
        for(unsigned i=0;i<before.regions;i++)put16(aliases+2+2*i,before.aliases[i]);
        add(paint,0xfc01,3,sync,6,MFG);add(paint,0xfc01,7,aliases,2+2*before.regions,MFG);
        unsigned capacity=before.regions, batch=positions<=capacity?positions:capacity>2?capacity-2:positions,counter=0;
        for(unsigned first=0;first<positions;first+=batch) {
            unsigned last=min(positions-1,first+batch-1),count=0;uint8_t starts[10],lengths[10];
            if(first) {starts[count]=0;lengths[count++]=first;}
            for(unsigned p=first;p<=last;p++) {starts[count]=p;lengths[count++]=1;}
            if(last+1<positions) {starts[count]=last+1;lengths[count++]=positions-1-last;}
            while(count<capacity) {
                unsigned j=0;while(j<count && lengths[j]<=1)j++;
                if(j==count) {cJSON_Delete(q);return false;}
                memmove(starts+j+2,starts+j+1,count-j-1);memmove(lengths+j+2,lengths+j+1,count-j-1);
                starts[j+1]=starts[j]+1;lengths[j+1]=lengths[j]-1;lengths[j]=1;count++;
            }
            uint8_t map[22]={0,count},frame[82]={0};unsigned length=6;counter++;frame[0]=counter;frame[4]=0;frame[5]=4;
            for(unsigned i=0;i<count;i++) {
                map[2+2*i]=starts[i];map[3+2*i]=lengths[i];
                if(lengths[i]==1 && starts[i]>=first && starts[i]<=last) {
                    unsigned puck=scene.reverse?positions-1-starts[i]:starts[i];hd_color_t color=scene.effect==9?scene.pucks[puck]:scene.background[puck%scene.background_count];
                    put16(frame+length,before.aliases[i]);put16(frame+length+2,(unsigned)lround((scene.brightness<scene.cap?scene.brightness:scene.cap)*2047.0/100)<<5);
                    hd_pack_color(color,frame+length+4);length+=7;
                }
            }
            add(paint,0xfc01,5,map,2+2*count,MFG);add(paint,0xfc01,1,frame,length,MFG);
        }
        geometry(paint,false,snapshot);
    } else for(unsigned f=0;f<hd_frames(&scene);f++) {
        uint8_t data[82];size_t length=hd_frame(&scene,positions,f,data);if(!length) {cJSON_Delete(q);return false;}
        char hex[165];hm_hex(data,length,hex);cJSON_AddItemToArray(samples,cJSON_CreateString(hex));
    }
    return q;
}
