#!/usr/bin/env python3

import csv
import datetime
import operator
import re
import funcparserlib
import funcparserlib.lexer
import funcparserlib.parser

csv.register_dialect('ckii', delimiter=';', doublequote=False,
                     quotechar='\0', quoting=csv.QUOTE_NONE, strict=True)

TAB_WIDTH = 4
CHARS_PER_LINE = 120

def files(where, glob):
    yield from sorted(where.glob(glob), key=operator.attrgetter('parts'))

def is_codename(string):
    try:
        return re.match(r'[ekdcb]_', string)
    except TypeError:
        return False

def chars(line):
    n = 0
    for char in line:
        assert char != '\n'
        n += TAB_WIDTH if char == '\t' else 1
    return n

token_specs = [
    ('comment', (r'#.*',)),
    ('whitespace', (r'[ \t]+',)),
    ('newline', (r'\r?\n',)),
    ('op', (r'[={}]',)),
    ('date', (r'\d*\.\d*\.\d*',)),
    ('number', (r'\d+(\.\d+)?',)),
    ('quoted_string', (r'"[^"#\r\n]*"',)),
    ('unquoted_string', (r'[^\s"#={}]+',))
]
useless = ['whitespace']
tokenize = funcparserlib.lexer.make_tokenizer(token_specs)

def unquote(string):
    return string[1:-1]

def make_number(string):
    try:
        return int(string)
    except ValueError:
        return float(string)

def make_date(string):
    # CKII appears to default to 0, not 1, but that's awkward to handle
    # with datetime, and it only comes up for b_embriaco anyway
    year, month, day = ((int(x) if x else 1) for x in string.split('.'))
    return datetime.date(year, month, day)

def some(tok_type):
    return (funcparserlib.parser.some(lambda tok: tok.type == tok_type) >>
            (lambda tok: tok.value))

class Stringifiable(object):
    def val_str(self):
        return self.indent * '\t' + self.val_inline_str(self.indent_col)

    def val_inline_str(self, col):
        return str(self.value)

    @property
    def indent(self):
        return self._indent

    @indent.setter
    def indent(self, value):
        self._indent = value

    @property
    def indent_col(self):
        return self.indent * TAB_WIDTH

    def str(self):
        s = self.indent * '\t'
        if self.pre_comments:
            s += ('\n' + s).join(self.pre_comments) + '\n'
        s += self.val_str()
        if post_comment:
            s += ' ' + self.post_comment
        s += '\n'
        return s

    def inline_str(self, col):
        nl = 0
        sep = '\n' + self.indent * '\t'
        s = ''
        if self.pre_comments:
            if (col > self.indent_col and
                col + chars(self.pre_comments[0]) > CHARS_PER_LINE):
                s += sep
                nl += 1
            s += sep.join(self.pre_comments) + sep
            nl += len(self.pre_comments)
            col = self.indent_col
        vis, (vnl¸ col) = self.val_inline_str(col)
        s += vis
        nl += vnl
        if self.post_comment:
            s += ' ' + self.post_comment + sep
            nl += 1
            col = self.indent_col
        return s, (nl, col)

class Commented(Stringifiable):
    str_to_val = lambda x: x
    
    def __init__(self, args):
        pre_comments, string, post_comment = args
        # self.parent = None
        self.indent = 0
        self.pre_comments = pre_comments
        self.value = str_to_val(string)
        self.post_comment = post_comment

class CK2String(Commented):
    def val_inline_str(self, col):
        return '"{}"'.format(x) if re.search(r'\s', x) else x

class CK2Number(Commented):
    def str_to_val(string):
        try:
            return int(string)
        except ValueError:
            return float(string)
    
class CK2Date(Commented):
    def str_to_val(string):
        # CKII appears to default to 0, not 1, but that's awkward to handle
        # with datetime, and it only comes up for b_embriaco anyway
        year, month, day = ((int(x) if x else 1) for x in string.split('.'))
        return datetime.date(year, month, day)

    def val_inline_str(self, col):
        return '{0.year}.{0.month}.{0.day}'.format(self.value), (0, 0)
    
class CK2Op(Commented):
    pass

