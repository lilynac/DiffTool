"""Check native platform plugins before Qt can abort the process."""
import os
from pathlib import Path
import stat
import sys


def unhide_plugins(directory):
    """Qt excludes macOS UF_HIDDEN plugin files from its discovery scan."""
    if sys.platform != 'darwin':
        return
    for path in Path(directory).rglob('*.dylib'):
        info = path.stat()
        if info.st_flags & stat.UF_HIDDEN:
            os.chflags(path, info.st_flags & ~stat.UF_HIDDEN)


def prepare_qt():
    if sys.platform != 'darwin':
        return
    from PySide6.QtCore import QLibraryInfo, QPluginLoader
    plugins = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))
    unhide_plugins(plugins)
    platform = os.environ.get('QT_QPA_PLATFORM', 'cocoa').split(':', 1)[0]
    if platform != 'cocoa':
        return
    file = plugins / 'platforms' / 'libqcocoa.dylib'
    loader = QPluginLoader(str(file))
    if not file.is_file() or not loader.metaData():
        raise RuntimeError('QtのMac用プラグインを読み込めません。仮想環境で python -m pip install --force-reinstall -r requirements.txt を実行してください。')
