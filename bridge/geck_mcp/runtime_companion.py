"""Optional Windows xNVSE read-only companion: bounded profiles, fresh samples, shared CLI/MCP."""
import ctypes
from ctypes import wintypes as W
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time
import uuid

from .authoring import atomic_write
from .runtime import Profile, evaluate, file_digest
from .transport import BridgeError

NATIVE=Path(__file__).resolve().parents[1]/'native/runtime'


def canonical(profile):
    profile=Profile.model_validate(profile)
    if any(p.kind!='quest_variable' for p in profile.probes):
        raise ValueError('Automatic adapter currently supports quest_variable probes only')
    if len({p.local_form.upper() for p in profile.probes})!=1:
        raise ValueError('Automatic adapter currently supports one quest per profile')
    if int(profile.probes[0].local_form,16)==0:
        raise ValueError('Quest local form cannot be zero')
    if len({p.variable.casefold() for p in profile.probes})!=len(profile.probes):
        raise ValueError('Automatic profile variables must be unique')
    value=profile.model_dump()
    return profile, hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def paths(project):
    token='geck_mcp_'+hashlib.sha256(project.project_id.encode()).hexdigest()[:12]
    base=project.game_root/'Data/NVSE/Plugins'
    return token,base/(token+'.dll'),base/(token+'.json'),project.state_dir/'companion/install.json'


def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    atomic_write(path,(json.dumps(value,indent=2)+'\n').encode())


def build(project,profile,zig):
    """Generate a bounded compile-time profile, then build a 32-bit plugin and test host.

    No game/editor operations, installers, compiler downloads, or arbitrary command text.
    """
    if project.launcher!='native':raise ValueError('Automatic companion supports native Windows only')
    profile,profile_hash=canonical(profile)
    if profile.plugin!=project.plugin:raise ValueError('Profile plugin differs from project')
    zig=Path(zig).resolve(strict=True)
    folder=project.state_dir/'companion/builds'/uuid.uuid4().hex
    folder.mkdir(parents=True)
    token,_,_,_=paths(project)
    macros={'GMR_PLUGIN':json.dumps(profile.plugin),'GMR_LOCAL_FORM':str(int(profile.probes[0].local_form,16))+'u',
            'GMR_LOCAL_HEX':json.dumps(profile.probes[0].local_form.upper()),
            'GMR_VARIABLES':','.join(json.dumps(p.variable) for p in profile.probes),
            'GMR_PROFILE_HASH':json.dumps(profile_hash),'GMR_NAME':json.dumps('GECK MCP '+project.project_id),
            'GMR_TELEMETRY':json.dumps(token+'.json')}
    header='\n'.join('#define '+k+' '+v for k,v in macros.items())+'\n'
    (folder/'runtime_config.h').write_text(header,encoding='ascii')
    for source,output,shared in [('companion.c',token+'.dll',True),('fake_host.c','fake_host.exe',False)]:
        cmd=[str(zig),'cc','-target','x86-windows-gnu','-std=c11','-O2','-Wall','-Wextra','-Werror',
             '-I',str(folder)]
        if shared:cmd+=['-shared']
        subprocess.run(cmd+[str(NATIVE/source),'-o',str(folder/output)],check=True,timeout=300)
    receipt={'schema_version':1,'project_id':project.project_id,'profile':profile.model_dump(),
             'profile_sha256':profile_hash,'dll':str(folder/(token+'.dll')),
             'sha256':file_digest(folder/(token+'.dll')),
             'native_source_sha256':file_digest(NATIVE/'companion.c')}
    write_json(folder/'build.json',receipt)
    return receipt


def game_closed(project):
    """Refuse installation/baseline changes while any FNV process runs; never kill it."""
    if os.name!='nt':raise ValueError('Installation requires native Windows')
    result=subprocess.run(['tasklist','/FI','IMAGENAME eq FalloutNV.exe','/FO','CSV','/NH'],
                          capture_output=True,text=True,check=True,timeout=10)
    if 'falloutnv.exe' in result.stdout.lower():raise ValueError('Quit FNV normally before installing/rebinding the companion')


