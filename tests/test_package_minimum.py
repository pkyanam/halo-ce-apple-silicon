import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('packager',Path(__file__).parents[1]/'overlay/tools/macos_package_app.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

class DeploymentTests(unittest.TestCase):
    def test_arm64_slice_selected(self):
        with patch.object(p,'run',return_value='cmd LC_BUILD_VERSION\nplatform 1\nminos 14.0\nsdk 26.0\n') as run:
            self.assertEqual(p.minimum_macos(Path('engine')), '14.0')
            self.assertEqual(run.call_args.args[:3], ('otool','-arch','arm64'))
    def test_legacy_command(self):
        with patch.object(p,'run',return_value='cmd LC_VERSION_MIN_MACOSX\nversion 13.4\nsdk 15.0\n'):
            self.assertEqual(p.minimum_macos(Path('library')), '13.4')
    def test_numeric_order_not_lexical(self):
        self.assertEqual(max(['9.0','14.0','15.2'],key=p.version_tuple),'15.2')
    def test_missing_metadata_rejected(self):
        with patch.object(p,'run',return_value='cmd LC_UUID\nuuid ignored\n'):
            with self.assertRaisesRegex(ValueError,'Missing'):p.minimum_macos(Path('library'))
    def test_ios_rejected(self):
        with patch.object(p,'run',return_value='cmd LC_BUILD_VERSION\nplatform 2\nminos 14.0\n'):
            with self.assertRaisesRegex(ValueError,'Non-macOS'):p.minimum_macos(Path('library'))

if __name__=='__main__':unittest.main()
