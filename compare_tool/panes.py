"""Selection detail and clickable overview panels."""
from difflib import SequenceMatcher
from html import escape
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextBrowser, QSplitter


def cell_text(value):
    return '∅' if value is None else str(value)


def highlighted_pair(left, right, changed):
    a, b = cell_text(left), cell_text(right)
    if not changed:
        return escape(a), escape(b)
    # Bound character alignment work for exceptionally long cells.
    if len(a) + len(b) > 20000:
        return f'<span style="background:#ffc9c5">{escape(a)}</span>', f'<span style="background:#bce9cc">{escape(b)}</span>'
    aa, bb = [], []
    for tag, i, j, k, l in SequenceMatcher(None, a, b).get_opcodes():
        av, bv = escape(a[i:j]), escape(b[k:l])
        aa.append(av if tag == 'equal' else f'<span style="background:#ffc9c5">{av}</span>')
        bb.append(bv if tag == 'equal' else f'<span style="background:#bce9cc">{bv}</span>')
    return ''.join(aa), ''.join(bb)


class DiffPane(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel('Diffペイン — 行を選択すると上下に表示')
        layout.addWidget(self.title)
        stack = QSplitter(Qt.Orientation.Vertical)
        self.editors = []
        for _ in range(2):
            editor = QTextBrowser()
            editor.setOpenLinks(False)
            editor.setMinimumHeight(50)
            self.editors.append(editor)
            stack.addWidget(editor)
        layout.addWidget(stack)
        self.clear()

    def clear(self):
        self.title.setText('Diffペイン — 行を選択すると上下に表示')
        for editor, label in zip(self.editors, ['左（比較元）', '右（比較先）']):
            editor.setPlainText(label)

    def show_row(self, row, is_text=False):
        from .ui import column_name
        labels = {'equal': '一致', 'changed': '変更', 'added': '追加', 'removed': '削除'}
        self.title.setText(f'Diffペイン — {labels[row.status]}　文字の変更：上が削除、下が追加')
        parts = [[], []]
        for col in range(max(len(row.left), len(row.right))):
            left = row.left[col] if col < len(row.left) else None
            right = row.right[col] if col < len(row.right) else None
            pair = highlighted_pair(left, right, col < len(row.changed) and row.changed[col])
            for side in range(2):
                prefix = '' if is_text else f'<b style="color:#60758c">{column_name(col+1)}:</b> '
                parts[side].append(prefix + pair[side])
        for side, (number, label) in enumerate([(row.left_number, '左'), (row.right_number, '右')]):
            body = '対応する行なし' if number is None else '　│　'.join(parts[side])
            body = body.replace('\r', '␍').replace('\n', '↵<br>')
            self.editors[side].setHtml(f'<div style="font-family:monospace;font-size:13px;white-space:pre-wrap"><b>{label} {number if number is not None else "—"}行</b><br>{body}</div>')


class LocationPane(QWidget):
    """Two overview tracks over the currently displayed row sequence."""
    row_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.first, self.last, self.selected = 0, 0, -1
        self.setMinimumWidth(70)
        self.setMaximumWidth(110)
        self.setToolTip('ロケーション：色の位置をクリック・ドラッグして移動（絞り込み中は表示行が対象）')
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_rows(self, rows):
        self.rows = rows
        self.selected = -1
        self.update()

    def set_viewport(self, first, last, selected):
        self.first, self.last, self.selected = first, last, selected
        self.update()

    def row_at(self, y):
        if not self.rows:
            return -1
        fraction = (y-28)/max(1, self.height()-40)
        return min(len(self.rows)-1, max(0, int(fraction*len(self.rows))))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            row = self.row_at(event.position().y())
            if row >= 0:
                self.row_requested.emit(row)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            row = self.row_at(event.position().y())
            if row >= 0:
                self.row_requested.emit(row)

    def paintEvent(self, event):
        p = QPainter(self)
        w, top, height = self.width(), 28, max(1, self.height()-40)
        p.fillRect(self.rect(), QColor('#f6f8fc'))
        p.setPen(QColor('#526a83'))
        p.drawText(0, 0, w, 24, Qt.AlignmentFlag.AlignCenter, '位置  左  右')
        track_width = (w-26)/2
        for x in [8, 18+track_width]:
            p.fillRect(QRectF(x, top, track_width, height), QColor('#e2e9f2'))
        count = len(self.rows)
        if not count:
            return
        step = height/count
        for i, row in enumerate(self.rows):
            if row.status == 'equal':
                continue
            color = {'changed':'#e8b849', 'added':'#4da879', 'removed':'#da7876'}[row.status]
            for side, number in enumerate([row.left_number, row.right_number]):
                p.fillRect(QRectF(8+side*(track_width+10), top+i*step, track_width, max(2, step)), QColor(color if number is not None else '#aebaca'))
        p.setPen(QPen(QColor('#245fa5'), 2))
        p.drawRect(QRectF(5, top+self.first*step, w-10, max(4, (self.last-self.first+1)*step)))
        if self.selected >= 0:
            p.setPen(QPen(QColor('#162f52'), 2))
            y = int(top+(self.selected+0.5)*step)
            p.drawLine(3, y, w-3, y)
