"""Existing bounded provider entrypoints enforce the shared descendant boundary."""
import json
import subprocess
import sys
import unittest


@unittest.skipUnless(sys.platform.startswith('linux') or sys.platform == 'darwin',
                     'POSIX inherited descendant containment')
class FabricWorkerContainmentTests(unittest.TestCase):
    def test_model_and_shadow_callbacks_cannot_start_detached_processes(self):
        for name in ('model_worker', 'shadow_worker'):
            with self.subTest(worker=name):
                code = '''
import io,json,subprocess,sys
from thm.runtime.fabric import %s as worker
def attempt(*args):
    subprocess.run([sys.executable,'-c','pass'],start_new_session=True,check=True)
    raise AssertionError('detached child escaped containment')
if hasattr(worker,'replay'):
    worker.replay=attempt
    sys.stdin=io.StringIO(json.dumps({'task':{'operation':'replay'},'limits':{'cpu':2,'io':1048576}}))
    try:worker.main()
    except PermissionError:print('DENIED')
else:
    worker.run=attempt
    sys.stdin=io.StringIO('{}\\n')
    worker.main()
''' % name
                result = subprocess.run([sys.executable, '-c', code], capture_output=True,
                                        text=True, timeout=10, start_new_session=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                if name == 'shadow_worker':
                    self.assertEqual(result.stdout.strip(), 'DENIED')
                else:
                    value = json.loads(result.stdout)
                    self.assertEqual(value['status'], 'failed')
                    self.assertEqual(value['error'], 'PermissionError')
                    self.assertIn('descendant_containment', value)


if __name__ == '__main__':
    unittest.main()
