"""Hand-written recursive-descent C parser producing c_ast trees.

ponytail: covers the C99/C11 subset the public checks exercise; unsupported forms raise
ParseError. Known ceilings: no string-literal concatenation, no `_Atomic(T *)`, function
parameters are not entered into the typedef scope.
"""
import re

from . import c_ast
from .c_lexer import CLexer, Token

STORAGE = {'typedef', 'extern', 'static', 'auto', 'register', '_Thread_local'}
QUALS = {'const', 'volatile', 'restrict', '_Atomic'}
FUNCSPEC = {'inline', '_Noreturn'}
BASIC = {'void', 'char', 'short', 'int', 'long', 'float', 'double', 'signed', 'unsigned', '_Bool', '_Complex'}
DECL_WORDS = STORAGE | QUALS | FUNCSPEC | BASIC | {'struct', 'union', 'enum', '_Alignas'}
BINARY = {'||': 1, '&&': 2, '|': 3, '^': 4, '&': 5, '==': 6, '!=': 6, '<': 7, '>': 7, '<=': 7, '>=': 7,
          '<<': 8, '>>': 8, '+': 9, '-': 9, '*': 10, '/': 10, '%': 10}
ASSIGN = {'=', '+=', '-=', '*=', '/=', '%=', '<<=', '>>=', '&=', '|=', '^='}
NAMES = ('ID', 'TYPEID')


class Coord:
    __slots__ = ('file', 'line', 'column', '__weakref__')

    def __init__(self, file, line, column=None):
        self.file, self.line, self.column = file, line, column

    def __str__(self):
        text = f'{self.file}:{self.line}'
        if self.column is not None:
            text += f':{self.column}'
        return text

    __repr__ = __str__


class ParseError(Exception):
    pass


def _constant_type(kind, text):
    if 'FLOAT' in kind:
        last = text[-1].lower()
        return 'float' if last == 'f' else 'long double' if last == 'l' else 'double'
    suffix = re.search('[uUlL]*$', text).group().lower()
    return ' '.join((['unsigned'] if 'u' in suffix else []) + ['long'] * suffix.count('l') + ['int'])


