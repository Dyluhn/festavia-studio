// SPDX-License-Identifier: MIT
// Bounded JSON walker: large channel lists never become a heap-allocated DOM.
#include "direct_json.h"
#include <string.h>
#include <stdint.h>
typedef struct {const char *p,*end;unsigned depth;} reader;
static void ws(reader *r) {while(r->p<r->end && (*r->p==' ' || *r->p=='\n' || *r->p=='\r' || *r->p=='\t'))r->p++;}
static bool take(reader *r,char c) {ws(r);if(r->p==r->end || *r->p!=c)return false;r->p++;return true;}
static bool string(reader *r,const char **start,size_t *length) {
    if(!take(r,'"'))return false;
    const char *s=r->p;
    while(r->p<r->end) {
        unsigned c=(uint8_t)*r->p++;
        if(c=='"') {*start=s;*length=r->p-s-1;return true;}
        if(c<32)return false;
        if(c=='\\') {
            if(r->p==r->end)return false;
            c=*r->p++;
            if(c=='u') {for(unsigned i=0;i<4;i++) {if(r->p==r->end)return false;
            c=*r->p++;if(!((c>='0' && c<='9') || (c>='a' && c<='f') || (c>='A' && c<='F')))return false;}}
            else if(!strchr("\"\\/bfnrt",c))return false;
        }
    }
    return false;
}
static bool equal(const char *s,size_t n,const char *literal) {return n==strlen(literal) && !memcmp(s,literal,n);}
static bool literal(reader *r,const char *s) {size_t n=strlen(s);if((size_t)(r->end-r->p)<n || memcmp(r->p,s,n))return false;r->p+=n;return true;}
static bool number(reader *r) {
    const char *p=r->p;if(p<r->end && *p=='-')p++;
    if(p==r->end)return false;
    if(*p=='0')p++;else {if(*p<'1' || *p>'9')return false;while(p<r->end && *p>='0' && *p<='9')p++;}
    if(p<r->end && *p=='.') {p++;const char *a=p;while(p<r->end && *p>='0' && *p<='9')p++;if(p==a)return false;}
    if(p<r->end && (*p=='e' || *p=='E')) {p++;if(p<r->end && (*p=='+' || *p=='-'))p++;const char *a=p;while(p<r->end && *p>='0' && *p<='9')p++;if(p==a)return false;}
    r->p=p;return true;
}
static bool skip(reader *r) {
    ws(r);if(r->p==r->end || ++r->depth>24)return false;
    char c=*r->p;bool ok=false;const char *s;size_t n;
    if(c=='{' || c=='[') {
        r->p++;char close=c=='{'?'}':']';ws(r);
        if(r->p<r->end && *r->p==close) {r->p++;ok=true;}
        else for(;;) {
            if(c=='{' && (!string(r,&s,&n) || !take(r,':')))break;
            if(!skip(r))break;
            if(take(r,close)) {ok=true;break;}
            if(!take(r,','))break;
        }
    } else if(c=='"')ok=string(r,&s,&n);
    else if(c=='t')ok=literal(r,"true");else if(c=='f')ok=literal(r,"false");else if(c=='n')ok=literal(r,"null");else ok=number(r);
    r->depth--;return ok;
}
static bool resource(reader *r,bool *active) {
    if(!take(r,'{'))return false;
    bool seen=false;
    for(;;) {
        const char *key,*s;size_t n,len;
        if(!string(r,&key,&n) || !take(r,':'))return false;
        if(equal(key,n,"status")) {
            if(seen || !string(r,&s,&len))return false;
            seen=true;
            if(equal(s,len,"active"))*active=true;else if(!equal(s,len,"inactive"))return false;
        } else if(!skip(r))return false;
        if(take(r,'}'))return seen;
        if(!take(r,','))return false;
    }
}
bool hd_entertainment(const char *data,size_t size,bool *active) {
    if(!data || !active || size>32768)return false;
    reader r={data,data+size,0};bool found=false,errors=false,value=false;
    if(!take(&r,'{'))return false;
    for(;;) {
        const char *key;size_t n;if(!string(&r,&key,&n) || !take(&r,':'))return false;
        if(equal(key,n,"errors")) {if(errors || !take(&r,'[') || !take(&r,']'))return false;errors=true;}
        else if(equal(key,n,"data")) {
            if(found || !take(&r,'['))return false;
            found=true;
            if(!take(&r,']'))for(;;) {if(!resource(&r,&value))return false;if(take(&r,']'))break;if(!take(&r,','))return false;}
        } else if(!skip(&r))return false;
        if(take(&r,'}'))break;
        if(!take(&r,','))return false;
    }
    ws(&r);if(r.p!=r.end || !found || !errors)return false;*active=value;return true;
}
