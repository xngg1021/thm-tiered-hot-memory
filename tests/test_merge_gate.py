import copy
import unittest
from scripts.verify_merge_gate import verify, REQUIRED, ARCHIVE, REPOSITORY


def snapshot():
    return dict(repository=REPOSITORY,pr_number=21,head_sha='a'*40,base_sha='b'*40,base_ref='main',state='open',draft=False,
        archive_v1_4_sha=ARCHIVE,merge_method='merge',force_push=False,
        workflow_runs=[dict(name=n,head_sha='a'*40,id=i+1,event='push',status='completed',conclusion='success') for i,n in enumerate(REQUIRED)],
        review=dict(status='reviewed',head_sha='a'*40,unresolved_actionable=0))


class MergeGateTests(unittest.TestCase):
    def test_changed_head_and_archive_refuse(self):
        s=snapshot();self.assertEqual(verify(s,expected_head='a'*40)['merge_method'],'merge')
        for key in ('head_sha','archive_v1_4_sha'):
            changed=copy.deepcopy(s);changed[key]='c'*40
            with self.assertRaises(ValueError):verify(changed,expected_head='a'*40)

    def test_newer_failed_run_and_foreign_sha_cannot_hide(self):
        s=snapshot();r=copy.deepcopy(s['workflow_runs'][0]);r.update(id=10,conclusion='failure');s['workflow_runs'].append(r)
        with self.assertRaises(ValueError):verify(s,expected_head='a'*40)
        s=snapshot();s['workflow_runs'][0]['head_sha']='b'*40
        with self.assertRaises(ValueError):verify(s,expected_head='a'*40)

    def test_review_outage_is_bounded_and_does_not_waive_findings(self):
        s=snapshot();s['review'].update(status='service-unavailable',attempts=2,reason='recorded timeout')
        verify(s,expected_head='a'*40)
        s['review']['unresolved_actionable']=1
        with self.assertRaises(ValueError):verify(s,expected_head='a'*40)


if __name__ == '__main__':unittest.main()