def install(project,build_receipt,expected_plugin_hash):
    """Own-file-only installation and build binding; game must be closed."""
    game_closed(project)
    profile,profile_hash=canonical(build_receipt['profile'])
    if (build_receipt.get('schema_version')!=1 or build_receipt['project_id']!=project.project_id or
            profile.plugin!=project.plugin or build_receipt['profile_sha256']!=profile_hash):
        raise ValueError('Build receipt/profile does not belong to this project')
    source=Path(build_receipt['dll']).resolve(strict=True)
    build_root=(project.state_dir/'companion/builds').resolve()
    if not source.is_relative_to(build_root) or file_digest(source)!=build_receipt['sha256']:
        raise ValueError('Build DLL changed or is outside project build state')
    plugin=project.game_root/'Data'/project.plugin
    if file_digest(plugin)!=expected_plugin_hash:raise ValueError('Installed plugin hash differs')
    _,target,_,receipt_path=paths(project)
    previous=json.loads(receipt_path.read_text()) if receipt_path.exists() else None
    if target.exists():
        if (not previous or previous.get('project_id')!=project.project_id or
                previous.get('game_root')!=str(project.game_root.resolve()) or
                Path(previous.get('target','')).resolve()!=target.resolve() or
                file_digest(target)!=previous.get('sha256')):
            raise ValueError('Refusing to replace an unowned or modified companion')
        backup=project.state_dir/'companion/backups'/str(previous['sha256']+'.dll')
        if not backup.exists():
            backup.parent.mkdir(parents=True,exist_ok=True)
            with backup.open('xb') as stream:stream.write(target.read_bytes())
    # Retain previous receipt as rollback/ownership evidence even when DLL is unchanged.
    if previous:
        write_json(project.state_dir/'companion/backups'/('install-'+uuid.uuid4().hex+'.json'),previous)
    target.parent.mkdir(parents=True,exist_ok=True)
    atomic_write(target,source.read_bytes())
    receipt={**build_receipt,'target':str(target),'game_root':str(project.game_root.resolve()),
             'plugin_sha256':expected_plugin_hash,'installed_at':time.time()}
    write_json(receipt_path,receipt)
    return {'installed':True,'restart_required':True,'receipt':str(receipt_path),'sha256':receipt['sha256']}


def process_identity(pid,expected_exe,expected_module):
    """Read OS process metadata/module inventory only; never game memory or input."""
    if os.name!='nt':raise ValueError('Automatic runtime reads require native Windows')
    k=ctypes.WinDLL('kernel32',use_last_error=True);p=ctypes.WinDLL('psapi',use_last_error=True)
    k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];k.OpenProcess.restype=W.HANDLE
    k.CloseHandle.argtypes=[W.HANDLE]
    k.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,ctypes.POINTER(W.DWORD)]
    k.GetProcessTimes.argtypes=[W.HANDLE,*([ctypes.POINTER(W.FILETIME)]*4)]
    p.EnumProcessModulesEx.argtypes=[W.HANDLE,ctypes.POINTER(W.HMODULE),W.DWORD,ctypes.POINTER(W.DWORD),W.DWORD]
    p.GetModuleFileNameExW.argtypes=[W.HANDLE,W.HMODULE,W.LPWSTR,W.DWORD]
    handle=k.OpenProcess(0x1000|0x0400|0x0010,False,pid)
    if not handle:raise ValueError('Game process is no longer available')
    try:
        text=ctypes.create_unicode_buffer(32768);length=W.DWORD(len(text))
        if not k.QueryFullProcessImageNameW(handle,0,text,ctypes.byref(length)):raise ctypes.WinError()
        if Path(text.value).resolve()!=expected_exe.resolve():raise ValueError('Wrong game executable')
        times=[W.FILETIME() for _ in range(4)]
        if not k.GetProcessTimes(handle,*[ctypes.byref(t) for t in times]):raise ctypes.WinError()
        started=(times[0].dwHighDateTime<<32)|times[0].dwLowDateTime
        mods=(W.HMODULE*1024)();needed=W.DWORD()
        if not p.EnumProcessModulesEx(handle,mods,ctypes.sizeof(mods),ctypes.byref(needed),3):raise ctypes.WinError()
        if needed.value>ctypes.sizeof(mods):raise ValueError('Module inventory truncated')
        found=set()
        for module in mods[:needed.value//ctypes.sizeof(W.HMODULE)]:
            if p.GetModuleFileNameExW(handle,module,text,len(text)):found.add(Path(text.value).resolve())
        if expected_module.resolve() not in found:raise ValueError('Companion is not loaded; restart FNV through xNVSE')
        if not any(x.name.lower()=='nvse_1_4.dll' for x in found):raise ValueError('xNVSE is not loaded')
        return started
    finally:k.CloseHandle(handle)


def ticks():
    if os.name!='nt':raise ValueError('Automatic runtime reads require native Windows')
    k=ctypes.WinDLL('kernel32');k.GetTickCount64.restype=ctypes.c_ulonglong
    return k.GetTickCount64()


def validate(document,profile,profile_hash,*,pid,started,tick):
    if document.get('schema_version')!=1 or document.get('adapter')!='geck-xnvse-1':
        raise ValueError('Unsupported companion document')
    if document.get('pid')!=pid or document.get('started')!=started:
        raise ValueError('Telemetry belongs to another process')
    age=tick-document.get('tick_ms',-10000)
    if not 0<=age<=3000:raise ValueError('Telemetry stale/future; game must advance frames')
    if (document.get('plugin')!=profile.plugin or document.get('profile_sha256')!=profile_hash or
            document.get('quest_local')!=profile.probes[0].local_form.upper()):
        raise ValueError('Wrong plugin/quest/profile identity')
    if document.get('status')!='sampled':raise ValueError('No complete observation: '+str(document.get('status')))
    prefix=document.get('runtime_prefix')
    if type(prefix)!=int or not 0<=prefix<255:raise ValueError('Invalid runtime mapping')
    values=document.get('values')
    if not isinstance(values,dict) or set(values)!={p.variable for p in profile.probes}:
        raise ValueError('Missing/unexpected variables')
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in values.values()):
        raise ValueError('Invalid numeric observation')
    for key in ('pid','started','epoch','sequence','tick_ms'):
        if type(document.get(key))!=int or document[key]<1:raise ValueError('Invalid '+key)
    return document


