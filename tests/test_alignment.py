from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from openpyxl import Workbook
from compare_tool.core import Options, compare_files, compare_rows


class ExcelAlignmentTests(unittest.TestCase):
    def compare(self, left, right):
        return compare_rows(left, right, excel=True, sheet_name='売上')

    def test_two_deleted_rows_with_shifted_formulas(self):
        left = [(f'P{i:03}', i, f'=B{i+1}*2') for i in range(1, 501)]
        # Include header to make physical row references representative.
        left.insert(0, ('商品ID', '数量', '金額'))
        right = left[:8] + left[10:]
        right = [row if i < 8 else (row[0], row[1], f'=B{i+1}*2') for i, row in enumerate(right)]
        rows = self.compare(left, right)
        self.assertEqual([r.left_number for r in rows if r.status == 'removed'], [9, 10])
        self.assertEqual(sum(r.status == 'changed' for r in rows), 0)
        self.assertEqual((rows[10].left_number, rows[10].right_number), (11, 9))
        self.assertEqual(rows[-1].status, 'equal')

    def test_insert_delete_and_edit_in_same_block(self):
        left = [('ID','名前','数'), ('A','甲',1), ('B','乙',2), ('C','丙',3), ('D','丁',4)]
        right = [('ID','名前','数'), ('A','甲',9), ('X','新規',7), ('C','丙',8), ('D','丁',4)]
        rows = self.compare(left, right)
        for identity in ['A', 'C', 'D']:
            pair = next(r for r in rows if r.left and r.left[0] == identity)
            self.assertEqual(pair.right[0], identity)
        self.assertEqual(next(r for r in rows if r.left and r.left[0]=='C').changed, (False,False,True))

    def test_deleted_before_changed_row(self):
        left = [('A',1),('B',2),('C',3),('D',4)]
        right = [('A',1),('C',30),('D',4)]
        rows = self.compare(left,right)
        self.assertEqual([r.status for r in rows], ['equal','removed','changed','equal'])
        self.assertEqual(rows[2].right_number, 2)

    def test_insert_before_changed_row(self):
        left = [('A',1),('B',2),('C',3)]
        right = [('A',1),('X',99),('B',20),('C',3)]
        rows = self.compare(left,right)
        self.assertEqual([r.status for r in rows], ['equal','added','changed','equal'])

    def test_duplicate_and_blank_rows(self):
        left = [('a',), (), ('repeat',), ('repeat',), ('end',)]
        right = [('a',), (), ('repeat',), ('end',)]
        rows = self.compare(left,right)
        self.assertEqual(sum(r.status=='removed' for r in rows),1)
        self.assertFalse(any(r.status=='changed' for r in rows))
        self.assertEqual(rows[-1].left_number,5)
        self.assertEqual(rows[-1].right_number,4)

    def test_formula_changes_and_strings_not_hidden(self):
        left = [('a',1,'=B1*2'), ('deleted',2,'=B2*2'), ('c',3,'=B3*2'), ('d',4,'="B4"'), ('e',5,"='Other'!B5")]
        right = [('a',1,'=B1*2'), ('c',3,'=B2*3'), ('d',4,'="B3"'), ('e',5,"='Other'!B4")]
        rows = self.compare(left,right)
        self.assertEqual([r.status for r in rows], ['equal','removed','changed','changed','changed'])

    def test_absolute_and_same_sheet_cell_references(self):
        left = [('a',1), ('gone',2), ('c',3,"='売上'!$B$3+B3")]
        right = [('a',1), ('c',3,"='売上'!$B$2+B2")]
        self.assertEqual(self.compare(left,right)[-1].status,'equal')

    def test_same_row_range_formulas_follow_rows(self):
        left = [('a',1), ('gone',2), ('c',3,'=SUM(B3:C3)')]
        right = [('a',1), ('c',3,'=SUM(B2:C2)')]
        self.assertEqual(self.compare(left,right)[-1].status,'equal')

    def test_range_losing_a_referenced_row_still_differs(self):
        left = [('a',1), ('gone',2), ('c',3,'=SUM(B1:B3)')]
        right = [('a',1), ('c',3,'=SUM(B1:B2)')]
        self.assertEqual(self.compare(left,right)[-1].status,'changed')

    def test_large_changed_block_uses_unique_column_anchors(self):
        left = [(f'P{i}',i) for i in range(600)]
        right = [(f'P{i}',i+1) for i in range(600) if i not in [7,8]]
        rows = self.compare(left,right)
        self.assertEqual(sum(r.status=='removed' for r in rows),2)
        for row in rows:
            if row.right:
                self.assertEqual(row.left[0],row.right[0])

    def test_real_files_and_position_mode(self):
        with TemporaryDirectory() as d:
            a,b=Path(d)/'a.xlsx',Path(d)/'b.xlsx'
            for path, data in [(a,[('A',1),('B',2),('C',3)]),(b,[('A',1),('C',3)])]:
                wb=Workbook()
                for row in data: wb.active.append(row)
                wb.save(path)
                wb.close()
            auto=compare_files(a,b)[0]
            fixed=compare_files(a,b,Options(align_excel=False))[0]
            self.assertEqual([r.status for r in auto.rows],['equal','removed','equal'])
            self.assertEqual([r.status for r in fixed.rows],['equal','changed','removed'])
