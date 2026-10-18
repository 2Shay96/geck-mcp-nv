/* GECK MCP read-only runtime telemetry. Uses xNVSE's public interfaces.
 * No console input, command execution endpoint, thread injection or engine writes.
 * Compile at most 2 + 2*N expressions once per process; evaluate on main loop only.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <math.h>
#include <string.h>
#include "nvse_abi.h"
#include "runtime_config.h"

static const char *names[]={GMR_VARIABLES};
#define N (sizeof(names)/sizeof(names[0]))
static ScriptAPI *api;
static Messaging *messages;
static void *loaded_expr, *index_expr, *exists_expr[N], *value_expr[N];
static bool compiled, compile_ok, loaded;
static unsigned epoch, sequence, errors;
static DWORD last_tick, process_id;
static ULONGLONG started;
static char target[MAX_PATH], temporary[MAX_PATH];

static bool numeric(void *expr, double *out) {
    Element value={0};
    unsigned before=errors;
    if (!expr || !api->CallFunction(expr,NULL,NULL,&value,0) ||
        errors!=before || value.type!=1 || !isfinite(value.number)) return false;
    *out=value.number;
    return true;
}
static void compile_queries(void) {
    if (compiled) return;
    compiled=true;
    compile_ok=true;
    loaded_expr=api->CompileExpression("IsModLoaded \"" GMR_PLUGIN "\"");
    index_expr=api->CompileExpression("GetModIndex \"" GMR_PLUGIN "\"");
    if (!loaded_expr || !index_expr) compile_ok=false;
    for (unsigned i=0;i<N;i++) {
        char expression[512];
        snprintf(expression,sizeof(expression),"HasVariable \"%s\" (BuildRef (GetModIndex \"" GMR_PLUGIN "\") %u)",names[i],GMR_LOCAL_FORM);
        exists_expr[i]=api->CompileExpression(expression);
        snprintf(expression,sizeof(expression),"GetVariable \"%s\" (BuildRef (GetModIndex \"" GMR_PLUGIN "\") %u)",names[i],GMR_LOCAL_FORM);
        value_expr[i]=api->CompileExpression(expression);
        if (!exists_expr[i] || !value_expr[i]) compile_ok=false;
    }
}
static void publish(const char *status, int prefix, const double *values) {
    /* Same-directory atomic rename: readers see complete documents or old ones.
     * Tick, process creation identity and sequence make old files detectable.
     */
    FILE *f=fopen(temporary,"wb");
    if (!f) return;
    fprintf(f,"{\"schema_version\":1,\"adapter\":\"geck-xnvse-1\",\"pid\":%lu,"
        "\"started\":%llu,\"tick_ms\":%llu,\"epoch\":%u,\"sequence\":%u,"
        "\"status\":\"%s\",\"plugin\":\"" GMR_PLUGIN "\",\"quest_local\":\"" GMR_LOCAL_HEX "\","
        "\"profile_sha256\":\"" GMR_PROFILE_HASH "\","
        "\"runtime_prefix\":%d,\"values\":{",(unsigned long)process_id,started,
        GetTickCount64(),epoch,++sequence,status,prefix);
    if (values) for (unsigned i=0;i<N;i++)
        fprintf(f,"%s\"%s\":%.17g",i?",":"",names[i],values[i]);
    fprintf(f,"}}\n");
    int failed=ferror(f);
    if (fclose(f)!=0) failed=1;
    if (!failed) MoveFileExA(temporary,target,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH);
}
static void sample(void) {
    double present, prefix, values[N];
    compile_queries();
    if (!compile_ok) { publish("compile_error",-1,NULL); return; }
    if (!numeric(loaded_expr,&present) || present!=1) {publish("plugin_unavailable",-1,NULL);return;}
    if (!numeric(index_expr,&prefix) || prefix<0 || prefix>=255 || floor(prefix)!=prefix) {
        publish("identity_error",-1,NULL);return;
    }
    for (unsigned i=0;i<N;i++) {
        double exists;
        if (!numeric(exists_expr[i],&exists) || exists!=1 || !numeric(value_expr[i],&values[i])) {
            publish("variable_unavailable",(int)prefix,NULL);return;
        }
    }
    publish("sampled",(int)prefix,values);
}
static void on_message(Message *message) {
    switch(message->type) {
    case 10: errors++; break; /* RuntimeScriptError: never turn failed calls into zero. */
    case MSG_PRELOAD: case MSG_MENU: case MSG_NEWGAME:
        loaded=false; epoch++; publish("loading",-1,NULL);
        /* NewGame occurs before initialization. Wait for DeferredInit/first loops. */
        if (message->type==MSG_NEWGAME) loaded=true;
        break;
    case MSG_POSTLOAD:
        /* xNVSE carries the success boolean in data, not a bool pointer. */
        loaded=message->data!=NULL; epoch++; publish(loaded?"awaiting_sample":"load_failed",-1,NULL);break;
    case MSG_EXIT: case MSG_EXIT_CONSOLE:
        loaded=false; publish("exited",-1,NULL);break;
    case MSG_LOOP:
        if (GetTickCount()-last_tick<500) break;
        last_tick=GetTickCount();
        if (loaded) sample();
        else publish("no_loaded_game",-1,NULL);
        break;
    }
}
__declspec(dllexport) bool NVSEPlugin_Query(const NVSEInterface *nvse, PluginInfo *info) {
    info->infoVersion=1;info->name=GMR_NAME;info->version=1;
    return !nvse->isEditor && !nvse->isNogore &&
        nvse->nvseVersion>=0x06040090 && nvse->nvseVersion<0x07000000 &&
        nvse->runtimeVersion==0x040020D0;
}
__declspec(dllexport) bool NVSEPlugin_Load(const NVSEInterface *nvse) {
    PluginInfo info;
    if (!NVSEPlugin_Query(nvse,&info)) return false;
    api=nvse->QueryInterface(6);messages=nvse->QueryInterface(2);
    if (!api || !api->CompileExpression || !api->CallFunction || !messages || messages->version<4) return false;
    const char *root=nvse->GetRuntimeDirectory();
    if (!root || strlen(root)>MAX_PATH-85) return false;
    snprintf(target,sizeof(target),"%sData\\NVSE\\Plugins\\" GMR_TELEMETRY,root);
    snprintf(temporary,sizeof(temporary),"%s.tmp",target);
    FILETIME creation,exit,kernel,user;
    if (!GetProcessTimes(GetCurrentProcess(),&creation,&exit,&kernel,&user)) return false;
    started=((ULONGLONG)creation.dwHighDateTime<<32)|creation.dwLowDateTime;
    process_id=GetCurrentProcessId();
    if (!messages->RegisterListener(nvse->GetPluginHandle(),"NVSE",on_message)) return false;
    publish("awaiting_game_load",-1,NULL);
    return true;
}
