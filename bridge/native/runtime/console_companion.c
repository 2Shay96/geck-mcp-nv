/* Opt-in console actuator, separate from the read-only telemetry DLL.
 * Uses public xNVSE Console/Script/Messaging APIs on the game's main loop.
 * Claim + durable dispatch receipt precede RunScriptLine; claims are never replayed.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wincrypt.h>
#include <stdio.h>
#include <string.h>
#include <ctype.h>
#include <math.h>
#include <stdlib.h>
#include <io.h>
#include "nvse_abi.h"
#include "console_protocol.h"
#include "console_config.h"

static ScriptAPI *scripts;
static ConsoleAPI *console;
static bool loaded, waiting, teleporting;
static ULONGLONG teleport_tick, settled_tick;
static int subject_prefix=-1;
static char resolved_command[513];
static unsigned epoch, sequence, errors;
static DWORD pid;
static ULONGLONG started, last_tick;
static char base[MAX_PATH], plugin[MAX_PATH];
static void *present_expr,*index_expr,*verify_expr;
static ConsoleRequest active;
/* xNVSE owns compiled expressions; bound unique verification allocations. */
static char verify_text[64][512];
static void *verify_cache[64];
static unsigned verify_count;
static char failed_expression[512];
static const char *compile_failure="";
static void *compile_verification(const char *text) {
    for(unsigned i=0;i<verify_count;i++)if(!strcmp(verify_text[i],text))return verify_cache[i];
    if(verify_count>=64){strcpy(failed_expression,text);compile_failure="expression_cache_limit";return NULL;}
    void *expression=scripts->CompileExpression(text);
    if(expression){strcpy(verify_text[verify_count],text);verify_cache[verify_count++]=expression;}
    else {strcpy(failed_expression,text);compile_failure="CompileExpression_returned_NULL";}
    return expression;
}
static bool numeric(void *expr,double *out) {
    Element result={0};unsigned before=errors;
    if(!expr||!scripts->CallFunction(expr,NULL,NULL,&result,0)||before!=errors||result.type!=1||!isfinite(result.number))return false;
    *out=result.number;return true;
}
static void path(char *out,const char *suffix){snprintf(out,MAX_PATH,"%s%s",base,suffix);}
static bool exists(const char *suffix){char name[MAX_PATH];path(name,suffix);return GetFileAttributesA(name)!=INVALID_FILE_ATTRIBUTES;}
static bool atomic_json(const char *suffix,const char *text) {
    char name[MAX_PATH],temp[MAX_PATH];path(name,suffix);snprintf(temp,MAX_PATH,"%s.tmp",name);
    HANDLE file=CreateFileA(temp,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
    if(file==INVALID_HANDLE_VALUE)return false;
    DWORD written=0,length=(DWORD)strlen(text);
    bool ok=WriteFile(file,text,length,&written,NULL)&&written==length&&FlushFileBuffers(file);
    CloseHandle(file);
    return ok&&MoveFileExA(temp,name,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH);
}
static bool context(char *out) {
    char name[MAX_PATH];path(name,".context");FILE *f=fopen(name,"rb");if(!f)return false;
    size_t n=fread(out,1,33,f);int extra=fgetc(f);fclose(f);
    if(n!=32||extra!=EOF)return false;
    out[32]=0;for(unsigned i=0;i<32;i++)if(!isxdigit((unsigned char)out[i]))return false;
    return true;
}
typedef struct {char path[MAX_PATH],hash[65];BY_HANDLE_FILE_INFORMATION info;} HashProof;
static HashProof hash_proofs[32];static unsigned hash_next;
static bool same_file(BY_HANDLE_FILE_INFORMATION a,BY_HANDLE_FILE_INFORMATION b){
    return a.dwVolumeSerialNumber==b.dwVolumeSerialNumber&&a.nFileIndexHigh==b.nFileIndexHigh&&a.nFileIndexLow==b.nFileIndexLow&&
        a.nFileSizeHigh==b.nFileSizeHigh&&a.nFileSizeLow==b.nFileSizeLow&&
        !memcmp(&a.ftLastWriteTime,&b.ftLastWriteTime,sizeof(FILETIME));
}
static bool hash_matches(const char *filename,const char *expected) {
    HCRYPTPROV provider=0;HCRYPTHASH hash=0;unsigned char bytes[4096],digest[32];DWORD length=32;
    char hex[65];bool ok=false;size_t total=0,n;FILE *f=fopen(filename,"rb");if(!f)return false;
    BY_HANDLE_FILE_INFORMATION info={0},after={0};bool cacheable=strcmp(filename,plugin)!=0;
    HANDLE handle=(HANDLE)_get_osfhandle(_fileno(f));
    if(!GetFileInformationByHandle(handle,&info)){fclose(f);return false;}
    ULONGLONG written_time=((ULONGLONG)info.ftLastWriteTime.dwHighDateTime<<32)|info.ftLastWriteTime.dwLowDateTime;
    if(cacheable&&written_time>started){fclose(f);return false;}
    if(cacheable)for(unsigned i=0;i<32;i++)if(!strcmp(hash_proofs[i].path,filename)&&!strcmp(hash_proofs[i].hash,expected)&&same_file(hash_proofs[i].info,info)){fclose(f);return true;}
    if(!CryptAcquireContextA(&provider,NULL,NULL,PROV_RSA_AES,CRYPT_VERIFYCONTEXT)||!CryptCreateHash(provider,CALG_SHA_256,0,0,&hash))goto done;
    while((n=fread(bytes,1,sizeof(bytes),f))!=0){total+=n;if(total>2UL*1024*1024*1024||!CryptHashData(hash,bytes,(DWORD)n,0))goto done;}
    if(ferror(f)||!CryptGetHashParam(hash,HP_HASHVAL,digest,&length,0)||length!=32)goto done;
    for(unsigned i=0;i<32;i++)snprintf(hex+2*i,3,"%02x",digest[i]);
    ok=strcmp(hex,expected)==0&&GetFileInformationByHandle(handle,&after)&&same_file(info,after);
    if(ok&&cacheable){HashProof *proof=&hash_proofs[hash_next++%32];strcpy(proof->path,filename);strcpy(proof->hash,expected);proof->info=after;}
done:
    if(hash)CryptDestroyHash(hash);if(provider)CryptReleaseContext(provider,0);fclose(f);return ok;
}
static bool plugin_matches(void){return hash_matches(plugin,GMC_PLUGIN_HASH);}
static bool mapping(int *prefix) {
    double present,index;
    if(!loaded||!numeric(present_expr,&present)||present!=1||!numeric(index_expr,&index)||index<0||index>=255||floor(index)!=index)return false;
    *prefix=(int)index;return true;
}
static void json_escape(char *out,const char *in) {
    while(*in){unsigned char c=(unsigned char)*in++;if(c=='"'||c=='\\')*out++='\\';
        if(c<32){sprintf(out,"\\u%04x",c);out+=6;}else *out++=(char)c;}
    *out=0;
}
static bool receipt(const char *status,bool sent,bool accepted,const char *effect,double value,bool has_value) {
    char text[5000],number[64],expression[3073];snprintf(number,sizeof(number),"%.17g",value);
    json_escape(expression,failed_expression);
    snprintf(text,sizeof(text),"{\"schema_version\":1,\"id\":\"%s\",\"pid\":%lu,\"started\":\"%llu\",\"epoch\":%u,\"tick_ms\":%llu,\"build_id\":\"" GMC_BUILD_ID "\",\"context\":\"%s\",\"status\":\"%s\",\"sent\":%s,\"acknowledged\":%s,\"effectVerified\":%s,\"value\":%s,\"subjectPlugin\":\"%s\",\"subjectPrefix\":%d,\"subjectHash\":\"%s\",\"nextContext\":\"%s\"}\n",
             active.id,(unsigned long)pid,started,epoch,GetTickCount64(),active.context,status,sent?"true":"false",accepted?"true":"false",effect,has_value?number:"null",active.subject_plugin,subject_prefix,active.subject_hash,active.next_context);
    size_t length=strlen(text);
    if(length<2)return false;
    snprintf(text+length-2,sizeof(text)-length+2,",\"failedExpression\":\"%s\",\"compileFailure\":\"%s\"}\n",expression,compile_failure);
    return atomic_json(".result.json",text);
}
static bool valid_text(const char *s,size_t size) {
    size_t n=0;while(n<size&&s[n]){if((unsigned char)s[n]<32||(unsigned char)s[n]>126)return false;n++;}return n>0&&n<size;
}
static bool safe_line(const char *line) {
    char verb[80];size_t i=0;while(*line==' ')line++;
    while(line[i]&&line[i]!=' '&&i<sizeof(verb)-1){verb[i]=(char)tolower((unsigned char)line[i]);i++;}verb[i]=0;
    const char *denied[]={"load","loadgame","con_loadgame","qqq","quitgame","exitgame","restartgame","bat","runbatch","cow"};
    for(i=0;i<sizeof(denied)/sizeof(denied[0]);i++)if(!strcmp(verb,denied[i]))return false;
    return valid_text(line,513)&&strchr(line,';')==NULL;
}
static bool identity(int *prefix) {
    char current[33];return active.pid==pid&&active.started==started&&active.epoch==epoch&&
        !strcmp(active.build,GMC_BUILD_ID)&&context(current)&&!strcmp(active.context,current)&&
        GetTickCount64()<=active.deadline&&mapping(prefix)&&active.prefix==(unsigned)*prefix&&plugin_matches();
}
static void heartbeat(void) {
    char text[1300],ctx[33]="";int prefix=-1;bool mapped=mapping(&prefix),hash_ok=plugin_matches(),ctx_ok=context(ctx);
    bool api_ok=console&&console->version>=2&&console->RunScriptLine;
    double menu=1;bool gameplay=loaded&&numeric(compile_verification("MenuMode 1007"),&menu)&&menu==0;
    const char *status=teleporting?"teleport_loading":!loaded?"no_loaded_game":!api_ok?"console_api_unavailable":!gameplay?"waiting_for_loading":!mapped?"mapping_unavailable":!hash_ok?"plugin_build_changed":!ctx_ok?"context_unavailable":"ready";
    snprintf(text,sizeof(text),"{\"schema_version\":1,\"adapter\":\"geck-console-1\",\"wire_version\":2,\"pid\":%lu,\"started\":\"%llu\",\"epoch\":%u,\"sequence\":%u,\"tick_ms\":%llu,\"build_id\":\"" GMC_BUILD_ID "\",\"plugin\":\"" GMC_PLUGIN "\",\"plugin_sha256\":\"" GMC_PLUGIN_HASH "\",\"context\":\"%s\",\"runtime_prefix\":%d,\"status\":\"%s\",\"claimPresent\":%s,\"console_api\":%u}\n",
        (unsigned long)pid,started,epoch,++sequence,GetTickCount64(),ctx,prefix,status,exists(".claimed")?"true":"false",api_ok?console->version:0);
    atomic_json(".ready.json",text);
}
static bool subject_mapping(void) {
    subject_prefix=-1;
    if(!active.subject_plugin[0])return true;
    if(active.subject_plugin[64]||active.subject_hash[64])return false;
    size_t n=strlen(active.subject_plugin);
    if(n<5||strstr(active.subject_plugin,"..")||(active.subject_local==0&&active.query_kind!=2)||active.subject_local>0xFFFFFF)return false;
    for(size_t i=0;i<n;i++)if(!(isalnum((unsigned char)active.subject_plugin[i])||strchr("_. -",active.subject_plugin[i])))return false;
    for(unsigned i=0;i<64;i++)if(!isxdigit((unsigned char)active.subject_hash[i]))return false;
    char filename[MAX_PATH],expression[180];double value;
    const char *root=plugin;size_t root_n=strlen(plugin)-strlen(GMC_PLUGIN);
    if(root_n+n>=MAX_PATH)return false;
    memcpy(filename,root,root_n);strcpy(filename+root_n,active.subject_plugin);
    if(!hash_matches(filename,active.subject_hash))return false;
    snprintf(expression,sizeof(expression),"IsModLoaded \"%s\"",active.subject_plugin);
    if(!numeric(compile_verification(expression),&value)||value!=1)return false;
    snprintf(expression,sizeof(expression),"GetModIndex \"%s\"",active.subject_plugin);
    if(!numeric(compile_verification(expression),&value)||value<0||value>=255||floor(value)!=value)return false;
    subject_prefix=(int)value;
    if(active.subject_local){
        snprintf(expression,sizeof(expression),"IsFormValid (BuildRef (GetModIndex \"%s\") %u)",active.subject_plugin,active.subject_local);
        if(!numeric(compile_verification(expression),&value)||value!=1)return false;
    }
    return true;
}
static void *typed_expression(unsigned kind,unsigned local,const char *variable) {
    char expr[512],ref[220];
    const char *name=active.subject_plugin[0]?active.subject_plugin:GMC_PLUGIN;
    snprintf(ref,sizeof(ref),"(BuildRef (GetModIndex \"%s\") %u)",name,local);
    if(kind==1)snprintf(expr,sizeof(expr),"GetQuestRunning %s",ref);
    else if(kind==2)snprintf(expr,sizeof(expr),"GetVariable \"%s\" %s",variable,ref);
    else if(kind==3)snprintf(expr,sizeof(expr),"player.GetItemCount %s",ref);
    else if(kind==4)snprintf(expr,sizeof(expr),"player.GetEquipped %s",ref);
    else if(kind==5)snprintf(expr,sizeof(expr),"player.GetWeaponHealthPerc");
    else if(kind==6)snprintf(expr,sizeof(expr),"player.GetEquippedCurrentHealth %u",(unsigned)strtoul(active.command,NULL,10));
    else return NULL;
    return compile_verification(expr);
}
static bool resolve_line(void) {
    const char *mark=strstr(active.command,"{form}");
    if(!mark){strcpy(resolved_command,active.command);return true;}
    if(subject_prefix<0||strstr(mark+6,"{form}"))return false;
    size_t first=(size_t)(mark-active.command);
    if(strlen(active.command)+2>512)return false;
    memcpy(resolved_command,active.command,first);
    snprintf(resolved_command+first,sizeof(resolved_command)-first,"%02X%06X%s",subject_prefix,active.subject_local,mark+6);
    return true;
}
static void process(void) {
    int prefix;
    if(teleporting){
        if(GetTickCount64()>active.deadline){receipt("effect_not_verified",true,true,"false",0,false);teleporting=false;return;}
        char current[33];double in_cell=0,menu=1;
        bool ready=loaded&&plugin_matches()&&context(current)&&!strcmp(current,active.next_context)&&mapping(&prefix)&&
                   numeric(compile_verification("MenuMode 1007"),&menu)&&menu==0&&numeric(verify_expr,&in_cell)&&in_cell==1;
        if(!ready)settled_tick=0;
        else if(!settled_tick)settled_tick=GetTickCount64();
        else if(GetTickCount64()-settled_tick>=1500&&GetTickCount64()-teleport_tick>=2000){
            receipt("effect_verified",true,true,"true",in_cell,true);teleporting=false;
        }
        return;
    }
    if(waiting){
        if(GetTickCount64()>active.deadline){receipt("effect_not_verified",true,true,"false",0,false);waiting=false;return;}
        if(!identity(&prefix)){receipt("context_changed_after_dispatch",true,true,"null",0,false);waiting=false;return;}
        double value;
        if(subject_mapping()&&numeric(verify_expr,&value)&&value==active.expected){receipt("effect_verified",true,true,"true",value,true);waiting=false;}
        else if(active.deadline-GetTickCount64()<500){receipt("effect_not_verified",true,true,"false",0,false);waiting=false;}
        return;
    }
    if(!exists(".request")||exists(".claimed"))return;
    char request[MAX_PATH],claimed[MAX_PATH];path(request,".request");path(claimed,".claimed");
    if(!MoveFileExA(request,claimed,MOVEFILE_WRITE_THROUGH))return;
    FILE *f=fopen(claimed,"rb");if(!f)return;
    size_t length=fread(&active,1,sizeof(active),f);int extra=fgetc(f);fclose(f);
    if(length!=sizeof(active)||extra!=EOF||memcmp(active.magic,"GMCMD02\0",8)||active.id[32]||active.context[32]||active.build[64]||active.subject_plugin[64]||active.subject_hash[64]||active.next_context[32])return;
    for(unsigned i=0;i<32;i++)if(!isxdigit((unsigned char)active.id[i])||!isxdigit((unsigned char)active.context[i]))return;
    failed_expression[0]=0;compile_failure="";
    if(!console||console->version<2||!safe_line(active.command)||!identity(&prefix)||active.verify_kind>6||active.query_index>1||active.query_kind>6||active.teleport>1||!isfinite(active.expected)){
        receipt("rejected_before_dispatch",false,false,"null",0,false);return;
    }
    if(!subject_mapping()||!resolve_line()){receipt("rejected_before_dispatch",false,false,"null",0,false);return;}
    verify_expr=NULL;
    if(active.query_kind){
        if(active.query_kind==2){
            if(subject_prefix<0){receipt("invalid_query",false,false,"null",0,false);return;}
            receipt("query_verified",false,false,"true",subject_prefix,true);return;
        }
        unsigned slot=(unsigned)strtoul(active.command,NULL,10);
        if(slot>19){receipt("invalid_query",false,false,"null",0,false);return;}
        double value;
        if((active.query_kind==5||active.query_kind==6)&&active.subject_plugin[0]){
            char check[320];
            snprintf(check,sizeof(check),"(player.GetEquippedObject %u) == (BuildRef (GetModIndex \"%s\") %u)",active.query_kind==5?5:slot,active.subject_plugin,active.subject_local);
            if(!numeric(compile_verification(check),&value)||value!=1){receipt("invalid_query",false,false,"null",0,false);return;}
        }
        void *expr=typed_expression(active.query_kind,active.subject_local,"");
        if(!expr||!numeric(expr,&value)){receipt("invalid_query",false,false,"null",0,false);return;}
        receipt("query_verified",false,false,"true",value,true);return;
    }
    bool coc=tolower((unsigned char)resolved_command[0])=='c'&&tolower((unsigned char)resolved_command[1])=='o'&&tolower((unsigned char)resolved_command[2])=='c'&&resolved_command[3]==' ';
    if(coc){
        if(!active.teleport||active.next_context[32]){receipt("rejected_before_dispatch",false,false,"null",0,false);return;}
        for(unsigned i=0;i<32;i++)if(!isxdigit((unsigned char)active.next_context[i])){receipt("rejected_before_dispatch",false,false,"null",0,false);return;}
        const char *cell=resolved_command+4;
        if(!*cell){receipt("invalid_query",false,false,"null",0,false);return;}
        for(unsigned i=0;cell[i];i++)if(!(isalnum((unsigned char)cell[i])||cell[i]=='_')){receipt("invalid_query",false,false,"null",0,false);return;}
        if(subject_prefix<0||!active.subject_local){receipt("invalid_verification",false,false,"null",0,false);return;}
        char expr[320];snprintf(expr,sizeof(expr),"(player.GetParentCell) == (BuildRef (GetModIndex \"%s\") %u)",active.subject_plugin,active.subject_local);
        verify_expr=compile_verification(expr);
        if(!verify_expr){receipt("verification_compile_error",false,false,"null",0,false);return;}
    }
    if(active.verify_kind&&!coc){
        if(!active.verify_form||active.verify_form>0xFFFFFF){receipt("invalid_verification",false,false,"null",0,false);return;}
        if(active.verify_kind==2){
            if(!valid_text(active.variable,65)){receipt("invalid_verification",false,false,"null",0,false);return;}
            for(unsigned i=0;active.variable[i];i++)if(!(isalnum((unsigned char)active.variable[i])||active.variable[i]=='_')){receipt("invalid_verification",false,false,"null",0,false);return;}
        }
        verify_expr=typed_expression(active.verify_kind,active.subject_plugin[0]?active.subject_local:active.verify_form,active.variable);
        if(!verify_expr){receipt("verification_compile_error",false,false,"null",0,false);return;}
    }
    if(active.query_index&&strcmp(active.command,"GetModIndex \"" GMC_PLUGIN "\"")){receipt("invalid_query",false,false,"null",0,false);return;}
    if(!identity(&prefix)||!subject_mapping()||!resolve_line()||!receipt("dispatching",false,false,"null",0,false))return;
    unsigned before=errors;
    if(coc){
        char name[MAX_PATH],temp[MAX_PATH];path(name,".context");snprintf(temp,sizeof(temp),"%s.new",name);
        HANDLE f=CreateFileA(temp,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);DWORD n=0;
        if(f==INVALID_HANDLE_VALUE)return;
        bool ok=WriteFile(f,active.next_context,32,&n,NULL)&&n==32&&FlushFileBuffers(f);CloseHandle(f);
        if(!ok||!MoveFileExA(temp,name,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH))return;
        epoch++;teleporting=true;teleport_tick=GetTickCount64();settled_tick=0;
    }
    bool accepted=console->RunScriptLine(resolved_command,NULL);
    if(!accepted||before!=errors){teleporting=false;receipt("execution_unconfirmed",true,false,"null",0,false);return;}
    if(active.query_index){receipt("query_verified",true,true,"true",(double)prefix,true);return;}
    if(coc){receipt("teleport_pending",true,true,"null",0,false);return;}
    waiting=active.verify_kind!=0;
    receipt(waiting?"verification_pending":"acknowledged",true,true,"null",0,false);
}
static void compile_queries(void) {
    if(!loaded)return;
    if(!present_expr)present_expr=scripts->CompileExpression("IsModLoaded \"" GMC_PLUGIN "\"");
    if(!index_expr)index_expr=scripts->CompileExpression("GetModIndex \"" GMC_PLUGIN "\"");
}
static void on_message(Message *m) {
    if(m->type==10){errors++;return;}
    if(m->type==MSG_PRELOAD||m->type==MSG_MENU||m->type==MSG_NEWGAME){loaded=m->type==MSG_NEWGAME;epoch++;}
    if(m->type==MSG_POSTLOAD){loaded=m->data!=NULL;epoch++;}
    if(m->type==MSG_EXIT||m->type==MSG_EXIT_CONSOLE){loaded=false;epoch++;}
    if(m->type==MSG_LOOP&&GetTickCount64()-last_tick>=500){last_tick=GetTickCount64();compile_queries();process();heartbeat();}
}
__declspec(dllexport) bool NVSEPlugin_Query(const NVSEInterface *nvse,PluginInfo *info) {
    info->infoVersion=1;info->name=GMC_NAME;info->version=1;
    return !nvse->isEditor&&!nvse->isNogore&&nvse->nvseVersion>=0x06040090&&nvse->nvseVersion<0x07000000&&nvse->runtimeVersion==0x040020D0;
}
__declspec(dllexport) bool NVSEPlugin_Load(const NVSEInterface *nvse) {
    PluginInfo info;if(!NVSEPlugin_Query(nvse,&info))return false;
    scripts=nvse->QueryInterface(6);console=nvse->QueryInterface(1);Messaging *messages=nvse->QueryInterface(2);
    if(!scripts||!scripts->CompileExpression||!scripts->CallFunction||!messages||messages->version<4)return false;
    const char *root=nvse->GetRuntimeDirectory();if(!root||strlen(root)>MAX_PATH-100)return false;
    snprintf(base,MAX_PATH,"%sData\\NVSE\\Plugins\\" GMC_TOKEN,root);snprintf(plugin,MAX_PATH,"%sData\\" GMC_PLUGIN,root);
    FILETIME creation,exit,kernel,user;if(!GetProcessTimes(GetCurrentProcess(),&creation,&exit,&kernel,&user))return false;
    pid=GetCurrentProcessId();started=((ULONGLONG)creation.dwHighDateTime<<32)|creation.dwLowDateTime;
    if(!messages->RegisterListener(nvse->GetPluginHandle(),"NVSE",on_message))return false;
    heartbeat();return true;
}
