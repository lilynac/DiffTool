import os
from pathlib import Path
import stat
import sys
from tempfile import TemporaryDirectory
import unittest
from compare_tool.startup import unhide_plugins


@unittest.skipUnless(sys.platform == 'darwin', 'macOS file flags')
class StartupTests(unittest.TestCase):
    def test_hidden_plugins_become_discoverable(self):
        from PySide6.QtCore import QDir
        with TemporaryDirectory() as directory:
            plugin = Path(directory)/'sample.dylib'
            other = Path(directory)/'private.txt'
            plugin.write_bytes(b'probe')
            other.write_text('keep hidden')
            os.chflags(plugin, stat.UF_HIDDEN)
            os.chflags(other, stat.UF_HIDDEN)
            self.assertNotIn(plugin.name, QDir(directory).entryList(QDir.Filter.Files))
            unhide_plugins(directory)
            self.assertIn(plugin.name, QDir(directory).entryList(QDir.Filter.Files))
            self.assertTrue(other.stat().st_flags & stat.UF_HIDDEN)