class CParser:
    def parse(self, text, filename='<unknown>'):
        """Parse C source text into a c_ast.FileAST; raises ParseError on syntax errors."""
        return self._parse(text, filename)

    def _parse(self, text, filename):
        self.scopes = [{}]
        self.lexer = CLexer(self._lex_error, self._push_scope, self._pop_scope, self._is_type)
        self.lexer.filename = filename
        self.lexer.input(text)
        self.buf, self.last = [], None
        ext = []
        while self.peek().type != '$end':
            ext.extend(self.external())
        return c_ast.FileAST(ext)

    # ------------------------------------------------------------------ tokens and scopes

    def peek(self, k=0):
        while len(self.buf) <= k:
            token = self.lexer.token()
            if token is None:
                token = Token('$end', '', self.lexer.lineno, None, self.lexer.filename)
            self.buf.append(token)
        return self.buf[k]

    def next(self):
        token = self.peek()
        if token.type == '$end':
            self.error('unexpected end of input')
        self.last = self.buf.pop(0)
        return token

    def at(self, value, k=0):
        token = self.peek(k)
        return token.value == value and token.type not in NAMES and token.type != '$end'

    def accept(self, value):
        return self.next() if self.at(value) else None

    def expect(self, value):
        if not self.at(value):
            self.error(f'expected {value!r}')
        return self.next()

    def error(self, message, token=None):
        token = token or self.peek()
        where = repr(token.value) if token.type != '$end' else 'end of input'
        raise ParseError(f'{token.filename}:{token.lineno}: {message} before {where}')

    def _lex_error(self, message, line, column):
        raise ParseError(f'{self.lexer.filename}:{line}: {message}')

    def _coord(self, token):
        return Coord(token.filename, token.lineno)

    def _push_scope(self):
        self.scopes.append({})

    def _pop_scope(self):
        if len(self.scopes) > 1:
            self.scopes.pop()

    def _is_type(self, name):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return False

    def _declare(self, name, is_type):
        self.scopes[-1][name] = is_type

    def starts_type(self, token):
        return token.type == 'TYPEID' or (token.type not in NAMES and token.value in DECL_WORDS)

    # ------------------------------------------------------------------ declarations

    def external(self):
        if self.at(';'):  # empty external declaration
            self.next()
            return []
        if self.peek().type == 'PPPRAGMA' or self.at('_Pragma'):
            return [self.pragma()]
        if self.at('_Static_assert'):
            return [self.static_assert()]
        return self.declaration(external=True)

    def specifiers(self):
        spec = {'quals': [], 'storage': [], 'funcspec': [], 'align': [], 'names': [], 'node': None,
                'typeid': False, 'coord': self._coord(self.peek())}
        while True:
            token = self.peek()
            value = token.value
            if token.type == 'TYPEID' and not spec['names'] and spec['node'] is None:
                spec['names'].append(self.next().value)
                spec['typeid'] = True
            elif token.type in NAMES or token.type == '$end':
                break
            elif value in STORAGE:
                spec['storage'].append(self.next().value)
            elif value == '_Atomic' and self.at('(', 1):
                self.next()
                self.next()
                inner = self.specifiers()
                self.expect(')')
                spec['names'] += inner['names']
                spec['node'] = spec['node'] or inner['node']
                spec['quals'] += inner['quals'] + ['_Atomic']
            elif value in QUALS:
                self.next()
                spec['quals'].append(value)
            elif value in FUNCSPEC:
                spec['funcspec'].append(self.next().value)
            elif value in BASIC:
                spec['names'].append(self.next().value)
            elif value in ('struct', 'union'):
                spec['node'] = self.struct_or_union()
            elif value == 'enum':
                spec['node'] = self.enum()
            elif value == '_Alignas':
                start = self.next()
                self.expect('(')
                alignment = self.typename() if self.starts_type(self.peek()) else self.conditional()
                self.expect(')')
                spec['align'].append(c_ast.Alignas(alignment, coord=self._coord(start)))
            else:
                break
        self._check_specifiers(spec)
        return spec

    def _check_specifiers(self, spec):
        names = spec['names']
        if not names and spec['node'] is None:
            self.error('missing type specifier')
        count = {word: names.count(word) for word in names}
        base = [word for word in names if word in ('void', 'char', 'int', 'float', 'double', '_Bool')]
        sized = [word for word in names if word in ('short', 'long', 'signed', 'unsigned')]
        bad = (any(n > 1 for word, n in count.items() if word != 'long') or count.get('long', 0) > 2
               or len(base) > 1 or ('short' in count and 'long' in count) or ('signed' in count and 'unsigned' in count)
               or (base and base[0] in ('void', 'float', '_Bool') and sized)
               or (base == ['double'] and (set(sized) - {'long'} or count.get('long', 0) > 1))
               or (base == ['char'] and ('short' in count or 'long' in count))
               or ((spec['typeid'] or spec['node'] is not None) and len(names) > (1 if spec['typeid'] else 0)))
        if bad:
            self.error('invalid combination of type specifiers ' + ' '.join(names))

    def declaration(self, external=False):
        spec = self.specifiers()
        if self.accept(';'):
            return [self._bare_decl(spec)]
        out = []
        while True:
            name, typ = self.declarator(spec)
            if (external and not out and isinstance(typ, c_ast.FuncDecl)
                    and (self.at('{') or self.starts_type(self.peek()))):
                return [self.funcdef(spec, name, typ)]
            out.append(self.init_declarator(spec, name, typ))
            if not self.accept(','):
                break
        self.expect(';')
        return out

    def _bare_decl(self, spec):
        base = spec['node'] if spec['node'] is not None else c_ast.IdentifierType(list(spec['names']))
        return c_ast.Decl(None, list(spec['quals']), list(spec['align']), list(spec['storage']),
                          list(spec['funcspec']), base, None, None, coord=spec['coord'])

    def init_declarator(self, spec, name, typ):
        coord = self._coord(name) if name else spec['coord']
        if 'typedef' in spec['storage']:
            self._declare(name.value, True)
            return c_ast.Typedef(name.value, list(spec['quals']), list(spec['storage']), typ, coord=coord)
        if name:
            self._declare(name.value, False)
        init = self.initializer() if self.accept('=') else None
        return c_ast.Decl(name and name.value, list(spec['quals']), list(spec['align']),
                          list(spec['storage']), list(spec['funcspec']), typ, init, None, coord=coord)

    def funcdef(self, spec, name, typ):
        param_decls = None
        if not self.at('{'):  # K&R parameter declarations
            param_decls = []
            while not self.at('{'):
                param_decls.extend(self.declaration())
        self._declare(name.value, False)
        decl = c_ast.Decl(name.value, list(spec['quals']), list(spec['align']), list(spec['storage']),
                          list(spec['funcspec']), typ, None, None, coord=self._coord(name))
        body = self.compound()
        return c_ast.FuncDef(decl, param_decls, body, coord=decl.coord)

    def declarator(self, spec, abstract=False):
        name, chain = self._declarator_chain(abstract)
        base = spec['node'] if spec['node'] is not None else c_ast.IdentifierType(list(spec['names']), coord=spec['coord'])
        typ = c_ast.TypeDecl(name and name.value, list(spec['quals']), [], base, coord=spec['coord'])
        for node in reversed(chain):
            node.type = typ
            typ = node
        return name, typ

    def _declarator_chain(self, abstract):
        pointers = []
        while self.at('*'):
            star = self.next()
            quals = []
            while self.peek().type not in NAMES and self.peek().value in QUALS:
                quals.append(self.next().value)
            pointers.append(c_ast.PtrDecl(quals, None, coord=self._coord(star)))
        name, inner = None, []
        nested = self.at('(') and (not abstract or self.at('*', 1) or self.at('(', 1) or self.peek(1).type == 'ID')
        if nested:
            self.next()
            name, inner = self._declarator_chain(abstract)
            self.expect(')')
        elif self.peek().type in NAMES:
            name = self.next()
        elif not abstract:
            self.error('expected a declarator')
        suffixes = []
        while self.at('[') or self.at('('):
            suffixes.append(self.array_suffix() if self.at('[') else self.function_suffix())
        return name, inner + suffixes + pointers[::-1]

    def array_suffix(self):
        start = self.next()
        quals = []
        while self.peek().type not in NAMES and self.peek().value in QUALS | {'static'}:
            quals.append(self.next().value)
        dim = None if self.at(']') else self.assignment()
        self.expect(']')  # end of array declarator
        return c_ast.ArrayDecl(None, dim, quals, coord=self._coord(start))

    def function_suffix(self):
        start = self.next()
        coord = self._coord(start)
        if self.accept(')'):
            return c_ast.FuncDecl(None, None, coord=coord)
        params = []
        if self.peek().type == 'ID' and (self.at(',', 1) or self.at(')', 1)):  # K&R identifier list
            while True:
                token = self.next()
                params.append(c_ast.ID(token.value, coord=self._coord(token)))
                if not self.accept(','):
                    break
        else:
            while True:
                if self.at('...'):
                    params.append(c_ast.EllipsisParam(coord=self._coord(self.next())))
                    break
                spec = self.specifiers()
                name, typ = self.declarator(spec, abstract=True)
                if name:
                    params.append(c_ast.Decl(name.value, list(spec['quals']), list(spec['align']), list(spec['storage']),
                                             list(spec['funcspec']), typ, None, None, coord=self._coord(name)))
                else:
                    params.append(c_ast.Typename(None, list(spec['quals']), list(spec['align']), typ, coord=spec['coord']))
                if not self.accept(','):
                    break
        self.expect(')')
        return c_ast.FuncDecl(c_ast.ParamList(params, coord=coord), None, coord=coord)

    def typename(self):
        spec = self.specifiers()
        _, typ = self.declarator(spec, abstract=True)
        return c_ast.Typename(None, list(spec['quals']), list(spec['align']), typ, coord=spec['coord'])

    def struct_or_union(self):
        start = self.next()
        kind = c_ast.Struct if start.value == 'struct' else c_ast.Union
        name = self.next().value if self.peek().type in NAMES else None
        members = None
        if self.accept('{'):
            members = []
            while not self.accept('}'):
                members.extend(self.struct_declaration())
        return kind(name, members, coord=self._coord(start))

    def struct_declaration(self):
        spec = self.specifiers()
        if self.accept(';'):  # anonymous struct/union member
            return [self._bare_decl(spec)]
        out = []
        while True:
            name, typ = self.declarator(spec, abstract=self.at(':'))
            bitsize = self.conditional() if self.accept(':') else None
            out.append(c_ast.Decl(name and name.value, list(spec['quals']), list(spec['align']), [], [],
                                  typ, None, bitsize, coord=self._coord(name) if name else spec['coord']))
            if not self.accept(','):
                break
        self.expect(';')
        return out

    def enum(self):
        start = self.next()
        name = self.next().value if self.peek().type in NAMES else None
        values = None
        if self.accept('{'):
            items = []
            while not self.accept('}'):
                token = self.next()
                value = self.conditional() if self.accept('=') else None
                items.append(c_ast.Enumerator(token.value, value, coord=self._coord(token)))
                self._declare(token.value, False)
                if not self.accept(','):
                    self.expect('}')
                    break
            values = c_ast.EnumeratorList(items, coord=self._coord(start))
        return c_ast.Enum(name, values, coord=self._coord(start))

    def initializer(self):
        if not self.at('{'):
            return self.assignment()
        start = self.next()
        exprs = []
        while not self.accept('}'):
            designators = []
            while self.at('.') or self.at('['):
                if self.accept('.'):
                    token = self.next()
                    designators.append(c_ast.ID(token.value, coord=self._coord(token)))
                else:
                    self.next()
                    designators.append(self.conditional())
                    self.expect(']')
            if designators:
                self.expect('=')
                exprs.append(c_ast.NamedInitializer(designators, self.initializer()))
            else:
                exprs.append(self.initializer())
            if not self.accept(','):
                self.expect('}')
                break
        return c_ast.InitList(exprs, coord=self._coord(start))

    def pragma(self):
        start = self.next()
        if start.type == 'PPPRAGMA':
            return c_ast.Pragma(start.value, coord=self._coord(start))
        self.expect('(')
        text = self.next()
        self.expect(')')
        return c_ast.Pragma(c_ast.Constant('string', text.value, coord=self._coord(text)), coord=self._coord(start))

    def static_assert(self):
        start = self.next()
        self.expect('(')
        cond = self.conditional()
        message = self.primary() if self.accept(',') else None
        self.expect(')')
        self.expect(';')
        return c_ast.StaticAssert(cond, message, coord=self._coord(start))

    # ------------------------------------------------------------------ statements

    def compound(self):
        start = self.expect('{')
        items = []
        while not self.accept('}'):
            if self.at('_Static_assert'):
                items.append(self.static_assert())
            elif self.starts_type(self.peek()):
                items.extend(self.declaration())
            else:
                stmt = self.statement()
                labels = (c_ast.Case, c_ast.Default)
                if items and isinstance(items[-1], labels) and not isinstance(stmt, labels):
                    items[-1].stmts.append(stmt)
                else:
                    items.append(stmt)
        return c_ast.Compound(items, coord=self._coord(start))

    def _paren_expression(self):
        self.expect('(')
        expr = self.expression()
        self.expect(')')
        return expr

    def statement(self):
        token = self.peek()
        coord = self._coord(token)
        if token.type == 'PPPRAGMA' or self.at('_Pragma'):
            return self.pragma()
        if self.at('{'):
            return self.compound()
        if self.accept('if'):
            cond = self._paren_expression()
            iftrue = self.statement()
            iffalse = self.statement() if self.accept('else') else None
            return c_ast.If(cond, iftrue, iffalse, coord=coord)
        if self.accept('while'):
            cond = self._paren_expression()
            return c_ast.While(cond, self.statement(), coord=coord)
        if self.accept('do'):
            body = self.statement()
            self.expect('while')
            cond = self._paren_expression()
            self.expect(';')
            return c_ast.DoWhile(cond, body, coord=coord)
        if self.accept('for'):
            self.expect('(')
            if self.starts_type(self.peek()):
                init = c_ast.DeclList(self.declaration(), coord=coord)
            else:
                init = None if self.at(';') else self.expression()
                self.expect(';')
            cond = None if self.at(';') else self.expression()
            self.expect(';')
            step = None if self.at(')') else self.expression()
            self.expect(')')
            return c_ast.For(init, cond, step, self.statement(), coord=coord)
        if self.accept('switch'):
            cond = self._paren_expression()
            return c_ast.Switch(cond, self.statement(), coord=coord)
        if self.accept('case'):
            expr = self.conditional()
            self.expect(':')
            return c_ast.Case(expr, [self.statement()], coord=coord)
        if self.accept('default'):
            self.expect(':')
            return c_ast.Default([self.statement()], coord=coord)
        if self.accept('goto'):
            name = self.next().value
            self.expect(';')
            return c_ast.Goto(name, coord=coord)
        if self.accept('break'):
            self.expect(';')
            return c_ast.Break(coord=coord)
        if self.accept('continue'):
            self.expect(';')
            return c_ast.Continue(coord=coord)
        if self.accept('return'):
            expr = None if self.at(';') else self.expression()
            self.expect(';')
            return c_ast.Return(expr, coord=coord)
        if self.accept(';'):
            return c_ast.EmptyStatement(coord=coord)
        if token.type == 'ID' and self.at(':', 1):
            self.next()
            self.next()
            return c_ast.Label(token.value, self.statement(), coord=coord)
        expr = self.expression()
        self.expect(';')
        return expr

    # ------------------------------------------------------------------ expressions

    def expression(self):
        first = self.assignment()
        if not self.at(','):
            return first
        exprs = [first]
        while self.accept(','):
            exprs.append(self.assignment())
        return c_ast.ExprList(exprs, coord=first.coord)

    def assignment(self):
        left = self.conditional()
        token = self.peek()
        if token.value in ASSIGN and token.type not in NAMES:
            self.next()
            return c_ast.Assignment(token.value, left, self.assignment(), coord=left.coord)
        return left

    def conditional(self):
        cond = self.binary(1)
        if not self.accept('?'):
            return cond
        iftrue = self.expression()
        self.expect(':')
        return c_ast.TernaryOp(cond, iftrue, self.conditional(), coord=cond.coord)

    def binary(self, minimum):
        left = self.cast()
        while True:
            token = self.peek()
            precedence = BINARY.get(token.value) if token.type not in NAMES else None
            if precedence is None or precedence < minimum:
                return left
            self.next()
            right = self.binary(precedence + 1)
            left = c_ast.BinaryOp(token.value, left, right, coord=left.coord)

    def cast(self):
        if self.at('(') and self.starts_type(self.peek(1)):
            start = self.next()
            to_type = self.typename()
            self.expect(')')
            if self.at('{'):
                return self.postfix(c_ast.CompoundLiteral(to_type, self.initializer(), coord=self._coord(start)))
            return c_ast.Cast(to_type, self.cast(), coord=self._coord(start))
        return self.unary()

    def unary(self):
        token = self.peek()
        coord = self._coord(token)
        if token.type in ('PLUSPLUS', 'MINUSMINUS'):
            self.next()
            return c_ast.UnaryOp(token.value, self.unary(), coord=coord)
        if token.type in ('AND', 'TIMES', 'PLUS', 'MINUS', 'NOT', 'LNOT'):
            self.next()
            return c_ast.UnaryOp(token.value, self.cast(), coord=coord)
        if self.at('sizeof') or self.at('_Alignof'):
            self.next()
            if self.at('(') and self.starts_type(self.peek(1)):
                self.next()
                operand = self.typename()
                self.expect(')')
                return c_ast.UnaryOp(token.value, operand, coord=coord)
            return c_ast.UnaryOp(token.value, self.unary(), coord=coord)
        return self.postfix(self.primary())

    def postfix(self, expr):
        while True:
            token = self.peek()
            coord = expr.coord
            if self.accept('['):
                subscript = self.expression()
                self.expect(']')
                expr = c_ast.ArrayRef(expr, subscript, coord=coord)
            elif self.accept('('):
                args = None
                if not self.at(')'):
                    items = [self.assignment()]
                    while self.accept(','):
                        items.append(self.assignment())
                    args = c_ast.ExprList(items, coord=items[0].coord)
                self.expect(')')
                expr = c_ast.FuncCall(expr, args, coord=coord)
            elif self.accept('.') or self.accept('->'):
                field = self.next()
                expr = c_ast.StructRef(expr, token.value, c_ast.ID(field.value, coord=self._coord(field)), coord=coord)
            elif self.accept('++') or self.accept('--'):
                expr = c_ast.UnaryOp('p' + token.value, expr, coord=coord)
            else:
                return expr

    def primary(self):
        token = self.peek()
        coord = self._coord(token)
        kind = token.type
        if kind == 'ID':
            return c_ast.ID(self.next().value, coord=coord)
        if kind.startswith('INT_CONST') or kind in ('FLOAT_CONST', 'HEX_FLOAT_CONST'):
            return c_ast.Constant(_constant_type(kind, token.value), self.next().value, coord=coord)
        if kind in ('CHAR_CONST', 'WCHAR_CONST'):
            return c_ast.Constant('char', self.next().value, coord=coord)
        if kind in ('STRING_LITERAL', 'WSTRING_LITERAL'):
            return c_ast.Constant('string', self.next().value, coord=coord)
        if self.accept('('):
            expr = self.expression()
            self.expect(')')
            return expr
        self.error('unexpected token')
