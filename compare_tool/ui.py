import sys
from pathlib import Path
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QThread, Signal
from PySide6.QtGui import QColor, QAction, QKeySequence, QIcon
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QComboBox, QCheckBox, QSplitter,
    QListWidget, QTableView, QMessageBox, QAbstractItemView, QHeaderView)
from .core import Options, compare_files, export_report
from .panes import DiffPane, LocationPane

COLORS = {'changed': '#fff0be', 'added': '#d8f3e3', 'removed': '#ffe0df'}


def column_name(number):
    result = ''
    while number:
        number, rem = divmod(number-1, 26)
        result = chr(65+rem) + result
    return result


class CompareWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, left, right, options, parent):
        super().__init__(parent)
        self.args = left, right, options

    def run(self):
        try:
            self.succeeded.emit(compare_files(*self.args))
        except Exception as exc:
            self.failed.emit(str(exc))


class DiffModel(QAbstractTableModel):
    def __init__(self, section, side, only_differences=False, search='', parent=None):
        super().__init__(parent)
        self.section, self.side = section, side
        self.rows = [r for r in section.rows if (not only_differences or r.status != 'equal')
                     and (not search or search.casefold() in ' '.join(str(v) for v in (*r.left, *r.right)).casefold())]

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self.section.columns

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, c = self.rows[index.row()], index.column()
        values = row.left if self.side == 'left' else row.right
        number = row.left_number if self.side == 'left' else row.right_number
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            value = values[c] if c < len(values) else None
            text = '' if value is None else str(value)
            if self.section.is_text:
                text = text.replace('\r', '␍').replace('\n', '↵')
            return text
        if role == Qt.ItemDataRole.BackgroundRole:
            if number is None:
                return QColor('#edf0f4')
            if c < len(row.changed) and row.changed[c]:
                return QColor(COLORS.get(row.status, '#ffffff'))
        if role == Qt.ItemDataRole.ForegroundRole:
            return QColor('#172337')

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return '内容' if self.section.is_text else column_name(section+1)
        row = self.rows[section]
        number = row.left_number if self.side == 'left' else row.right_number
        return str(number) if number is not None else '—'


