"""Render the source SVG into native application icons using Qt."""
from pathlib import Path
import os
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from compare_tool.startup import prepare_qt
prepare_qt()
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QBuffer, QIODevice
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


def main():
    app = QApplication.instance() or QApplication([])
    assets = ROOT / 'assets'
    renderer = QSvgRenderer(str(assets / 'sheetdiff.svg'))
    if not renderer.isValid():
        raise RuntimeError('Invalid source SVG')

    def png(size):
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not image.save(buffer, 'PNG'):
            raise RuntimeError('PNG export failed')
        return bytes(buffer.data())

    sizes = [16, 24, 32, 48, 64, 128, 256]
    chunks = [png(size) for size in sizes]
    offset = 6 + 16 * len(sizes)
    entries = []
    for size, data in zip(sizes, chunks):
        entries.append(struct.pack('<BBBBHHII', size % 256, size % 256,
                                   0, 0, 1, 32, len(data), offset))
        offset += len(data)
    (assets / 'sheetdiff.ico').write_bytes(
        struct.pack('<HHH', 0, 1, len(sizes)) + b''.join(entries) + b''.join(chunks))
    (assets / 'sheetdiff.png').write_bytes(png(512))
    if sys.platform == 'darwin':
        with tempfile.TemporaryDirectory() as directory:
            iconset = Path(directory) / 'sheetdiff.iconset'
            iconset.mkdir()
            for size in [16, 32, 128, 256, 512]:
                for scale in [1, 2]:
                    suffix = '@2x' if scale == 2 else ''
                    (iconset / f'icon_{size}x{size}{suffix}.png').write_bytes(png(size*scale))
            subprocess.run(['iconutil', '-c', 'icns', str(iconset),
                            '-o', str(assets / 'sheetdiff.icns')], check=True)
    print('Application icons generated')


if __name__ == '__main__':
    main()
