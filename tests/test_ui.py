import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from compare_tool.ui import MainWindow, DiffModel
from compare_tool.core import Section, compare_rows


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from compare_tool.startup import prepare_qt
        prepare_qt()
        cls.app = QApplication.instance() or QApplication([])

    def test_worker_navigation_and_filters(self):
        with TemporaryDirectory() as directory:
            a, b = Path(directory)/'a.txt', Path(directory)/'b.txt'
            a.write_text('same\nbefore\n', encoding='utf-8')
            b.write_text('same\nafter\nextra\n', encoding='utf-8')
            window = MainWindow()
            window.paths[0].setText(str(a))
            window.paths[1].setText(str(b))
            window.compare()
            loop = QEventLoop()
            window.worker.finished.connect(loop.quit)
            QTimer.singleShot(10000, loop.quit)
            loop.exec()
            window.worker.wait()
            self.app.processEvents()
            try:
                self.assertEqual(len(window.sections), 1)
                self.assertEqual(window.tables[0].model().rowCount(), 3)
                window.navigate(1)
                self.assertEqual(window.tables[0].currentIndex().row(), 1)
                window.only_diff.setChecked(True)
                self.assertEqual(window.tables[0].model().rowCount(), 2)
                window.search.setText('extra')
                self.assertEqual(window.tables[1].model().rowCount(), 1)
                self.assertEqual(window.source_paths, {a.resolve(), b.resolve()})
            finally:
                window.close()

    def test_detail_and_location_selection(self):
        from PySide6.QtCore import Qt, QPoint
        from PySide6.QtTest import QTest
        left = [(f'row {i}', '<tag>') for i in range(200)]
        right = list(left)
        right[100] = ('CHANGED', '<script>')
        right.append(('new', 'value'))
        window = MainWindow()
        window.show()
        window.loaded([Section('data', compare_rows(left, right, align=False), 2)])
        self.app.processEvents()
        try:
            window.tables[1].selectRow(100)
            self.assertEqual(window.tables[0].currentIndex().row(), 100)
            self.assertIn('row 100', window.diff_pane.editors[0].toPlainText())
            self.assertIn('<script>', window.diff_pane.editors[1].toPlainText())
            self.assertEqual(window.location.selected, 100)
            self.assertEqual(window.location.row_at(0), 0)
            self.assertEqual(window.location.row_at(window.location.height()), 200)
            QTest.mouseClick(window.location, Qt.MouseButton.LeftButton,
                             pos=QPoint(30, window.location.height()-10))
            self.assertEqual(window.tables[0].currentIndex().row(), 200)
            self.assertIn('対応する行なし', window.diff_pane.editors[0].toPlainText())
            window.only_diff.setChecked(True)
            self.assertEqual(len(window.location.rows), 2)
            window.select_row(0)
            self.assertIn('CHANGED', window.diff_pane.editors[1].toPlainText())
            window.search.setText('does not exist')
            self.assertEqual(len(window.location.rows), 0)
            self.assertEqual(window.location.row_at(10), -1)
            self.assertNotIn('CHANGED', window.diff_pane.editors[1].toPlainText())
        finally:
            window.close()

    def test_sheet_named_text_still_has_excel_headers(self):
        from PySide6.QtCore import Qt
        model = DiffModel(Section('テキスト', compare_rows([('a',)], [('b',)]), 1), 'left')
        self.assertEqual(model.headerData(0, Qt.Orientation.Horizontal), 'A')


if __name__ == '__main__':
    unittest.main()
