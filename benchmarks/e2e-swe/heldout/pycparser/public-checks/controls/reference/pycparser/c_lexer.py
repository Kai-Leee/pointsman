"""C tokenizer with a typedef-lookup hook, '#line' and '#pragma' handling."""
import re

KEYWORDS = {word: word.upper() for word in '''
    auto break case char const continue default do double else enum extern float for goto if
    inline int long register restrict return short signed sizeof static struct switch typedef
    union unsigned void volatile while _Bool _Complex _Atomic _Thread_local _Alignof _Pragma
'''.split()}
KEYWORDS.update({word: word.upper() for word in ('_Static_assert', '_Alignas', '_Noreturn')})

OPS = {
    '+': 'PLUS', '-': 'MINUS', '*': 'TIMES', '/': 'DIVIDE', '%': 'MOD', '|': 'OR', '&': 'AND',
    '~': 'NOT', '^': 'XOR', '<<': 'LSHIFT', '>>': 'RSHIFT', '||': 'LOR', '&&': 'LAND', '!': 'LNOT',
    '<': 'LT', '>': 'GT', '<=': 'LE', '>=': 'GE', '==': 'EQ', '!=': 'NE', '=': 'EQUALS',
    '*=': 'TIMESEQUAL', '/=': 'DIVEQUAL', '%=': 'MODEQUAL', '+=': 'PLUSEQUAL', '-=': 'MINUSEQUAL',
    '<<=': 'LSHIFTEQUAL', '>>=': 'RSHIFTEQUAL', '&=': 'ANDEQUAL', '|=': 'OREQUAL', '^=': 'XOREQUAL',
    '++': 'PLUSPLUS', '--': 'MINUSMINUS', '->': 'ARROW', '?': 'CONDOP', '(': 'LPAREN', ')': 'RPAREN',
    '[': 'LBRACKET', ']': 'RBRACKET', '{': 'LBRACE', '}': 'RBRACE', ',': 'COMMA', '.': 'PERIOD',
    ';': 'SEMI', ':': 'COLON', '...': 'ELLIPSIS',
}

_SUFFIX = r'(?:[uU](?:ll|LL|[lL])?|(?:ll|LL|[lL])[uU]?)?'
_RULES = [
    ('HEX_FLOAT_CONST', r'0[xX](?:[0-9a-fA-F]*\.[0-9a-fA-F]+|[0-9a-fA-F]+\.?)[pP][+-]?\d+[fFlL]?'),
    ('FLOAT_CONST', r'(?:\d*\.\d+|\d+\.)(?:[eE][+-]?\d+)?[fFlL]?|\d+[eE][+-]?\d+[fFlL]?'),
    ('INT_CONST_HEX', r'0[xX][0-9a-fA-F]+' + _SUFFIX),
    ('INT_CONST_BIN', r'0[bB][01]+' + _SUFFIX),
    ('INT_CONST_OCT', r'0[0-7]*' + _SUFFIX),
    ('INT_CONST_DEC', r'[1-9]\d*' + _SUFFIX),
    ('WCHAR_CONST', r"L'(?:[^'\\\n]|\\.)+'"),
    ('WSTRING_LITERAL', r'L"(?:[^"\\\n]|\\.)*"'),
    ('CHAR_CONST', r"'(?:[^'\\\n]|\\.)+'"),
    ('STRING_LITERAL', r'"(?:[^"\\\n]|\\.)*"'),
    ('ID', r'[A-Za-z_$][A-Za-z0-9_$]*'),
    ('OP', '|'.join(re.escape(op) for op in sorted(OPS, key=len, reverse=True))),
]
_MASTER = re.compile('|'.join(f'(?P<g{index}>{pattern})' for index, (_, pattern) in enumerate(_RULES)))


class Token:
    def __init__(self, type, value, lineno, column, filename=None):
        self.type, self.value, self.lineno, self.column, self.filename = type, value, lineno, column, filename

    def __repr__(self):
        return f'Token({self.type!r}, {self.value!r}, {self.lineno})'


class CLexer:
    def __init__(self, error_func, on_lbrace_func, on_rbrace_func, type_lookup_func):
        self.error_func = error_func
        self.on_lbrace_func = on_lbrace_func
        self.on_rbrace_func = on_rbrace_func
        self.type_lookup_func = type_lookup_func
        self.filename = '<unknown>'
        self.input('')

    def input(self, text):
        self.text, self.pos, self.lineno, self.line_start = text, 0, 1, 0

    def token(self):
        text = self.text
        while self.pos < len(text):
            char = text[self.pos]
            if char == '\n':
                self.pos += 1
                self.lineno += 1
                self.line_start = self.pos
            elif char in ' \t\r\f\v':
                self.pos += 1
            elif text.startswith('/*', self.pos):
                end = text.find('*/', self.pos + 2)
                end = len(text) if end < 0 else end + 2
                newlines = text.count('\n', self.pos, end)
                if newlines:
                    self.lineno += newlines
                    self.line_start = text.rfind('\n', self.pos, end) + 1
                self.pos = end
            elif text.startswith('//', self.pos):
                end = text.find('\n', self.pos)
                self.pos = len(text) if end < 0 else end
            elif char == '#' and not text[self.line_start:self.pos].strip():
                token = self._directive()
                if token is not None:
                    return token
            else:
                return self._match()
        return None

    def _directive(self):
        start = self.pos
        end = self.text.find('\n', start)
        end = len(self.text) if end < 0 else end
        line = self.text[start + 1:end].strip()
        self.pos = end
        words = line.split(None, 1)
        if not words:
            return None
        if words[0] == 'pragma':
            return Token('PPPRAGMA', words[1].strip() if len(words) > 1 else '', self.lineno,
                         start - self.line_start + 1, self.filename)
        if words[0] == 'line' or words[0].isdigit():
            parts = (words[1] if words[0] == 'line' and len(words) > 1 else line).split()
            if parts and parts[0].isdigit():
                self.lineno = int(parts[0]) - 1  # the newline ending the directive makes it N
                if len(parts) > 1:
                    self.filename = parts[1].strip('"')
        return None  # other directives: input is assumed preprocessed

    def _match(self):
        match = _MASTER.match(self.text, self.pos)
        column = self.pos - self.line_start + 1
        if match is None:
            self.error_func(f'Illegal character {self.text[self.pos]!r}', self.lineno, column)
            self.pos += 1
            return self.token()
        self.pos = match.end()
        kind, value = _RULES[int(match.lastgroup[1:])][0], match.group()
        if kind == 'ID':
            kind = KEYWORDS.get(value) or ('TYPEID' if self.type_lookup_func(value) else 'ID')
        elif kind == 'OP':
            kind = OPS[value]
            if value == '{':
                self.on_lbrace_func()
            elif value == '}':
                self.on_rbrace_func()
        return Token(kind, value, self.lineno, column, self.filename)
