"""Original endpoint-lease regressions; no game, assets or network sockets."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

MODULE=Path(__file__).resolve().parents[1]/'overlay/tools/macos_network_test_lock.py'
spec=importlib.util.spec_from_file_location('network_lease',MODULE)
lease_module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(lease_module)


class NetworkLeaseTests(unittest.TestCase):
    def test_conflict_and_release(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(lease_module.tempfile,'gettempdir',return_value=directory):
            first=lease_module.acquire_network_test_lock()
            try:
                with self.assertRaisesRegex(RuntimeError,'serialize'):
                    lease_module.acquire_network_test_lock()
            finally:
                first.close()
            lease_module.acquire_network_test_lock().close()

    def test_process_exit_releases_lease(self):
        script='''import importlib.util,os,sys
s=importlib.util.spec_from_file_location('lease',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
m.tempfile.gettempdir=lambda:sys.argv[2]
lease=m.acquire_network_test_lock()
os._exit(0)
'''
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run([sys.executable,'-c',script,str(MODULE),directory],check=True)
            with patch.object(lease_module.tempfile,'gettempdir',return_value=directory):
                lease_module.acquire_network_test_lock().close()


if __name__=='__main__':unittest.main()