class PathInput(QLineEdit):
    def __init__(self):
        super().__init__()
        self._file_path = ''
        self.setAcceptDrops(True)
        self.textEdited.connect(self._path_edited)
        self.editingFinished.connect(lambda: self.setText(self._file_path))
        self.setPlaceholderText('ファイルを選択、またはここへドロップ')

    @property
    def file_path(self):
        return self._file_path

    def setText(self, path):
        self._file_path = str(Path(path).expanduser().absolute()) if path else ''
        super().setText(Path(self._file_path).name if self._file_path else '')
        self.setToolTip(self._file_path)
        self.setCursorPosition(0)

    def _path_edited(self, text):
        self._file_path = str(Path(text).expanduser().absolute()) if text else ''
        self.setToolTip(self._file_path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and event.mimeData().urls()[0].isLocalFile():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.setText(event.mimeData().urls()[0].toLocalFile())
        event.acceptProposedAction()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.sections = []
        self.source_paths = set()
        self.worker = None
        self._selecting = False
        self.setWindowTitle('SheetDiff — Excel・CSV・テキスト比較')
        self.resize(1380, 860)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(22, 18, 22, 18)
        title = QLabel('SheetDiff')
        title.setStyleSheet('font-size: 26px; font-weight: 700; color: #173c6c;')
        layout.addWidget(title)
        layout.addWidget(QLabel('Excel・CSV・テキストを左右に並べて比較'))
        paths = QHBoxLayout()
        self.paths = []
        for label in ['左のファイル（比較元）', '右のファイル（比較先）']:
            box = QVBoxLayout()
            box.addWidget(QLabel(label))
            line = QHBoxLayout()
            edit, button = PathInput(), QPushButton('参照…')
            self.paths.append(edit)
            button.clicked.connect(lambda checked=False, target=edit: self.browse(target))
            line.addWidget(edit)
            line.addWidget(button)
            box.addLayout(line)
            paths.addLayout(box)
        layout.addLayout(paths)
        options = QHBoxLayout()
        self.space, self.case = QCheckBox('空白を無視'), QCheckBox('大文字・小文字を無視')
        self.align_excel = QCheckBox('Excelの行挿入・削除を検出')
        self.align_excel.setChecked(True)
        self.align_excel.setToolTip('行の内容から対応づけます。オフにすると同じセル位置で比較します。')
        self.cached = QCheckBox('Excelの保存済み計算結果を比較')
        self.cached.setToolTip('オフ：数式を比較。オン：Excelが最後に保存した計算結果を比較。再計算はしません。未保存の結果は空欄になります。')
        self.encoding = QComboBox()
        self.encoding.addItems(['auto', 'utf-8-sig', 'cp932', 'utf-16', 'euc_jp'])
        for widget in [self.space, self.case, self.cached, QLabel('文字コード'), self.encoding]:
            options.addWidget(widget)
        options.addStretch()
        swap = QPushButton('左右を入替')
        swap.clicked.connect(self.swap)
        options.addWidget(swap)
        self.compare_button = QPushButton('比較する')
        self.compare_button.setObjectName('primary')
        self.compare_button.clicked.connect(self.compare)
        options.addWidget(self.compare_button)
        layout.addLayout(options)
        toolbar = QHBoxLayout()
        self.only_diff = QCheckBox('差分だけ表示')
        self.only_diff.toggled.connect(self.show_section)
        toolbar.addWidget(self.only_diff)
        toolbar.addWidget(self.align_excel)
        self.search = QLineEdit()
        self.search.setPlaceholderText('表示行を検索（左右の値から絞り込み）')
        self.search.textChanged.connect(self.show_section)
        toolbar.addWidget(self.search)
        for label, delta, shortcut in [('↑ 前の差分', -1, 'Shift+F7'), ('↓ 次の差分', 1, 'F7')]:
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, d=delta: self.navigate(d))
            toolbar.addWidget(button)
            action = QAction(self)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(lambda checked=False, d=delta: self.navigate(d))
            self.addAction(action)
        export = QPushButton('差分CSVを保存')
        export.clicked.connect(self.export)
        toolbar.addWidget(export)
        layout.addLayout(toolbar)
        self.splitter = QSplitter()
        self.sheets = QListWidget()
        self.sheets.setMinimumWidth(180)
        self.sheets.currentRowChanged.connect(self.show_section)
        self.splitter.addWidget(self.sheets)
        self.tables = []
        for _ in range(2):
            table = QTableView()
            table.setAlternatingRowColors(False)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setWordWrap(False)
            table.verticalHeader().setDefaultSectionSize(28)
            table.horizontalHeader().setDefaultSectionSize(145)
            table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            self.tables.append(table)
            self.splitter.addWidget(table)
        self.location = LocationPane()
        self.location.row_requested.connect(self.select_row)
        self.splitter.insertWidget(1, self.location)
        self.splitter.setSizes([180, 80, 530, 530])
        for source, target in [self.tables, self.tables[::-1]]:
            source.verticalScrollBar().valueChanged.connect(target.verticalScrollBar().setValue)
            source.horizontalScrollBar().valueChanged.connect(target.horizontalScrollBar().setValue)
            source.horizontalHeader().sectionResized.connect(
                lambda c, old, new, t=target: t.setColumnWidth(c, new) if t.columnWidth(c) != new else None)
        self.tables[0].verticalScrollBar().valueChanged.connect(self.update_location)
        self.tables[0].verticalScrollBar().rangeChanged.connect(self.update_location)
        self.diff_pane = DiffPane()
        self.vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        self.vertical_splitter.addWidget(self.splitter)
        self.vertical_splitter.addWidget(self.diff_pane)
        self.vertical_splitter.setSizes([480, 180])
        layout.addWidget(self.vertical_splitter, 1)
        self.summary = QLabel('2つのファイルを選択して「比較する」を押してください。')
        layout.addWidget(self.summary)
        layout.addWidget(QLabel('黄色：変更  /  緑：右に追加  /  赤：左から削除  /  灰：対応する行なし　　Excelは同名シートで比較・行の挿入／削除を検出可能'))
        copy = QAction(self)
        copy.setShortcut(QKeySequence.StandardKey.Copy)
        copy.triggered.connect(self.copy_row)
        self.addAction(copy)
        self.setStyleSheet('''
            QMainWindow, QWidget { background: #f6f8fc; color: #24344a; }
            QLineEdit, QComboBox, QListWidget, QTableView { background: white; border: 1px solid #d5dfea; border-radius: 4px; }
            QLineEdit, QComboBox { padding: 7px; }
            QPushButton { padding: 8px 13px; background: white; border: 1px solid #c6d2e1; border-radius: 5px; }
            QPushButton:hover { background: #e7eef8; }
            QPushButton#primary { background: #245fa5; color: white; font-weight: bold; }
            QPushButton:disabled { color: #98a4b2; }
            QHeaderView::section { background: #eaf0f8; padding: 5px; border: 0; border-right: 1px solid #d5dfea; }
            QListWidget::item { padding: 10px; }
            QListWidget::item:selected { background: #d9e8fb; color: #153966; }
            QTableView { selection-background-color: #b9d5f8; selection-color: #172337; }
        ''')

    def browse(self, edit):
        name, _ = QFileDialog.getOpenFileName(self, '比較するファイル', edit.file_path,
            '対応ファイル (*.xlsx *.xlsm *.csv *.tsv *.txt *.log *.md);;すべてのファイル (*)')
        if name:
            edit.setText(name)

    def swap(self):
        a, b = [p.file_path for p in self.paths]
        self.paths[0].setText(b)
        self.paths[1].setText(a)

    def compare(self):
        if self.worker and self.worker.isRunning():
            return
        paths = [p.file_path for p in self.paths]
        if not all(Path(p).is_file() for p in paths):
            QMessageBox.warning(self, 'ファイルを確認', '左右に存在するファイルを指定してください。')
            return
        self.source_paths = {Path(p).resolve() for p in paths}
        self.sections = []
        self.sheets.clear()
        self.diff_pane.clear()
        self.location.set_rows([])
        for table in self.tables:
            old = table.model()
            table.setModel(None)
            if old:
                old.deleteLater()
        self.compare_button.setEnabled(False)
        self.summary.setText('比較中…')
        self.worker = CompareWorker(*paths, Options(self.space.isChecked(), self.case.isChecked(),
            self.cached.isChecked(), self.encoding.currentText(), self.align_excel.isChecked()), self)
        self.worker.succeeded.connect(self.loaded)
        self.worker.failed.connect(self.failed)
        self.worker.finished.connect(lambda: self.compare_button.setEnabled(True))
        self.worker.start()

    def loaded(self, sections):
        self.sections = sections
        for section in sections:
            label = f'{section.name}  ·  {section.differences}行'
            if section.presence != '両側':
                label += f'（{section.presence}）'
            self.sheets.addItem(label)
        self.sheets.setCurrentRow(0)
        self.show_section()

    def failed(self, message):
        self.summary.setText('比較できませんでした。')
        QMessageBox.warning(self, '比較エラー', message)

    def show_section(self, *args):
        index = self.sheets.currentRow()
        if not 0 <= index < len(self.sections):
            return
        section = self.sections[index]
        self._selecting = True
        self.diff_pane.clear()
        for table, side in zip(self.tables, ['left', 'right']):
            old = table.model()
            model = DiffModel(section, side, self.only_diff.isChecked(), self.search.text(), table)
            table.setModel(model)
            table.selectionModel().currentRowChanged.connect(self.row_selected)
            if old:
                old.deleteLater()
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            if section.is_text:
                table.setColumnWidth(0, max(700, table.viewport().width()-5))
        self._selecting = False
        self.location.set_rows(self.tables[0].model().rows)
        self.update_location()
        self.summary.setText(f'{section.name}  |  {section.presence}  |  差分 {section.differences}行  |  表示 {self.tables[0].model().rowCount()}行')

    def navigate(self, delta):
        table = self.tables[0]
        model = table.model()
        if model is None:
            return
        indices = [i for i, row in enumerate(model.rows) if row.status != 'equal']
        if not indices:
            return
        current = table.currentIndex().row()
        candidates = [i for i in indices if i > current] if delta > 0 else [i for i in indices if i < current]
        row = (candidates[0] if delta > 0 else candidates[-1]) if candidates else (indices[0] if delta > 0 else indices[-1])
        self.select_row(row)

    def row_selected(self, current, previous):
        if not self._selecting and current.isValid():
            self.select_row(current.row(), center=False)

    def select_row(self, row, center=True):
        model = self.tables[0].model()
        if self._selecting or model is None or not 0 <= row < model.rowCount():
            return
        self._selecting = True
        try:
            for view in self.tables:
                view.selectRow(row)
                if center:
                    view.scrollTo(view.model().index(row, 0), QAbstractItemView.ScrollHint.PositionAtCenter)
            self.diff_pane.show_row(model.rows[row], model.section.is_text)
            self.update_location()
        finally:
            self._selecting = False

    def update_location(self, *args):
        table = self.tables[0]
        model = table.model()
        if model is None or not model.rowCount():
            self.location.set_viewport(0, 0, -1)
            return
        first = max(0, table.rowAt(0))
        last = table.rowAt(table.viewport().height()-1)
        if last < 0:
            last = model.rowCount()-1
        self.location.set_viewport(first, last, table.currentIndex().row())

    def copy_row(self):
        for table in self.tables:
            if table.hasFocus() and table.currentIndex().isValid():
                model = table.model()
                r = model.rows[table.currentIndex().row()]
                values = r.left if model.side == 'left' else r.right
                QApplication.clipboard().setText('\t'.join('' if v is None else str(v) for v in values))

    def export(self):
        if not self.sections:
            return
        path, _ = QFileDialog.getSaveFileName(self, '全シートの差分を保存', 'differences.csv', 'CSV (*.csv)')
        if path:
            try:
                if Path(path).resolve() in self.source_paths:
                    raise ValueError('比較元のファイルと別の保存先を指定してください。')
                export_report(path, self.sections)
                self.statusBar().showMessage(f'保存しました：{path}', 8000)
            except Exception as exc:
                QMessageBox.warning(self, '保存エラー', str(exc))

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, '比較中', '比較が完了してから閉じてください。')
            event.ignore()
        else:
            event.accept()


def main():
    from .startup import prepare_qt
    prepare_qt()
    app = QApplication(sys.argv)
    app.setApplicationName('SheetDiff')
    app.setOrganizationName('SheetDiff')
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parents[1] / 'assets' / 'sheetdiff.png')))
    window = MainWindow()
    if len(sys.argv) >= 3:
        for edit, path in zip(window.paths, sys.argv[1:3]):
            edit.setText(path)
        window.compare()
    window.show()
    sys.exit(app.exec())
