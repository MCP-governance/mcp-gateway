import unittest

from agent_policy import policy, quota_observation, reserve_blocked


class PolicyChecks(unittest.TestCase):
    def test_auxiliary_and_high_end_cannot_acquire_write_permission(self):
        for agent in ('luna','haiku','astra','fable','mythos'):
            with self.subTest(agent=agent),self.assertRaisesRegex(ValueError,'read-only'):
                policy({'agent_policy':{'profiles':{agent:{'write_enabled':True}}}})

    def test_high_end_effort_is_strictly_below_xhigh(self):
        for agent in ('astra','fable','mythos'):
            for effort in ('xhigh','max'):
                with self.subTest(agent=agent,effort=effort),self.assertRaisesRegex(ValueError,'below xhigh'):
                    policy({'agent_policy':{'profiles':{agent:{'effort':effort}}}})

    def test_roles_keep_provider_identity_and_mythos_requires_explicit_activation(self):
        rules=policy({})
        self.assertFalse(rules['profiles']['mythos']['enabled'])
        self.assertEqual((rules['max_stages'],rules['max_calls']),(16,18))
        with self.assertRaisesRegex(ValueError,'reassigned'):
            policy({'agent_policy':{'profiles':{'sol':{'provider':'claude'}}}})

    def test_quota_age_does_not_replenish_until_reset(self):
        self.assertTrue(reserve_blocked({'status':'warning','remaining_percent':6,'observed_at':1,'reset_at':2000},10,now=1000))
        self.assertTrue(reserve_blocked({'status':'exhausted','remaining_percent':None,'reset_at':None},10,now=1000))
        self.assertFalse(reserve_blocked({'status':'exhausted','remaining_percent':0,'reset_at':900},10,now=1000))

    def test_tied_empty_quota_waits_for_the_latest_limiting_window(self):
        result=quota_observation({'type':'token_count','rate_limits':{'primary':{'used_percent':100,'resets_at':1500},'secondary':{'used_percent':100,'resets_at':2000}}},now=1000)
        self.assertEqual((result['status'],result['remaining_percent'],result['reset_at']),('exhausted',0,2000))


if __name__=='__main__':
    unittest.main()
