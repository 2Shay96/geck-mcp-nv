/* Executes the actual 32-bit plugin under a fake xNVSE host, never FNV. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "nvse_abi.h"
#include "runtime_config.h"
static void (*callback)(Message *);
static int compile_count, mode;
static bool listener(uint32_t handle,const char *sender,void (*fn)(Message *)) {
    if(handle!=42 || strcmp(sender,"NVSE")) return false;
    callback=fn;return true;
}
static void *compile_expr(const char *text) {
    compile_count++;
    if(mode==4) return NULL;
    return _strdup(text);
}
static bool call(void *expression,void *object,void *container,Element *out,uint8_t count,...) {
    (void)object;(void)container;(void)count;
    const char *text=expression;
    out->type=1;out->number=1;
    if(strstr(text,"IsModLoaded")) out->number=mode==1?0:1;
    else if(!strncmp(text,"GetModIndex",11)) out->number=11;
    else if(strstr(text,"HasVariable")) out->number=mode==2?0:1;
    else if(strstr(text,"GetVariable")) {
        if(mode==3) {out->number=NAN;return true;}
        if(mode==5) {Message error={"NVSE",10,0,NULL};callback(&error);return true;}
        if(strstr(text,"\"Fuel\"")) out->number=83;
        else if(strstr(text,"\"IdleFuelUsed\"")) out->number=7;
        else if(strstr(text,"\"ObservedSpeed\"")) out->number=60;
        else if(strstr(text,"\"ExpectedSpeed\"")) out->number=250;
        else if(strstr(text,"\"SpeedError\"")) out->number=-190;
    } else return false;
    return true;
}
static ScriptAPI scripts={.CallFunction=call,.CompileExpression=compile_expr};
static Messaging messaging={.version=4,.RegisterListener=listener};
static void *query(uint32_t id){return id==6?(void *)&scripts:id==2?(void *)&messaging:NULL;}
static uint32_t handle(void){return 42;}
static const char *root(void){return ".\\";}
static void send(unsigned type,void *data){Message m={"NVSE",type,0,data};callback(&m);}
static void copy_result(const char *label){
    char dest[100];snprintf(dest,sizeof(dest),"%s.json",label);
    if(!CopyFileA("Data\\NVSE\\Plugins\\" GMR_TELEMETRY,dest,FALSE)) exit(20);
}
int main(int argc,char **argv){
    mode=argc>2?atoi(argv[2]):0;
    HMODULE dll=LoadLibraryA(argv[1]);if(!dll){printf("load error %lu\n",GetLastError());return 2;}
    bool (*q)(const NVSEInterface *,PluginInfo *)=(void *)GetProcAddress(dll,"NVSEPlugin_Query");
    bool (*load)(const NVSEInterface *)=(void *)GetProcAddress(dll,"NVSEPlugin_Load");
    if(!q||!load)return 3;
    NVSEInterface api={.nvseVersion=0x06040090,.runtimeVersion=0x040020D0,.QueryInterface=query,
        .GetPluginHandle=handle,.GetRuntimeDirectory=root};
    PluginInfo info;
    api.isEditor=1;if(q(&api,&info))return 4;api.isEditor=0;
    api.runtimeVersion=1;if(q(&api,&info))return 5;api.runtimeVersion=0x040020D0;
    api.nvseVersion=0x06030000;if(q(&api,&info))return 6;api.nvseVersion=0x06040090;
    if(!q(&api,&info)||!load(&api))return 7;
    copy_result("startup");
    send(MSG_POSTLOAD,(void *)1);Sleep(510);send(MSG_LOOP,NULL);copy_result("sample");
    int before=compile_count;
    Sleep(510);send(MSG_LOOP,NULL);if(compile_count!=before)return 8;
    send(MSG_PRELOAD,NULL);copy_result("loading");
    send(MSG_POSTLOAD,NULL);copy_result("failed");
    send(MSG_POSTLOAD,(void *)1);Sleep(510);send(MSG_LOOP,NULL);copy_result("reloaded");
    send(MSG_EXIT,NULL);copy_result("exited");
    printf("native host checks passed; compiled expressions=%d; mode=%d\n",compile_count,mode);
    return 0;
}
