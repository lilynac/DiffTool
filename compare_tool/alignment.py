"""Order-preserving row alignment, with bounded matching of edited blocks."""
from collections import Counter
from difflib import SequenceMatcher
from itertools import zip_longest
import re


def is_formula(value):
    return isinstance(value, str) and value.startswith('=')


def alignment_keys(rows, normalize):
    # Formula row numbers change when Excel moves rows. Values identify anchors;
    # formulas are still compared in full after correspondence is established.
    return [tuple(('formula',) if is_formula(v) else normalize(v) for v in row)
            for row in rows]


def align_rows(a, b):
    counts_a = Counter((c, value) for row in a for c, value in enumerate(row) if value not in [('formula',), ('NoneType', None), ('str', '')])
    counts_b = Counter((c, value) for row in b for c, value in enumerate(row) if value not in [('formula',), ('NoneType', None), ('str', '')])

    def similarity(left, right):
        matches = 0
        usable = 0
        identity = False
        for c, (x, y) in enumerate(zip_longest(left, right)):
            if x == y and x in [('formula',), ('NoneType', None), ('str', '')]:
                continue
            usable += 1
            if x == y:
                matches += 1
                if counts_a[c, x] == counts_b[c, x] == 1:
                    identity = True
        return max(matches / max(usable, 1), 0.9 if identity else 0)

    def edited(i, j, k, l):
        n, m = j-i, l-k
        if not n or not m:
            return list(zip_longest(range(i, j), range(k, l)))
        if n*m > 250_000:
            # Find a common unique-column anchor before falling back to position.
            best = []
            for col in range(min(max(map(len, a[i:j]), default=0), max(map(len, b[k:l]), default=0))):
                aa = [row[col] if col < len(row) else None for row in a[i:j]]
                bb = [row[col] if col < len(row) else None for row in b[k:l]]
                anchors = [(i+x, k+y) for tag, p, q, r, s in SequenceMatcher(None, aa, bb, autojunk=False).get_opcodes()
                           if tag == 'equal' for x, y in zip(range(p,q), range(r,s))
                           if counts_a[col, aa[x]] == counts_b[col, aa[x]] == 1]
                if len(anchors) > len(best):
                    best = anchors
            if best:
                result, pi, pk = [], i, k
                for ai, bi in best:
                    result.extend(edited(pi, ai, pk, bi))
                    result.append((ai, bi))
                    pi, pk = ai+1, bi+1
                result.extend(edited(pi, j, pk, l))
                return result
            return list(zip_longest(range(i, j), range(k, l)))
        trace = [bytearray(m+1) for _ in range(n+1)]
        previous = list(range(m+1))
        for x in range(1, n+1):
            current = [float(x)] + [0.0]*m
            for y in range(1, m+1):
                # Pair edits, but prefer gaps when another row has stronger evidence.
                substitution = previous[y-1] + 1.8 - 1.6*similarity(a[i+x-1], b[k+y-1])
                removal, addition = previous[y]+1, current[y-1]+1
                best = min(substitution, removal, addition)
                current[y] = best
                trace[x][y] = 0 if best == substitution else 1 if best == removal else 2
            previous = current
        result, x, y = [], n, m
        while x or y:
            step = trace[x][y] if x and y else 1 if x else 2
            if step == 0:
                x, y = x-1, y-1
                result.append((i+x, k+y))
            elif step == 1:
                x -= 1
                result.append((i+x, None))
            else:
                y -= 1
                result.append((None, k+y))
        return result[::-1]

    result = []
    for tag, i, j, k, l in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == 'replace':
            result.extend(edited(i, j, k, l))
        else:
            result.extend(zip_longest(range(i, j), range(k, l)))
    return result


_CELL = re.compile(r'(\$?[A-Za-z]{1,3})(\$?)([1-9][0-9]*)\Z')


def mapped_formula(value, row_map, sheet_name):
    """Map same-sheet A1 references back to left rows; preserve string literals.

    Contiguous same-sheet ranges map only when every referenced row survives
    with the same offset. Other-sheet/structured references remain literal.
    """
    if not is_formula(value):
        return value
    from openpyxl.formula import Tokenizer
    from openpyxl.formula.tokenizer import TokenizerError
    try:
        tokens = Tokenizer(value).items
    except (TokenizerError, IndexError, ValueError):
        return value
    parts = []
    for token in tokens:
        text = token.value
        if token.type == 'OPERAND' and token.subtype == 'RANGE':
            prefix, sep, ref = text.rpartition('!')
            if not sep:
                ref = text
            local = not sep or prefix.strip("'").replace("''", "'") == sheet_name
            cells = ref.split(':')
            matches = [_CELL.fullmatch(cell) for cell in cells] if local and len(cells) <= 2 else []
            if matches and all(matches):
                numbers = [int(match.group(3)) for match in matches]
                originals = [row_map.get(number) for number in numbers]
                valid = all(original is not None for original in originals)
                if valid and len(numbers) == 2:
                    start, end = sorted(numbers)
                    offset = originals[0]-numbers[0]
                    valid = end-start <= 10000 and all(row_map.get(r) == r+offset for r in range(start, end+1))
                if valid:
                    mapped = ':'.join(match.group(1)+match.group(2)+str(original)
                                      for match, original in zip(matches, originals))
                    text = (prefix+'!' if sep else '') + mapped
        parts.append(text)
    return '=' + ''.join(parts)
