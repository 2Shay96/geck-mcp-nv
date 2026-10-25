"""Synthetic fixtures only; native host optionally runs the actual generated DLL."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from geck_mcp import runtime_companion as c
from geck_mcp.service import Service
from geck_mcp.transport import BridgeError


class CompanionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.p=SimpleNamespace(project_id='fixture',game_root=root/'game',state_dir=root/'state',
                               plugin='Fixture.esp',launcher='native',plugin_path=root/'game/Data/Fixture.esp')
        self.profile={'plugin':'Fixture.esp','probes':[
            {'key':'fuel','kind':'quest_variable','local_form':'00ABCD','variable':'Fuel'},
            {'key':'idle','kind':'quest_variable','local_form':'00ABCD','variable':'IdleFuelUsed'},
            {'key':'error','kind':'quest_variable','local_form':'00ABCD','variable':'SpeedError'}],
            'rules':[{'key':'no_idle_waste','kind':'equals','fields':['idle'],'value':0}]}
        self.model,self.profile_hash=c.canonical(self.profile)
        _,self.module,self.telemetry,self.receipt_path=c.paths(self.p)
        self.module.parent.mkdir(parents=True);self.module.write_bytes(b'synthetic dll')
        self.p.plugin_path.write_bytes(b'synthetic plugin')
        self.dll_hash=c.file_digest(self.module);self.plugin_hash=c.file_digest(self.p.plugin_path)
        self.receipt={'schema_version':1,'project_id':self.p.project_id,'target':str(self.module),
            'game_root':str(self.p.game_root.resolve()),'profile_sha256':self.profile_hash,
            'profile':self.model.model_dump(),'sha256':self.dll_hash,'plugin_sha256':self.plugin_hash}
        c.write_json(self.receipt_path,self.receipt)
        self.doc={'schema_version':1,'adapter':'geck-xnvse-1','pid':123,'started':456,'tick_ms':10000,
                  'epoch':2,'sequence':10,'status':'sampled','plugin':'Fixture.esp','quest_local':'00ABCD',
                  'runtime_prefix':17,'profile_sha256':self.profile_hash,
                  'values':{'Fuel':83,'IdleFuelUsed':7,'SpeedError':-190}}
        c.write_json(self.telemetry,self.doc)
        self.process=patch.object(c,'process_identity',return_value=456)
        self.process.start();self.addCleanup(self.process.stop)
        self.tick=patch.object(c,'ticks',return_value=10500)
        self.tick.start();self.addCleanup(self.tick.stop)

    def snapshot(self):return c.snapshot(self.p,self.profile,self.plugin_hash)

    def test_profile_validation_and_stable_hash(self):
        self.assertEqual(c.canonical(self.model.model_dump())[1],self.profile_hash)
        variants=[]
        for edit in [lambda p:p['probes'][0].update(kind='item_count',variable=None),
                     lambda p:p['probes'][0].update(local_form='000000'),
                     lambda p:p['probes'][0].update(local_form='000001'),
                     lambda p:p['probes'][1].update(variable='fuel')]:
            value=copy.deepcopy(self.profile);edit(value);variants.append(value)
        for value in variants:
            with self.subTest(value=value),self.assertRaises(ValueError):c.canonical(value)

    def test_fresh_rules_and_aliases_missing_not_zero(self):
        result=self.snapshot()
        self.assertEqual(result['values'],{'fuel':83,'idle':7,'error':-190})
        self.assertEqual(result['rules'],[{'key':'no_idle_waste','status':'fail'}])
        self.doc['values']['IdleFuelUsed']=0;c.write_json(self.telemetry,self.doc)
        self.assertEqual(self.snapshot()['rules'][0]['status'],'pass')
        del self.doc['values']['Fuel'];c.write_json(self.telemetry,self.doc)
        with self.assertRaisesRegex(BridgeError,'variables'):self.snapshot()

    def test_stale_future_wrong_process_epoch_and_numeric(self):
        for key,value in [('tick_ms',6000),('tick_ms',11000),('started',457),('epoch',0),
                          ('pid',True),('runtime_prefix',255),('profile_sha256','wrong'),
                          ('quest_local','000001'),('status','compile_error')]:
            with self.subTest(key=key):
                doc={**self.doc,key:value};c.write_json(self.telemetry,doc)
                with self.assertRaises(BridgeError):self.snapshot()
        for value in [float('nan'),float('inf'),True,'missing']:
            doc=copy.deepcopy(self.doc);doc['values']['Fuel']=value;c.write_json(self.telemetry,doc)
            with self.subTest(value=value),self.assertRaises(BridgeError):self.snapshot()

    def test_changed_plugin_dll_and_receipt_rejected(self):
        self.module.write_bytes(b'changed')
        with self.assertRaisesRegex(BridgeError,'DLL changed'):self.snapshot()
        self.module.write_bytes(b'synthetic dll');self.p.plugin_path.write_bytes(b'changed')
        with self.assertRaisesRegex(BridgeError,'Plugin build changed'):self.snapshot()
        self.p.plugin_path.write_bytes(b'synthetic plugin')
        c.write_json(self.receipt_path,{**self.receipt,'game_root':'elsewhere'})
        with self.assertRaisesRegex(BridgeError,'receipt identity'):self.snapshot()

    def test_fresh_comparison_and_new_baseline_guards(self):
        with self.assertRaises(BridgeError):c.snapshot(self.p,self.profile,self.plugin_hash,{})
        before=self.snapshot();self.doc['sequence']+=1;self.doc['values']['Fuel']-=2
        c.write_json(self.telemetry,self.doc)
        after=c.snapshot(self.p,self.profile,self.plugin_hash,before)
        self.assertEqual(after['delta']['fuel'],-2)
        for key,value in [('pid',124),('started',457),('epoch',3),('profile_sha256','x'),
                          ('plugin_sha256','x'),('companion_sha256','x'),('sequence',11),
                          ('values',[]),('values',{'fuel':float('nan'),'idle':7,'error':-190})]:
            with self.subTest(key=key),self.assertRaises(ValueError):c.compare({**before,key:value},after)

    def test_install_ownership_backup_and_rebind(self):
        folder=self.p.state_dir/'companion/builds/test';folder.mkdir(parents=True)
        source=folder/'test.dll';source.write_bytes(b'new dll')
        build={**self.receipt,'dll':str(source),'sha256':c.file_digest(source)}
        with patch.object(c,'game_closed',side_effect=ValueError('still running')):
            with self.assertRaisesRegex(ValueError,'still running'):c.install(self.p,build,self.plugin_hash)
        with patch.object(c,'game_closed'):
            self.module.write_bytes(b'foreign')
            with self.assertRaisesRegex(ValueError,'unowned or modified'):c.install(self.p,build,self.plugin_hash)
            self.module.write_bytes(b'synthetic dll')
            c.install(self.p,build,self.plugin_hash)
            self.assertEqual(self.module.read_bytes(),b'new dll')
            self.assertEqual((self.p.state_dir/'companion/backups'/ (self.dll_hash+'.dll')).read_bytes(),b'synthetic dll')
            self.p.plugin_path.write_bytes(b'new plugin');new_hash=c.file_digest(self.p.plugin_path)
            c.install(self.p,build,new_hash)
            self.assertEqual(json.loads(self.receipt_path.read_text())['plugin_sha256'],new_hash)
            source.write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError,'Build DLL changed'):c.install(self.p,build,new_hash)

    def test_service_wrapper_reports_without_editor_transport(self):
        service=object.__new__(Service);service.project=self.p
        first=service.runtime_snapshot(self.profile,self.plugin_hash)
        self.assertTrue(first['ok'],first)
        self.assertEqual(first['operation'],'geck_runtime_snapshot')
        c.write_json(self.telemetry,{**self.doc,'status':'variable_unavailable','values':{}})
        failed=service.runtime_snapshot(self.profile,self.plugin_hash)
        self.assertFalse(failed['ok']);self.assertIsNone(failed['data'])
        self.assertEqual(failed['error']['code'],'RUNTIME_COMPANION_UNAVAILABLE')

    def test_readiness_separates_installed_fresh_process_build_and_mapping(self):
        result=c.readiness(self.p,self.profile,self.plugin_hash)
        self.assertTrue(result['ready'],result)
        self.assertEqual(result['mapping']['runtimePrefix'],'11')
        for key,value in [('tick_ms',1),('started',457),('profile_sha256','wrong'),('status','plugin_unavailable')]:
            with self.subTest(key=key):
                c.write_json(self.telemetry,{**self.doc,key:value})
                result=c.readiness(self.p,self.profile,self.plugin_hash)
                self.assertTrue(result['installed'])
                self.assertFalse(result['ready'])
                self.assertEqual(result['mapping']['confidence'],'unverified')
                self.assertIsNone(result['mapping']['runtimePrefix'])

    def test_mixed_probe_profile_reports_unsupported_probes_and_manual_route(self):
        mixed=copy.deepcopy(self.profile)
        mixed['probes'].append({'key':'items','kind':'item_count','local_form':'000123'})
        mixed['probes'].append({'key':'state','kind':'disabled','local_form':'000124'})
        result=c.readiness(self.p,mixed,self.plugin_hash)
        self.assertEqual(result['unsupportedProbes'],[{'key':'items','kind':'item_count'},{'key':'state','kind':'disabled'}])
        self.assertFalse(result['ready'])
        self.assertIn('manual',result['reason'])
        self.assertTrue(c.readiness(self.p,mixed,self.plugin_hash,'vanilla')['ready'])
        with self.assertRaises(BridgeError) as caught:c.snapshot(self.p,mixed,self.plugin_hash)
        self.assertEqual(caught.exception.code,'RUNTIME_ADAPTER_UNSUPPORTED')
        self.assertEqual(caught.exception.evidence['unsupportedProbes'],result['unsupportedProbes'])

    def test_missing_companion_preflight_has_exact_paths_and_never_installs(self):
        before={str(p):p.read_bytes() for p in self.p.game_root.rglob('*') if p.is_file()}
        preview=c.preflight(self.p,self.profile)
        self.assertEqual(preview['files']['dll'],str(self.module))
        self.assertFalse(preview['compiler']['available'])
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.p.game_root.rglob('*') if p.is_file()})
        with patch.object(c,'paths',return_value=('missing',self.module.with_name('missing.dll'),self.telemetry,self.receipt_path.with_name('missing.json'))):
            missing=c.readiness(self.p,self.profile,self.plugin_hash)
        self.assertFalse(missing['installed']);self.assertFalse(missing['ready'])
        self.assertIn('unsupported by this read-only adapter',missing['consoleExecution'])

    def test_explicit_save_context_invalidates_old_sample_and_baseline(self):
        before=self.snapshot()
        c.set_save_context(self.p,'new explicit save')
        with self.assertRaisesRegex(BridgeError,'predates explicit'):self.snapshot()
        self.doc['tick_ms']=10600;self.doc['sequence']+=1;c.write_json(self.telemetry,self.doc)
        with patch.object(c,'ticks',return_value=10700):
            after=self.snapshot()
        with self.assertRaisesRegex(ValueError,'changed'):c.compare(before,after)
        self.assertIn('save_context',after)

    @unittest.skipUnless(os.name=='nt' and os.environ.get('GECK_MCP_ZIG'),'requires Windows and GECK_MCP_ZIG compiler path')
    def test_native_generated_dll_six_failure_modes_and_load_lifecycle(self):
        receipt=c.build(self.p,self.profile,os.environ['GECK_MCP_ZIG'])
        dll=Path(receipt['dll']);host=dll.parent/'fake_host.exe'
        for mode,status in [(0,'sampled'),(1,'plugin_unavailable'),(2,'variable_unavailable'),
                            (3,'variable_unavailable'),(4,'compile_error'),(5,'variable_unavailable')]:
            with self.subTest(mode=mode):
                root=dll.parent/str(mode);(root/'Data/NVSE/Plugins').mkdir(parents=True)
                run=subprocess.run([str(host),str(dll),str(mode)],cwd=root,capture_output=True,text=True,timeout=15)
                self.assertEqual(run.returncode,0,run.stdout+run.stderr)
                load=lambda name:json.loads((root/(name+'.json')).read_text())
                sample=load('sample')
                self.assertEqual(sample['status'],status)
                self.assertEqual(sample['profile_sha256'],self.profile_hash)
                self.assertEqual(sample['plugin'],'Fixture.esp')
                self.assertEqual(sample['quest_local'],'00ABCD')
                self.assertGreater(load('reloaded')['epoch'],sample['epoch'])
                self.assertEqual(load('loading')['values'],{})
                self.assertEqual(load('failed')['status'],'load_failed')
                self.assertEqual(load('exited')['status'],'exited')
                self.assertEqual(sample['values'],{'Fuel':83,'IdleFuelUsed':7,'SpeedError':-190} if mode==0 else {})


if __name__=='__main__':unittest.main()