def compare(baseline,current):
    fields=('pid','started','epoch','plugin_sha256','companion_sha256','profile_sha256')
    if any(baseline.get(k)!=current.get(k) for k in fields):
        raise ValueError('Game/load/build/profile changed; new baseline required')
    if (type(baseline.get('sequence'))!=int or baseline['sequence']<1 or
            current['sequence']<=baseline['sequence']):raise ValueError('No fresh sample after baseline')
    if not isinstance(baseline.get('values'),dict) or set(current['values'])!=set(baseline['values']):
        raise ValueError('Baseline fields differ')
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in baseline['values'].values()):
        raise ValueError('Invalid baseline values')
    return {k:current['values'][k]-baseline['values'][k] for k in current['values']}


def snapshot(project,profile,expected_plugin_hash,baseline=None):
    try:
        profile,profile_hash=canonical(profile)
        if project.launcher!='native' or profile.plugin!=project.plugin:
            raise ValueError('Automatic adapter needs native Windows and the configured plugin')
        _,module,telemetry,receipt_path=paths(project)
        if not receipt_path.exists():raise ValueError('No companion installed for this project; build/install it first')
        receipt=json.loads(receipt_path.read_text())
        if (receipt['project_id']!=project.project_id or receipt['profile_sha256']!=profile_hash or
                receipt['game_root']!=str(project.game_root.resolve()) or
                Path(receipt['target']).resolve()!=module.resolve()):
            raise ValueError('Installation receipt identity differs')
        if receipt['plugin_sha256']!=expected_plugin_hash or file_digest(project.plugin_path)!=expected_plugin_hash:
            raise ValueError('Plugin build changed; quit FNV and rebind/restart with the checked build')
        if file_digest(module)!=receipt['sha256']:raise ValueError('Companion DLL changed')
        if not telemetry.exists():raise ValueError('Companion awaits normal game restart through xNVSE')
        document=json.loads(telemetry.read_text())
        if type(document.get('pid'))!=int or not 0<document['pid']<2**32:raise ValueError('Invalid process ID')
        started=process_identity(document['pid'],project.game_root/'FalloutNV.exe',module)
        validate(document,profile,profile_hash,pid=document['pid'],started=started,tick=ticks())
        current={**document,'values':{p.key:document['values'][p.variable] for p in profile.probes},
                 'plugin_sha256':expected_plugin_hash,'companion_sha256':receipt['sha256'],
                 'identity':'verified_loaded_companion'}
        checkpoint={'capture':'complete','values':{k:{'value':v} for k,v in current['values'].items()}}
        # evaluate() requires user-attested for the vanilla path; here OS/companion
        # identity replaces the manual observation gate, without claiming atomic frames.
        delta=compare(baseline,current) if baseline is not None else None
        before={'capture':'complete','values':{k:{'value':v} for k,v in baseline['values'].items()}} if baseline is not None else None
        current['rules']=evaluate(profile,checkpoint,before,'user_attested')
        if delta is not None:current['delta']=delta
        return current
    except (OSError,ValueError,KeyError,TypeError) as error:
        raise BridgeError('RUNTIME_COMPANION_UNAVAILABLE',str(error)) from error
