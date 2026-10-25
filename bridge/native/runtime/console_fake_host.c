/* Tests the actual actuator DLL against synthetic public xNVSE interfaces, never FNV. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "nvse_abi.h"
#include "console_protocol.h"
#include "console_config.h"
static void (*callback)(Message *);
static int mode,executions;
static bool initialization_complete;
static bool listener(uint32_t handle,const char *sender,void (*fn)(Message *)){(void)handle;(void)sender;callback=fn;return true;}
static void *compile(const char *text){
    if(!initialization_complete)exit(40);
    /* A permissive compiler hid the real vanilla-cell EditorID failure. */
    if(strstr(text,"GetInCell"))return NULL;
    if(strstr(text,"GetParentCell")){
        if(strcmp(text,"(player.GetParentCell) == (BuildRef (GetModIndex \"Other.esp\") 2048)"))exit(42);
        if(mode==28)return NULL;
    }
    return _strdup(text);
}
static bool call(void *expr,void *object,void *container,Element *out,uint8_t count,...){
    (void)object;(void)container;(void)count;const char *text=expr;out->type=1;out->number=1;
    if(strstr(text,"IsFormValid"))out->number=mode==24?0:1;
    else if(strstr(text,"GetItemCount")){if(mode==21)return false;out->number=5+executions;}
    else if(strstr(text,"GetParentCell"))out->number=mode==22?0:1;
    else if(strstr(text,"MenuMode"))out->number=0;
    else if(strstr(text,"GetWeaponHealthPerc"))out->number=66;
    else if(strstr(text,"GetEquippedCurrentHealth"))out->number=132;
    else if(strstr(text,"GetEquippedObject"))out->number=1;
    else if(strstr(text,"GetEquipped"))out->number=1;
    else if(strstr(text,"IsModLoaded")&&strstr(text,"Other.esp"))out->number=mode==18?0:1;
    else if(strstr(text,"GetQuestRunning"))out->number=executions>0&&mode!=8?1:0;
    else if(strstr(text,"GetVariable"))out->number=executions>0?7:0;
    else if(!strncmp(text,"GetModIndex",11))out->number=strstr(text,"Other.esp")?12:17;
    return true;
}
static bool run(const char *text,void *object){
    (void)object;if(strcmp(text,"GetModIndex \"" GMC_PLUGIN "\"")&&strcmp(text,"startquest 11000800")&&strcmp(text,"player.AddItemHealthPercent 0C000800 1 0.66")&&strcmp(text,"coc TestCell"))exit(25);
    executions++;return mode!=6;
}
static ConsoleAPI console={.version=3,.RunScriptLine=run};
static ScriptAPI scripts={.CallFunction=call,.CompileExpression=compile};
static Messaging messaging={.version=4,.RegisterListener=listener};
static void *query(uint32_t id){return id==6?(void *)&scripts:id==2?(void *)&messaging:id==1&&mode!=10?(void *)&console:NULL;}
static uint32_t handle(void){return 42;}
static const char *root(void){return ".\\";}
static void send(unsigned type,void *data){Message message={"NVSE",type,0,data};callback(&message);}
static void copy_result(const char *suffix,const char *name){
    char source[MAX_PATH];snprintf(source,MAX_PATH,"Data\\NVSE\\Plugins\\" GMC_TOKEN "%s",suffix);
    if(!CopyFileA(source,name,FALSE))exit(20);
}
static void write_file(const char *suffix,const void *data,size_t size){
    char name[MAX_PATH];snprintf(name,MAX_PATH,"Data\\NVSE\\Plugins\\" GMC_TOKEN "%s",suffix);FILE *f=fopen(name,"wb");if(!f)exit(21);
    if(fwrite(data,1,size,f)!=size||fclose(f))exit(22);
}
int main(int argc,char **argv){
    if(argc<2)return 1;mode=argc>2?atoi(argv[2]):0;
    HMODULE dll=LoadLibraryA(argv[1]);if(!dll)return 2;
    bool (*load)(const NVSEInterface *)=(void *)GetProcAddress(dll,"NVSEPlugin_Load");
    NVSEInterface api={.nvseVersion=0x06040090,.runtimeVersion=0x040020D0,.QueryInterface=query,.GetPluginHandle=handle,.GetRuntimeDirectory=root};
    char ctx[33]="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";write_file(".context",ctx,32);
    if(!load(&api))return 3;
    initialization_complete=true;
    send(MSG_POSTLOAD,(void *)1);Sleep(510);send(MSG_LOOP,NULL);copy_result(".ready.json","ready.json");
    FILETIME creation,exit,kernel,user;GetProcessTimes(GetCurrentProcess(),&creation,&exit,&kernel,&user);
    ConsoleRequest request={0};memcpy(request.magic,"GMCMD02\0",8);strcpy(request.id,"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");strcpy(request.context,ctx);strcpy(request.build,GMC_BUILD_ID);
    request.pid=GetCurrentProcessId();request.started=((ULONGLONG)creation.dwHighDateTime<<32)|creation.dwLowDateTime;request.epoch=1;request.deadline=GetTickCount64()+1800;request.prefix=17;
    strcpy(request.command,"startquest 11000800");request.verify_kind=1;request.verify_form=0x800;request.expected=1;
    if(mode==1)request.pid++;
    if(mode==2)request.epoch++;
    if(mode==3)request.deadline=1;
    if(mode==4)request.prefix=10;
    if(mode==5)strcpy(request.command,"load SomeSave");
    if(mode==7){strcpy(request.command,"GetModIndex \"" GMC_PLUGIN "\"");request.verify_kind=0;request.query_index=1;}
    if(mode==9){FILE *f=fopen("Data\\" GMC_PLUGIN,"wb");fputs("newer plugin",f);fclose(f);}
    if(mode==11)strcpy(request.context,"cccccccccccccccccccccccccccccccc");
    if(mode>=13){
        if(!CopyFileA("Data/" GMC_PLUGIN,"Data/Other.esp",FALSE))return 41;
        strcpy(request.subject_plugin,"Other.esp");strcpy(request.subject_hash,GMC_PLUGIN_HASH);request.subject_local=0x800;
        request.verify_kind=0;strcpy(request.command,"player.AddItemHealthPercent {form} 1 0.66");
        if(mode==14){request.query_kind=2;strcpy(request.command,"5");}
        if(mode==15||mode==21){request.query_kind=3;strcpy(request.command,"5");}
        if(mode==16){request.verify_kind=3;request.expected=6;}
        if(mode==17||mode==22||mode==23||mode==28||mode==29){
            strcpy(request.command,"coc TestCell");request.teleport=mode!=23;
            strcpy(request.next_context,"dddddddddddddddddddddddddddddddd");request.deadline=GetTickCount64()+4000;
            if(mode==29){request.subject_plugin[0]=0;request.subject_local=0;}
        }
        if(mode==19)memset(request.subject_hash,'0',64);
        if(mode==20){request.query_kind=6;strcpy(request.command,"5");}
        if(mode==25){request.query_kind=5;strcpy(request.command,"5");}
        if(mode==26){request.query_kind=4;strcpy(request.command,"5");}
        if(mode==27){FILE *f=fopen("Data/Other.esp","wb");fputs("changed other plugin",f);fclose(f);}
    }
    write_file(".request",&request,sizeof(request));Sleep(510);send(MSG_LOOP,NULL);copy_result(".result.json","initial.json");
    if(mode==12)send(MSG_PRELOAD,NULL);
    for(int i=0;i<(mode==22?8:4);i++){Sleep(510);send(MSG_LOOP,NULL);}
    copy_result(".result.json","final.json");
    write_file(".request",&request,sizeof(request));Sleep(510);send(MSG_LOOP,NULL);
    int expected=(mode==0||mode==6||mode==7||mode==8||mode==12||mode==13||mode==16||mode==17||mode==22)?1:0;
    if(executions!=expected)return 23;
    printf("console host passed; mode=%d; executions=%d\n",mode,executions);return 0;
}
