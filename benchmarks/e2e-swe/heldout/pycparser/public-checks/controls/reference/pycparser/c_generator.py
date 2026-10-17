"""Regenerate C source text from c_ast trees."""
from . import c_ast
from .c_parser import BINARY

SIMPLE = (c_ast.ID, c_ast.Constant, c_ast.ArrayRef, c_ast.StructRef, c_ast.FuncCall, c_ast.CompoundLiteral)
LOOSE = (c_ast.Assignment, c_ast.TernaryOp, c_ast.ExprList)
STATEMENTS = (c_ast.Compound, c_ast.If, c_ast.For, c_ast.While, c_ast.DoWhile, c_ast.Switch, c_ast.Case,
              c_ast.Default, c_ast.Label, c_ast.Goto, c_ast.Return, c_ast.Break, c_ast.Continue,
              c_ast.EmptyStatement, c_ast.Pragma, c_ast.FuncDef)


class CGenerator:
    def __init__(self, reduce_parentheses=False):
        self.reduce_parentheses = reduce_parentheses
        self.indent = 0

    def visit(self, node):
        if node is None:
            return ''
        return getattr(self, 'visit_' + type(node).__name__)(node)

    # ------------------------------------------------------------------ expressions

    def _wrap(self, node, keep=SIMPLE):
        text = self.visit(node)
        return text if isinstance(node, keep) else f'({text})'

    def visit_ID(self, n):
        return n.name

    def visit_Constant(self, n):
        return n.value

    def visit_ArrayRef(self, n):
        return f'{self._wrap(n.name)}[{self.visit(n.subscript)}]'

    def visit_StructRef(self, n):
        return f'{self._wrap(n.name)}{n.type}{self.visit(n.field)}'

    def visit_FuncCall(self, n):
        return f'{self._wrap(n.name)}({self.visit(n.args)})'

    def visit_UnaryOp(self, n):
        if n.op in ('p++', 'p--'):
            return self._wrap(n.expr) + n.op[1:]
        if n.op in ('sizeof', '_Alignof'):
            return f'{n.op}({self.visit(n.expr)})'
        return n.op + self._wrap(n.expr)

    def visit_BinaryOp(self, n):
        left = self._operand(n.left, n.op, False)
        right = self._operand(n.right, n.op, True)
        return f'{left} {n.op} {right}'

    def _operand(self, node, op, is_right):
        text = self.visit(node)
        if isinstance(node, c_ast.BinaryOp):
            if not self.reduce_parentheses:
                return f'({text})'
            inner, outer = BINARY[node.op], BINARY[op]
            if inner > outer or (inner == outer and not is_right):
                return text
            return f'({text})'
        return f'({text})' if isinstance(node, LOOSE) else text

    def visit_Assignment(self, n):
        rvalue = self._wrap(n.rvalue, keep=(c_ast.Node,)) if not isinstance(n.rvalue, c_ast.ExprList) else f'({self.visit(n.rvalue)})'
        return f'{self._wrap(n.lvalue, keep=SIMPLE + (c_ast.UnaryOp,))} {n.op} {rvalue}'

    def visit_TernaryOp(self, n):
        keep = SIMPLE + (c_ast.UnaryOp, c_ast.Cast)
        return f'{self._wrap(n.cond, keep)} ? {self._wrap(n.iftrue, keep)} : {self._wrap(n.iffalse, keep)}'

    def visit_Cast(self, n):
        return f'({self.visit(n.to_type)}) {self._wrap(n.expr, SIMPLE + (c_ast.UnaryOp, c_ast.Cast))}'

    def visit_ExprList(self, n):
        return ', '.join(self._wrap(e, keep=(c_ast.Node,)) if not isinstance(e, c_ast.ExprList) else f'({self.visit(e)})'
                         for e in n.exprs)

    def visit_InitList(self, n):
        return '{' + ', '.join(self._init(e) for e in n.exprs) + '}'

    def visit_NamedInitializer(self, n):
        designators = ''.join('.' + d.name if isinstance(d, c_ast.ID) else f'[{self.visit(d)}]' for d in n.name)
        return f'{designators} = {self._init(n.expr)}'

    def _init(self, node):
        return f'({self.visit(node)})' if isinstance(node, c_ast.ExprList) else self.visit(node)

    def visit_CompoundLiteral(self, n):
        return f'({self.visit(n.type)}){self.visit(n.init)}'

    # ------------------------------------------------------------------ declarations

    def visit_Decl(self, n):
        parts = list(n.storage or []) + list(n.funcspec or [])
        parts += [self.visit(a) for a in n.align or []]
        if isinstance(n.type, (c_ast.Struct, c_ast.Union, c_ast.Enum)):
            parts += list(n.quals or []) + [self.visit(n.type)]
        else:
            parts.append(self._type(n.type))
        text = ' '.join(part for part in parts if part)
        if n.bitsize is not None:
            text += ' : ' + self.visit(n.bitsize)
        if n.init is not None:
            text += ' = ' + self._init(n.init)
        return text

    def visit_Typedef(self, n):
        return ' '.join(list(n.storage or []) + [self._type(n.type)])

    def visit_Typename(self, n):
        return self._type(n.type)

    def visit_Alignas(self, n):
        return f'_Alignas({self.visit(n.alignment)})'

    def visit_DeclList(self, n):
        # ponytail: one declaration per for-init; several would need a shared specifier prefix
        return ', '.join(self.visit(d) for d in n.decls)

    def _type(self, typ):
        modifiers = []
        while not isinstance(typ, c_ast.TypeDecl):
            modifiers.append(typ)
            typ = typ.type
        text = typ.declname or ''
        previous = None
        for node in modifiers:
            if isinstance(node, c_ast.PtrDecl):
                text = '*' + ''.join(q + ' ' for q in node.quals or []) + text
            else:
                if isinstance(previous, c_ast.PtrDecl):
                    text = f'({text})'
                if isinstance(node, c_ast.ArrayDecl):
                    inside = list(node.dim_quals or []) + ([self.visit(node.dim)] if node.dim is not None else [])
                    text += '[' + ' '.join(inside) + ']'
                else:
                    text += f'({self.visit(node.args)})'
            previous = node
        base = ' '.join(list(typ.quals or []) + [self.visit(typ.type)])
        return f'{base} {text}'.strip()

    visit_TypeDecl = visit_PtrDecl = visit_ArrayDecl = visit_FuncDecl = _type

    def visit_IdentifierType(self, n):
        return ' '.join(n.names)

    def visit_ParamList(self, n):
        return ', '.join(self.visit(p) for p in n.params)

    def visit_EllipsisParam(self, n):
        return '...'

    def _aggregate(self, keyword, name, body):
        text = keyword + (' ' + name if name else '')
        return text if body is None else text + ' { ' + body + '}'

    def visit_Struct(self, n):
        return self._aggregate('struct', n.name, None if n.decls is None else ''.join(self.visit(d) + '; ' for d in n.decls))

    def visit_Union(self, n):
        return self._aggregate('union', n.name, None if n.decls is None else ''.join(self.visit(d) + '; ' for d in n.decls))

    def visit_Enum(self, n):
        return self._aggregate('enum', n.name, None if n.values is None else self.visit(n.values) + ' ')

    def visit_EnumeratorList(self, n):
        return ', '.join(self.visit(e) for e in n.enumerators)

    def visit_Enumerator(self, n):
        return n.name + ('' if n.value is None else ' = ' + self.visit(n.value))

    def visit_StaticAssert(self, n):
        message = '' if n.message is None else ', ' + self.visit(n.message)
        return f'_Static_assert({self.visit(n.cond)}{message})'

    # ------------------------------------------------------------------ statements

    def _pad(self):
        return '  ' * self.indent

    def _stmt(self, node):
        if isinstance(node, STATEMENTS):
            return self.visit(node)
        return self._pad() + self.visit(node) + ';\n'

    def _nested(self, node):
        if isinstance(node, c_ast.Compound):
            return self._stmt(node)
        self.indent += 1
        text = self._stmt(node)
        self.indent -= 1
        return text

    def visit_FileAST(self, n):
        return ''.join(self._stmt(e) for e in n.ext)

    def visit_FuncDef(self, n):
        knr = ''.join(self._pad() + self.visit(d) + ';\n' for d in n.param_decls or [])
        return self._pad() + self.visit(n.decl) + '\n' + knr + self.visit(n.body)

    def visit_Compound(self, n):
        self.indent += 1
        body = ''.join(self._stmt(s) for s in n.block_items or [])
        self.indent -= 1
        return self._pad() + '{\n' + body + self._pad() + '}\n'

    def visit_If(self, n):
        text = self._pad() + f'if ({self.visit(n.cond)})\n' + self._nested(n.iftrue)
        if n.iffalse is not None:
            text += self._pad() + 'else\n' + self._nested(n.iffalse)
        return text

    def visit_For(self, n):
        head = f'for ({self.visit(n.init)}; {self.visit(n.cond)}; {self.visit(n.next)})'
        return self._pad() + head + '\n' + self._nested(n.stmt)

    def visit_While(self, n):
        return self._pad() + f'while ({self.visit(n.cond)})\n' + self._nested(n.stmt)

    def visit_DoWhile(self, n):
        return self._pad() + 'do\n' + self._nested(n.stmt) + self._pad() + f'while ({self.visit(n.cond)});\n'

    def visit_Switch(self, n):
        return self._pad() + f'switch ({self.visit(n.cond)})\n' + self._nested(n.stmt)

    def visit_Case(self, n):
        return self._pad() + f'case {self.visit(n.expr)}:\n' + ''.join(self._nested(s) for s in n.stmts or [])

    def visit_Default(self, n):
        return self._pad() + 'default:\n' + ''.join(self._nested(s) for s in n.stmts or [])

    def visit_Label(self, n):
        return self._pad() + n.name + ':\n' + self._stmt(n.stmt)

    def visit_Goto(self, n):
        return self._pad() + f'goto {n.name};\n'

    def visit_Return(self, n):
        return self._pad() + 'return' + ('' if n.expr is None else ' ' + self.visit(n.expr)) + ';\n'

    def visit_Break(self, n):
        return self._pad() + 'break;\n'

    def visit_Continue(self, n):
        return self._pad() + 'continue;\n'

    def visit_EmptyStatement(self, n):
        return self._pad() + ';\n'

    def visit_Pragma(self, n):
        if isinstance(n.string, c_ast.Node):
            return self._pad() + f'_Pragma({self.visit(n.string)})\n'
        return f'#pragma {n.string}\n'
