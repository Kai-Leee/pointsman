"""AST node classes, written from the public instruction's node table.

Each class is generated from one table row: unmarked names are leaf attributes
(attr_names), `*` names are child nodes and `**` names are lists of child nodes.
"""
import sys


class Node:
    __slots__ = ('coord',)
    attr_names = ()
    _fields = ()

    def __init__(self, *args, coord=None, **kwargs):
        names = [name for name, _ in self._fields]
        if len(args) > len(names):
            raise TypeError(f'{type(self).__name__}() takes {len(names)} positional arguments')
        values = dict(zip(names, args))
        for key, value in kwargs.items():
            if key not in names or key in values:
                raise TypeError(f'{type(self).__name__}() got an unexpected or repeated argument {key!r}')
            values[key] = value
        for name in names:
            setattr(self, name, values.get(name))
        self.coord = coord

    def children(self):
        out = []
        for name, kind in self._fields:
            value = getattr(self, name)
            if kind == '*' and value is not None:
                out.append((name, value))
            elif kind == '**':
                for index, child in enumerate(value or ()):
                    out.append((f'{name}[{index}]', child))
        return tuple(out)

    def __iter__(self):
        for _, child in self.children():
            yield child

    def show(self, buf=sys.stdout, offset=0, attrnames=False, nodenames=False, showcoord=False, _my_node_name=None):
        label = type(self).__name__
        if nodenames and _my_node_name is not None:
            label += ' <' + _my_node_name + '>'
        buf.write(' ' * offset + label + ':')
        if attrnames and self.attr_names:
            buf.write(' ' + ', '.join(f'{name}={getattr(self, name)!r}' for name in self.attr_names))
        if showcoord and self.coord is not None:
            buf.write(f' (at {self.coord})')
        buf.write('\n')
        for name, child in self.children():
            child.show(buf, offset + 2, attrnames, nodenames, showcoord, _my_node_name=name)


_TABLE = '''
FileAST: ext**
Decl: name quals align storage funcspec type* init* bitsize*
TypeDecl: declname quals align type*
IdentifierType: names
PtrDecl: quals type*
ArrayDecl: type* dim* dim_quals
FuncDecl: args* type*
FuncDef: decl* param_decls** body*
Typedef: name quals storage type*
Struct: name decls**
Union: name decls**
Enum: name values*
Enumerator: name value*
EnumeratorList: enumerators**
ParamList: params**
EllipsisParam:
DeclList: decls**
Typename: name quals align type*
Compound: block_items**
If: cond* iftrue* iffalse*
For: init* cond* next* stmt*
While: cond* stmt*
DoWhile: cond* stmt*
Switch: cond* stmt*
Case: expr* stmts**
Default: stmts**
Return: expr*
Break:
Continue:
EmptyStatement:
Goto: name
Label: name stmt*
BinaryOp: op left* right*
UnaryOp: op expr*
TernaryOp: cond* iftrue* iffalse*
Assignment: op lvalue* rvalue*
Cast: to_type* expr*
FuncCall: name* args*
ExprList: exprs**
InitList: exprs**
Constant: type value
ID: name
ArrayRef: name* subscript*
StructRef: name* type field*
NamedInitializer: name** expr*
CompoundLiteral: type* init*
StaticAssert: cond* message*
Pragma: string
Alignas: alignment*
'''

for _row in _TABLE.strip().splitlines():
    _name, _, _rest = _row.partition(':')
    _spec = tuple((word.rstrip('*'), word[len(word.rstrip('*')):]) for word in _rest.split())
    globals()[_name] = type(_name, (Node,), {
        '__slots__': tuple(field for field, _ in _spec),
        '_fields': _spec,
        'attr_names': tuple(field for field, kind in _spec if not kind),
        '__module__': __name__,
    })


class NodeVisitor:
    def visit(self, node):
        method = getattr(self, 'visit_' + type(node).__name__, None)
        if method is None:
            return self.generic_visit(node)
        return method(node)

    def generic_visit(self, node):
        for child in node:
            self.visit(child)