class CK2Pair(Stringifiable):
    def __init__(self, args):
        self.items = args
        self.key, self.tis, self.value = args

    @indent.setter
    def indent(self, value):
        self._indent = value
        for item in self.items:
            item.indent = value

    def val_str(self):
        s = self.key.str()
        col = chars(s)
        tis_is = self.key.inline_str(col)
        col_tis = col + chars(tis_is)
        if col_tis > CHARS_PER_LINE:
            tis_s = self.tis.str()
            s += '\n' + tis_s
            col = chars(tis_s)
        else:
            s += tis_is
            col = col_tis
        val_is = self.value.inline_str(col)
        if col + chars(val_is) > CHARS_PER_LINE:
            s += '\n' + self.value.str()
        else:
            s += val_is
        return s

    def val_inline_str(self, col):
        return ' '#.join(x.val_inline_str(col) for x in self.items), (0, 0)

class CK2Obj(Stringifiable):
    def __init__(self, args):
        self.items = args
        self.kel, self.contents, self.ker = args
        self.indent = 0

    @indent.setter
    def indent(self, value):
        self._indent = value
        for item in self.items:
            item.indent = value

    def val_str(self):
        for item in self.contents:
            item.indent = self.indent + 1
        return ' '.join(x.val_str() for x in self.items)

many = funcparserlib.parser.many
maybe = funcparserlib.parser.maybe
fwd = funcparserlib.parser.with_forward_decls
endmark = funcparserlib.parser.skip(funcparserlib.parser.finished)
nl = funcparserlib.parser.skip(many(lambda tok: tok.type == 'newline'))
comment = some('comment') + nl
commented = lambda x: many(comment) + x + maybe(comment) >> tuple

def op(string):
    return commented(funcparserlib.parser.a(
        funcparserlib.lexer.Token('op', string))) >> CK2Op

unquoted_string = commented(some('unquoted_string')) >> CK2String
quoted_string = commented(some('quoted_string') >> unquote) >> CK2String
number = commented(some('number')) >> CK2Number
date = commented(some('date')) >> CK2Date
key = unquoted_string | quoted_string | number | date
value = fwd(lambda: obj | key)
pair = key + op('=') + value >> CK2Pair
obj = fwd(lambda: op('{') + many(pair | value) + op('}') >> CK2Obj)
toplevel = many(pair | value) + many(comment) + endmark

def parse(s):
    return toplevel.parse([t for t in tokenize(s) if t.type not in useless])

def parse_file(path, encoding='cp1252'):
    with path.open(encoding=encoding) as f:
        try:
            tree = parse(f.read())
        except funcparserlib.parser.NoParseError:
            print(path)
            raise
    return tree

def to_string(x, indent=-1, fq_keys=[], force_quote=False):
    if isinstance(x, str):
        # unquoted_string or quoted_string
        return '"{}"'.format(x) if force_quote or re.search(r'\s', x) else x
    if isinstance(x, tuple):
        if len(x) == 4:
            # pair
            return '{}{} {}= {}'.format(
                to_string(x[0], indent),
                to_string(x[1]),
                to_string(x[2], indent),
                to_string(x[3], indent, fq_keys, x[1] in fq_keys))
        if len(x) == 2 and not isinstance(x[1], list):
            # key
            return (to_string(x[0], indent) +
                    to_string(x[1], force_quote=force_quote))
        if indent == -1:
            # top-level many(pair | value)
            return ('\n'.join(to_string(y, 0, fq_keys) for y in x[0]) +
                    to_string(x[1]))
        # obj
        if (not x[0] and len(x[1]) == 3 and not x[2] and
            all(len(y) == 2 and not y[0] and isinstance(y[1], int) for y in x[1])):
            return '{{ {0[1]} {1[1]} {2[1]} }}'.format(*x[1])
        sep = '\n' + '\t' * (indent + 1)
        return '{}{{{}{}}}'.format(
            to_string(x[0], indent),
            (sep + sep.join(to_string(y, indent + 1, fq_keys) for y in x[1]) +
             '\n' + '\t' * indent) if x[1] else '',
            ('\t' + to_string(x[2][:-1], indent + 1) + x[2][-1] +
             '\n' + '\t' * indent if x[2] else ''))
    if isinstance(x, list):
        # comments
        if not x:
            return ''
        if isinstance(x[0], str):
            ws = '\n' + '\t' * indent
            return ws.join(x) + ws
    if isinstance(x, datetime.date):
        return '{0.year}.{0.month}.{0.day}'.format(x)
    return str(x)
