import unittest
from live_load import poll_observation

class LoadClientTests(unittest.TestCase):
    def test_list_evidence_during_transient_load_does_not_crash_or_finish(self):
        for data in ([], ['busy'], {'load':[]}, None):
            _, outcome, terminal = poll_observation({'ok':False,'data':data,
                'outcome':'failed_before_change','error':{'code':'EDITOR_UNRESPONSIVE'}})
            self.assertEqual(outcome, 'loading')
            self.assertFalse(terminal)

    def test_terminal_verification_and_failures_stay_distinct(self):
        self.assertTrue(poll_observation({'ok':True,'data':{'load':{'outcome':'loaded_verified'}}})[2])
        self.assertTrue(poll_observation({'ok':False,'data':[],'error':{'code':'LOAD_CONTEXT_CHANGED'}})[2])
