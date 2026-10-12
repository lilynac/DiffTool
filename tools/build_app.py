"""Build a native app with the SheetDiff icon on the current OS."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
subprocess.run([sys.executable, str(root / 'tools' / 'build_icons.py')], check=True, cwd=root)
icon = 'sheetdiff.icns' if sys.platform == 'darwin' else 'sheetdiff.ico'
command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--windowed',
           '--name', 'SheetDiff', '--icon', str(root / 'assets' / icon),
           '--add-data', f'{root / "assets"}:assets']
if sys.platform == 'darwin':
    command.extend(['--osx-bundle-identifier', 'app.sheetdiff.desktop'])
subprocess.run(command + [str(root / 'main.py')], check=True, cwd=root)
if sys.platform == 'darwin':
    bundle = root / 'dist' / 'SheetDiff.app'
    # Finder metadata on generated resources can prevent ad-hoc signing.
    subprocess.run(['xattr', '-cr', str(bundle)], check=True)
    subprocess.run(['codesign', '--force', '--deep', '--sign', '-', str(bundle)], check=True)
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(bundle)], check=True)
