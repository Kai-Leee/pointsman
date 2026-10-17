"""Public acceptance cases for pycparser, authored from the task's public instruction.md only.

Each case asserts only what the instruction states; points its atoms list as gaps are left
unasserted. The candidate package is imported inside the case functions.
"""
import io
import json
import re

CASES = {}


def case(test_id):
    def register(function):
        CASES[test_id] = function
        return function
    return register


# ----------------------------------------------------------------------------- checker helpers

def ast():
    from pycparser import c_ast
    return c_ast


def parse(text, **kwargs):
    from pycparser import CParser
    return CParser().parse(text, **kwargs)


def generate(node, reduce_parentheses=None):
    from pycparser.c_generator import CGenerator
    generator = CGenerator() if reduce_parentheses is None else CGenerator(reduce_parentheses=reduce_parentheses)
    return generator.visit(node)


def lex(text, lookup=lambda name: False, calls=None):
    from pycparser.c_lexer import CLexer

    def record(name):
        if calls is not None:
            calls.append(name)
        return lookup(name)

    lexer = CLexer(lambda *args: None, lambda *args: None, lambda *args: None, record)
    lexer.input(text)
    tokens = []
    for _ in range(10000):
        token = lexer.token()
        if token is None:
            return tokens
        tokens.append(token)
    raise AssertionError('lexer did not reach the end of input')


def walk(node):
    yield node
    for _, child in node.children():
        yield from walk(child)


def nodes(root, kind):
    cls = getattr(ast(), kind)
    return [n for n in walk(root) if isinstance(n, cls)]


def named(root, name, kind='Decl'):
    found = [n for n in nodes(root, kind) if n.name == name]
    if not found:
        raise AssertionError(f'no {kind} named {name!r}')
    return found[0]


def is_a(node, kind):
    return isinstance(node, getattr(ast(), kind))


def leaf_values(node):
    """Every leaf attribute value in a subtree (used where the node class is left open)."""
    values = []
    for n in walk(node):
        values += [getattr(n, name) for name in n.attr_names]
    return values


def statements(function_def):
    return list(function_def.body.block_items or [])


def difference(a, b, path='root'):
    """Structural comparison: node class, attr_names values, children() names (coord ignored)."""
    c_ast = ast()
    if isinstance(a, c_ast.Node) or isinstance(b, c_ast.Node):
        if type(a).__name__ != type(b).__name__:
            return f'{path}: {type(a).__name__} != {type(b).__name__}'
        for name in a.attr_names:
            found = difference(getattr(a, name), getattr(b, name), f'{path}.{name}')
            if found:
                return found
        ka, kb = a.children(), b.children()
        if [n for n, _ in ka] != [n for n, _ in kb]:
            return f'{path}: children {[n for n, _ in ka]} != {[n for n, _ in kb]}'
        for (name, x), (_, y) in zip(ka, kb):
            found = difference(x, y, f'{path}/{name}')
            if found:
                return found
        return None
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            return f'{path}: length {len(a)} != {len(b)}'
        for index, (x, y) in enumerate(zip(a, b)):
            found = difference(x, y, f'{path}[{index}]')
            if found:
                return found
        return None
    return None if a == b else f'{path}: {a!r} != {b!r}'


def to_json(node):
    """The instruction's generic walker: _nodetype, attr_names values, children() entries, coord string."""
    c_ast = ast()

    def convert(value):
        if isinstance(value, c_ast.Node):
            return to_json(value)
        if isinstance(value, (list, tuple)):
            return [convert(v) for v in value]
        return value

    out = {'_nodetype': type(node).__name__}
    for name in node.attr_names:
        out[name] = convert(getattr(node, name))
    for name, child in node.children():
        out[name] = to_json(child)
    out['coord'] = None if node.coord is None else str(node.coord)
    return out


def json_nodes(data):
    if isinstance(data, dict):
        if '_nodetype' in data:
            yield data
        for value in data.values():
            yield from json_nodes(value)
    elif isinstance(data, list):
        for value in data:
            yield from json_nodes(value)


def roundtrip(c, tree, label, reduce_parentheses=None):
    text = generate(tree, reduce_parentheses)
    c.require(isinstance(text, str), f'{label}: generator returns a str')
    again = parse(text)
    c.equal(difference(tree, again), None, f'{label}: re-parsed AST equals the original\n{text}')
    return text, again


def stdlib_probe(c):
    code = r'''
import json, sys
before = set(sys.modules)
import pycparser, pycparser.c_ast, pycparser.c_parser, pycparser.c_lexer, pycparser.c_generator
loaded = sorted({name.split('.')[0] for name in set(sys.modules) - before})
import importlib.metadata as md
dists = md.packages_distributions().get('pycparser') or ['pycparser']
requires = {}
for dist in dists:
    try:
        requires[dist] = md.distribution(dist).requires or []
    except md.PackageNotFoundError:
        requires[dist] = None
print(json.dumps({'loaded': loaded, 'requires': requires,
                  'stdlib': sorted(set(sys.stdlib_module_names) | set(sys.builtin_module_names))}))
'''
    done = c.run_python(code)
    c.equal(done.returncode, 0, f'importing every pycparser module succeeds: {done.stderr[-1500:]}')
    data = json.loads(done.stdout.strip().splitlines()[-1])
    foreign = [name for name in data['loaded'] if name != 'pycparser' and name not in data['stdlib']]
    c.equal(foreign, [], 'modules imported from outside pycparser belong to the standard library')
    return data


# ----------------------------------------------------------------------------- install-surface

@case('T.R01.01')
def tokenize_parse_generate(c):
    from pycparser import CParser, c_ast
    from pycparser.c_generator import CGenerator
    source = 'int main(void) { return 0; }'
    tokens = lex(source)
    c.equal([(t.type, t.value) for t in tokens[:2]], [('INT', 'int'), ('ID', 'main')], 'CLexer tokenizes the source')
    c.equal(len(tokens), 10, 'token count of the source')
    tree = CParser().parse(source)
    c.require(isinstance(tree, c_ast.FileAST), 'parse returns a c_ast.FileAST')
    text = CGenerator().visit(tree)
    c.require(isinstance(text, str) and 'main' in text, 'CGenerator returns C text')
    c.require(isinstance(CParser().parse(text), c_ast.FileAST), 'regenerated text re-parses')
    stdlib_probe(c)


@case('T.R02.01')
def no_third_party_dependencies(c):
    data = stdlib_probe(c)
    for dist, requires in data['requires'].items():
        if requires is None:
            continue
        runtime = [r for r in requires if not re.search(r'extra\s*==', r)]
        c.equal(runtime, [], f'distribution {dist} declares no runtime dependency')


@case('T.R02.02')
def offline_editable_install(c):
    from pathlib import Path
    receipt = c.ctx['install']
    c.equal(receipt.get('pip_no_index'), '1', 'install ran with no package index')
    c.equal(receipt.get('returncode'), 0, f"offline install succeeds: {receipt.get('stderr_tail', '')[-1500:]}")
    done = c.run_python('import pycparser; print(pycparser.__file__)')
    c.equal(done.returncode, 0, f'pycparser imports from an unrelated directory: {done.stderr[-1500:]}')
    location = Path(done.stdout.strip().splitlines()[-1]).resolve()
    project = Path(c.ctx['project']).resolve()
    c.require(project in location.parents, f'import resolves to the project tree (editable): {location}')


@case('T.R03.01')
def public_import_surface(c):
    code = '\n'.join([
        'from pycparser import CParser, c_ast',
        'from pycparser.c_ast import NodeVisitor',
        'from pycparser.c_generator import CGenerator',
        'from pycparser.c_lexer import CLexer, Token',
        'from pycparser.c_parser import Coord, ParseError',
        'print("ok")',
    ])
    done = c.run_python(code)
    c.equal(done.returncode, 0, f'the five documented imports succeed: {done.stderr[-1500:]}')
    c.equal(done.stdout.strip(), 'ok', 'import script completed')


@case('T.R03.02')
def top_level_reexport(c):
    import pycparser
    import pycparser.c_parser
    c.require(pycparser.CParser is pycparser.c_parser.CParser, 'pycparser.CParser is pycparser.c_parser.CParser')


# ----------------------------------------------------------------------------- parser-declarations

@case('T.R04.01')
def parse_returns_fileast_with_filename(c):
    from pycparser import CParser, c_ast
    parser = CParser()
    a = parser.parse('int x;')
    b = parser.parse('int x;\nint y;', filename='m.c')
    c.require(isinstance(a, c_ast.FileAST) and isinstance(b, c_ast.FileAST), 'both parses return FileAST')
    x = named(a, 'x')
    c.equal(x.coord.file, '<unknown>', 'default filename')
    y = named(b, 'y')
    c.equal((y.coord.file, y.coord.line), ('m.c', 2), 'Decl y coord file and line')


@case('T.R04.02')
def variable_function_and_knr(c):
    tree = parse('int x, *p; extern int g(int, char *); int kr(a, b) int a; char b; { return a; }')
    c.require(is_a(named(tree, 'x').type, 'TypeDecl'), 'x is a TypeDecl')
    c.require(is_a(named(tree, 'p').type, 'PtrDecl'), 'p is a PtrDecl')
    g = named(tree, 'g')
    c.equal(g.storage, ['extern'], 'g storage')
    c.require(is_a(g.type, 'FuncDecl') and is_a(g.type.args, 'ParamList'), 'g is a FuncDecl with a ParamList')
    c.equal(len(g.type.args.params), 2, 'g has two parameters')
    kr = [f for f in nodes(tree, 'FuncDef') if f.decl.name == 'kr']
    c.equal(len(kr), 1, 'kr is a FuncDef')
    params = kr[0].param_decls
    c.require(isinstance(params, list) and len(params) == 2, f'kr.param_decls lists two Decls: {params!r}')
    c.equal([(type(d).__name__, d.name) for d in params], [('Decl', 'a'), ('Decl', 'b')], 'K&R declarations')
    c.equal([d.type.type.names for d in params], [['int'], ['char']], 'K&R declaration types')
    c.require(is_a(kr[0].body, 'Compound'), 'kr body is a Compound')


@case('T.R04.03')
def specifiers_and_declarator_chains(c):
    tree = parse('unsigned long long int a; const volatile char c; _Atomic int t; int *p; int m[3][4]; int (*fp)(int, double);')
    a = named(tree, 'a')
    c.equal(a.type.type.names, ['unsigned', 'long', 'long', 'int'], 'multi-word specifier in source order')
    cq = named(tree, 'c')
    c.require('const' in cq.quals and 'volatile' in cq.quals, f'c carries const and volatile: {cq.quals}')
    c.require('_Atomic' in named(tree, 't').type.quals, 't carries _Atomic on its TypeDecl')
    p = named(tree, 'p').type
    c.require(is_a(p, 'PtrDecl') and is_a(p.type, 'TypeDecl') and p.type.declname == 'p', 'p: PtrDecl -> TypeDecl(p)')
    m = named(tree, 'm').type
    c.require(is_a(m, 'ArrayDecl') and is_a(m.dim, 'Constant') and m.dim.value == '3', 'm outer ArrayDecl dim 3')
    c.require(is_a(m.type, 'ArrayDecl') and is_a(m.type.dim, 'Constant') and m.type.dim.value == '4', 'm inner ArrayDecl dim 4')
    c.require(is_a(m.type.type, 'TypeDecl') and m.type.type.declname == 'm', 'm chain ends in TypeDecl(m)')
    fp = named(tree, 'fp').type
    c.require(is_a(fp, 'PtrDecl') and is_a(fp.type, 'FuncDecl'), 'fp: PtrDecl -> FuncDecl')
    c.equal(len(fp.type.args.params), 2, 'fp takes two parameters')
    c.require(is_a(fp.type.type, 'TypeDecl') and fp.type.type.declname == 'fp', 'fp chain ends in TypeDecl(fp)')


@case('T.R04.04')
def struct_union_enum_members(c):
    tree = parse('struct S { unsigned a : 3; union { int i; float f; }; char data[]; }; enum E { A, B = 2 };')
    s = [n for n in nodes(tree, 'Struct') if n.name == 'S' and n.decls is not None]
    c.equal(len(s), 1, 'struct S definition found')
    members = s[0].decls
    c.equal(len(members), 3, 'struct S has three members')
    c.equal(members[0].name, 'a', 'first member name')
    c.require(is_a(members[0].bitsize, 'Constant') and members[0].bitsize.value == '3', 'a has bitsize 3')
    c.equal(members[1].name, None, 'anonymous member has no name')
    c.require(is_a(members[1].type, 'Union') and len(members[1].type.decls) == 2, 'anonymous member is a two-member Union')
    c.equal(members[2].name, 'data', 'third member name')
    c.require(is_a(members[2].type, 'ArrayDecl') and members[2].type.dim is None, 'flexible array member has dim None')
    e = [n for n in nodes(tree, 'Enum') if n.name == 'E']
    c.equal(len(e), 1, 'enum E found')
    c.require(is_a(e[0].values, 'EnumeratorList'), 'enum values is an EnumeratorList')
    items = e[0].values.enumerators
    c.equal([(i.name, i.value is None) for i in items], [('A', True), ('B', False)], 'enumerators')
    c.require(is_a(items[1].value, 'Constant') and items[1].value.value == '2', 'B = 2')


@case('T.R04.05')
def designated_initializers_and_compound_literals(c):
    tree = parse('struct P { int x, y; }; struct P p = { .y = 2, .x = 1 }; int a[4] = { [2] = 5, 6 }; int *q = (int []){ 1, 2 };')
    init = named(tree, 'p').init
    c.require(is_a(init, 'InitList') and len(init.exprs) == 2, 'p.init is a two-element InitList')
    for item, field, value in zip(init.exprs, 'yx', '21'):
        c.require(is_a(item, 'NamedInitializer'), f'.{field} initializer is a NamedInitializer')
        c.require(len(item.name) == 1 and field in leaf_values(item.name[0]), f'designator names {field}')
        c.require(is_a(item.expr, 'Constant') and item.expr.value == value, f'.{field} = {value}')
    init = named(tree, 'a').init
    c.require(is_a(init, 'InitList') and len(init.exprs) == 2, 'a.init is a two-element InitList')
    first, second = init.exprs
    c.require(is_a(first, 'NamedInitializer') and len(first.name) == 1 and '2' in leaf_values(first.name[0]), 'first designates index 2')
    c.require(is_a(first.expr, 'Constant') and first.expr.value == '5', '[2] = 5')
    c.require(is_a(second, 'Constant') and second.value == '6', 'second element is Constant 6')
    q = named(tree, 'q').init
    c.require(is_a(q, 'CompoundLiteral') and is_a(q.type, 'Typename'), 'q.init is a CompoundLiteral with a Typename')
    c.require(is_a(q.init, 'InitList') and [e.value for e in q.init.exprs] == ['1', '2'], 'compound literal InitList 1, 2')


@case('T.R04.08')
def c11_keywords(c):
    tree = parse('_Static_assert(sizeof(int) == 4, "int size"); _Alignas(16) int buf; _Noreturn void die(void); '
                 '_Atomic int a; _Atomic(int) b; _Pragma("once")\nint z;')
    asserts = nodes(tree, 'StaticAssert')
    c.equal(len(asserts), 1, 'one StaticAssert')
    c.require(is_a(asserts[0].cond, 'BinaryOp') and asserts[0].cond.op == '==', 'StaticAssert cond is BinaryOp ==')
    message = asserts[0].message
    c.require(is_a(message, 'Constant') and message.value.startswith('"'), 'StaticAssert message is a string Constant')
    align = named(tree, 'buf').align
    c.require(isinstance(align, list) and len(align) == 1 and is_a(align[0], 'Alignas'), 'buf.align holds one Alignas')
    c.require('_Noreturn' in named(tree, 'die').funcspec, 'die funcspec has _Noreturn')
    for name in 'ab':
        decl = named(tree, name)
        c.require('_Atomic' in list(decl.quals) + list(decl.type.quals), f'_Atomic qualifies {name}')
    c.require(any(is_a(e, 'Pragma') for e in tree.ext), 'a Pragma is a file-scope item')
    c.require(is_a(named(tree, 'z').type, 'TypeDecl'), 'z still parses after _Pragma')


@case('T.R04.09')
def vla_and_array_parameter_qualifiers(c):
    tree = parse('void f(int n, const int a[const n]) { int v[n]; }')
    f = nodes(tree, 'FuncDef')[0]
    a = [p for p in f.decl.type.args.params if getattr(p, 'name', None) == 'a']
    c.equal(len(a), 1, 'parameter a found')
    t = a[0].type
    c.require(is_a(t, 'ArrayDecl') and is_a(t.dim, 'ID') and t.dim.name == 'n', 'a: ArrayDecl dim ID n')
    c.equal(t.dim_quals, ['const'], 'a dim_quals')
    v = named(f.body, 'v').type
    c.require(is_a(v, 'ArrayDecl') and is_a(v.dim, 'ID') and v.dim.name == 'n', 'v: ArrayDecl dim ID n')


@case('T.R04.11')
def empty_external_declaration(c):
    c.require(parse(';') is not None, "a lone ';' parses")
    tree = parse('int x;;\n;')
    c.equal(named(tree, 'x').name, 'x', 'Decl x is kept')


@case('T.R04.12')
def scoped_typedef_disambiguation(c):
    tree = parse('typedef int T; int a, b; void f(void) { T * x; a * b; { int T = 3; T = T + 1; } T * y; }')
    f = nodes(tree, 'FuncDef')[0]
    for name in 'xy':
        t = named(f, name).type
        c.require(is_a(t, 'PtrDecl') and is_a(t.type, 'TypeDecl') and is_a(t.type.type, 'IdentifierType'),
                  f'{name}: PtrDecl -> TypeDecl -> IdentifierType')
        c.equal(t.type.type.names, ['T'], f'{name} points to T')
    mul = [n for n in nodes(f, 'BinaryOp') if n.op == '*']
    c.require(len(mul) == 1 and is_a(mul[0].left, 'ID') and mul[0].left.name == 'a', "'a * b;' is a BinaryOp")
    inner = [s for s in statements(f) if is_a(s, 'Compound')]
    c.equal(len(inner), 1, 'inner block found')
    t = named(inner[0], 'T')
    c.require(is_a(t.type, 'TypeDecl') and t.type.type.names == ['int'], 'inner Decl T of type int')
    assigns = nodes(inner[0], 'Assignment')
    c.require(len(assigns) == 1 and is_a(assigns[0].lvalue, 'ID') and assigns[0].lvalue.name == 'T', 'T = T + 1 assigns ID T')


# ----------------------------------------------------------------------------- parser-expressions-statements

@case('T.R04.06')
def precedence_and_comma(c):
    tree = parse('int f(int a, int b, int c) { int x; x = a + b * c; x = a || b && c; x = a - b - c; '
                 'x = (a, b, c); x = a ? b : c; x = (char)a << 1; return x; }')
    rvalues = [s.rvalue for s in statements(nodes(tree, 'FuncDef')[0]) if is_a(s, 'Assignment')]
    c.equal(len(rvalues), 6, 'six assignments')
    r = rvalues
    c.require(is_a(r[0], 'BinaryOp') and r[0].op == '+' and is_a(r[0].right, 'BinaryOp') and r[0].right.op == '*', 'a + (b * c)')
    c.require(is_a(r[1], 'BinaryOp') and r[1].op == '||' and is_a(r[1].right, 'BinaryOp') and r[1].right.op == '&&', 'a || (b && c)')
    c.require(is_a(r[2], 'BinaryOp') and r[2].op == '-' and is_a(r[2].left, 'BinaryOp') and r[2].left.op == '-', '(a - b) - c')
    c.require(r[3] is not None, 'comma expression accepted')
    c.require(is_a(r[4], 'TernaryOp'), 'conditional is a TernaryOp')
    c.require(is_a(r[5], 'BinaryOp') and r[5].op == '<<' and is_a(r[5].left, 'Cast'), '((char)a) << 1')


@case('T.R04.07')
def all_statement_kinds(c):
    tree = parse('int f(int n) { int i; if (n) i = 1; else i = 2; for (i = 0; i < n; i++) continue; while (n) break; '
                 'do n--; while (n); switch (n) { case 1: n = 2; break; default: n = 3; } goto end; end: return n; }')
    body = statements(nodes(tree, 'FuncDef')[0])
    kinds = [type(s).__name__ for s in body]
    for kind in ('If', 'For', 'While', 'DoWhile', 'Switch', 'Goto', 'Label'):
        c.require(kind in kinds, f'{kind} statement in body: {kinds}')
    get = {k: body[kinds.index(k)] for k in kinds}
    c.require(get['If'].iffalse is not None, 'If has an else branch')
    c.require(is_a(get['For'].stmt, 'Continue'), 'For body is Continue')
    c.require(is_a(get['While'].stmt, 'Break'), 'While body is Break')
    inside = [type(n).__name__ for n in walk(get['Switch'].stmt)]
    c.require('Case' in inside and 'Default' in inside, 'Switch statement contains Case and Default')
    c.equal(get['Goto'].name, 'end', 'goto target')
    c.require(get['Label'].name == 'end' and is_a(get['Label'].stmt, 'Return'), 'label end: return')


@case('T.R05.13')
def operator_strings(c):
    tree = parse('void f(void) { x = a + b; x = a * b; x = a || b; x = a && b; x = a == b; x = a >> b; x += a; x *= a; x >>= a; }')
    c.equal([n.op for n in nodes(tree, 'BinaryOp')], ['+', '*', '||', '&&', '==', '>>'], 'BinaryOp.op values')
    c.equal([n.op for n in nodes(tree, 'Assignment')], ['='] * 6 + ['+=', '*=', '>>='], 'Assignment.op values')


@case('T.R05.14')
def unary_operator_strings(c):
    tree = parse('void f(void) { x = &a; x = *p; x = -a; x = !a; a++; a--; x = sizeof a; x = sizeof(int); }')
    ops = []
    for s in statements(nodes(tree, 'FuncDef')[0]):
        node = s.rvalue if is_a(s, 'Assignment') else s
        ops.append(node.op if is_a(node, 'UnaryOp') else type(node).__name__)
    c.equal(ops, ['&', '*', '-', '!', 'p++', 'p--', 'sizeof', 'sizeof'], 'UnaryOp.op values')


@case('T.R05.15')
def structref_kinds(c):
    tree = parse('void f(void) { s.f; p->f; }')
    refs = statements(nodes(tree, 'FuncDef')[0])
    c.require(all(is_a(r, 'StructRef') for r in refs) and len(refs) == 2, 'both statements are StructRef')
    c.equal([r.type for r in refs], ['.', '->'], 'StructRef.type values')
    c.equal([(type(r.name).__name__, r.name.name) for r in refs], [('ID', 's'), ('ID', 'p')], 'StructRef bases')
    c.require(all('f' in leaf_values(r.field) for r in refs), 'field identifies member f')


@case('T.R05.16')
def constant_kinds(c):
    tree = parse('int a = 42; int b = 0x2A; unsigned c = 10u; long d = 10L; double e = 3.14; float g = 2.5f; '
                 'long double h = 1.0L; char *s = "hi"; char k = \'c\';')
    expected = {'a': ('int', '42'), 'b': ('int', '0x2A'), 'c': ('unsigned int', '10u'), 'd': ('long int', '10L'),
                'e': ('double', '3.14'), 'g': ('float', '2.5f'), 'h': ('long double', '1.0L'),
                's': ('string', '"hi"'), 'k': ('char', "'c'")}
    for name, (kind, value) in expected.items():
        init = named(tree, name).init
        c.require(is_a(init, 'Constant'), f'{name} initializer is a Constant')
        c.equal((init.type, init.value), (kind, value), f'{name} Constant type/value')


@case('T.R05.18')
def empty_parameter_and_argument_lists(c):
    tree = parse('int f(); int g(void); int h(int a); void t(void) { f(); h(1); }')
    f = named(tree, 'f').type
    c.require(is_a(f, 'FuncDecl') and f.args is None, 'f() has args None')
    c.require('args' not in [n for n, _ in f.children()], 'f FuncDecl has no args child')
    g = named(tree, 'g').type.args
    c.require(is_a(g, 'ParamList') and len(g.params) == 1 and is_a(g.params[0], 'Typename'), '(void) is a ParamList of one Typename')
    c.require(any(is_a(n, 'IdentifierType') and n.names == ['void'] for n in walk(g.params[0])), 'the Typename names void')
    c.require(is_a(named(tree, 'h').type.args, 'ParamList'), 'h has a ParamList')
    calls = nodes(nodes(tree, 'FuncDef')[0], 'FuncCall')
    c.equal([call.name.name for call in calls], ['f', 'h'], 'two calls')
    c.require(calls[0].args is None, 'f() call args None')
    args = calls[1].args
    c.require(is_a(args, 'ExprList') and len(args.exprs) == 1 and is_a(args.exprs[0], 'Constant') and args.exprs[0].value == '1',
              'h(1) args ExprList of Constant 1')


@case('T.R05.22')
def comma_operator_is_exprlist(c):
    tree = parse('int f(void) { int x; x = (1, 2, 3); return x; }')
    rvalue = nodes(tree, 'Assignment')[0].rvalue
    c.require(is_a(rvalue, 'ExprList'), 'comma expression is an ExprList')
    c.equal([(type(e).__name__, e.value) for e in rvalue.exprs], [('Constant', '1'), ('Constant', '2'), ('Constant', '3')], 'ExprList items')
    c.equal([n.op for n in nodes(tree, 'BinaryOp') if n.op == ','], [], "no BinaryOp ','")


# ----------------------------------------------------------------------------- ast-node-api

NODE_TABLE = '''
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
TABLE = {}
for _row in NODE_TABLE.strip().splitlines():
    _name, _, _rest = _row.partition(':')
    TABLE[_name] = [(w.rstrip('*'), w[len(w.rstrip('*')):]) for w in _rest.split()]
DECLARATION_NODES = list(TABLE)[:18]
OTHER_NODES = list(TABLE)[18:]


def construction_table(c, names):
    c_ast = ast()
    for cls_name in names:
        cls = getattr(c_ast, cls_name)
        fields = TABLE[cls_name]
        args, expected_children = [], set()
        for field, kind in fields:
            if kind == '*':
                value = c_ast.ID(f'{cls_name}.{field}')
                expected_children.add((field, id(value)))
            elif kind == '**':
                value = [c_ast.ID(f'{cls_name}.{field}.0'), c_ast.ID(f'{cls_name}.{field}.1')]
                expected_children |= {(f'{field}[{i}]', id(v)) for i, v in enumerate(value)}
            else:
                value = [] if field == 'align' else f'{cls_name}.{field}'
            args.append(value)
        node = cls(*args)
        for (field, _), value in zip(fields, args):
            c.require(getattr(node, field) is value, f'{cls_name}: positional argument lands on {field}')
        children = node.children()
        c.require(isinstance(children, tuple), f'{cls_name}.children() is a tuple')
        c.equal({(name, id(child)) for name, child in children}, expected_children, f'{cls_name}.children() names')
        c.equal(len(children), len(expected_children), f'{cls_name}.children() count')
        leaves = [field for field, kind in fields if not kind]
        c.require(isinstance(cls.attr_names, tuple), f'{cls_name}.attr_names is a tuple')
        c.equal(sorted(cls.attr_names), sorted(leaves), f'{cls_name}.attr_names holds exactly the leaf names')


@case('T.R05.01')
def node_base_and_coord(c):
    from pycparser.c_parser import Coord
    tree = parse('int f(int a) { return a; }')
    every = list(walk(tree))
    c.require(len(every) > 5, 'tree has nodes')
    c_ast = ast()
    for node in every:
        c.require(isinstance(node, c_ast.Node), f'{type(node).__name__} is a c_ast.Node')
        c.require(node.coord is None or isinstance(node.coord, Coord), f'{type(node).__name__}.coord is a Coord or None')
    c.require(isinstance(nodes(tree, 'FuncDef')[0].decl.coord, Coord), "FuncDef's Decl carries a Coord")


@case('T.R05.02')
def children_indexed_names(c):
    tree = parse('int a; int b; void f(void) { a = 1; b = 2; }')
    top = tree.children()
    c.require(isinstance(top, tuple) and all(isinstance(p, tuple) and len(p) == 2 for p in top), 'children() is a tuple of pairs')
    c.equal([name for name, _ in top], ['ext[0]', 'ext[1]', 'ext[2]'], 'FileAST children names')
    body = nodes(tree, 'FuncDef')[0].body
    names = [name for name, _ in body.children()]
    c.equal(names, ['block_items[0]', 'block_items[1]'], 'Compound children names')
    c.equal([n.lvalue.name for _, n in body.children()], ['a', 'b'], 'children in source order')


@case('T.R05.03')
def attr_names_class_level(c):
    c_ast = ast()
    for cls in (c_ast.ID, c_ast.BinaryOp, c_ast.Constant, c_ast.Decl):
        c.require(isinstance(cls.attr_names, tuple), f'{cls.__name__}.attr_names is a tuple')
    c.equal(c_ast.ID.attr_names, ('name',), 'ID.attr_names')
    c.equal(c_ast.BinaryOp.attr_names, ('op',), 'BinaryOp.attr_names')
    c.equal(set(c_ast.Constant.attr_names), {'type', 'value'}, 'Constant.attr_names')
    c.equal(set(c_ast.Decl.attr_names) & {'type', 'init', 'bitsize'}, set(), 'Decl.attr_names excludes child names')


@case('T.R05.04')
def show_options(c):
    tree = parse('int x = 1;', filename='s.c')

    def show(**kwargs):
        buf = io.StringIO()
        tree.show(buf=buf, **kwargs)
        return buf.getvalue()

    default = show()
    lines = [line for line in default.splitlines() if line.strip()]
    c.require(lines and 'FileAST' in lines[0], 'first line names FileAST')
    indent = [len(line) - len(line.lstrip()) for line in lines]
    c.require(max(indent) > indent[0], 'deeper nodes are more indented')
    c.require('ext[0]' not in default and 's.c:1' not in default, 'default omits node names and coords')
    c.require('x' in show(attrnames=True), 'attrnames=True includes the leaf value x')
    c.require('ext[0]' in show(nodenames=True), "nodenames=True includes 'ext[0]'")
    c.require('s.c:1' in show(showcoord=True), "showcoord=True includes 's.c:1'")


@case('T.R05.05')
def nodes_iterate_children(c):
    tree = parse('int a; int b; void f(void) { a = 1; b = 2; }')
    for node in (tree, nodes(tree, 'FuncDef')[0].body):
        yielded = list(iter(node))
        c.equal([id(n) for n in yielded], [id(n) for _, n in node.children()], f'iter({type(node).__name__}) yields children()')


@case('T.R05.06')
def mutable_nodes(c):
    tree = parse('int f(int a, int b) { return a + b; }')
    ret = nodes(tree, 'Return')[0]
    ret.expr.left.name = 'c'
    c.equal(ret.expr.left.name, 'c', 'assignment to a node attribute succeeds')
    again = nodes(parse(generate(tree)), 'Return')[0].expr
    c.require(is_a(again, 'BinaryOp') and again.op == '+', 're-parsed return is BinaryOp +')
    c.equal((again.left.name, again.right.name), ('c', 'b'), 'rewritten operand survives generation')


@case('T.R05.07')
def programmatic_ast_to_generator(c):
    c_ast = ast()
    tree = c_ast.FileAST([c_ast.Decl('x', [], [], [], [], c_ast.TypeDecl('x', [], [], c_ast.IdentifierType(['int'])),
                                     c_ast.Constant('int', '5'), None)])
    c.equal(generate(tree).strip(), 'int x = 5;', 'generated text')


@case('T.R05.08')
def json_serialization(c):
    tree = parse('int x = 1;', filename='j.c')
    data = to_json(tree)
    text = json.dumps(data)
    c.equal(data['_nodetype'], 'FileAST', 'root _nodetype')
    decls = [d for d in json_nodes(json.loads(text)) if d['_nodetype'] == 'Decl']
    c.equal(len(decls), 1, 'one Decl dict')
    c.equal(decls[0].get('name'), 'x', 'Decl name')
    c.require(re.fullmatch(r'j\.c:1(:\d+)?', str(decls[0].get('coord'))), f"Decl coord is 'j.c:1[:column]': {decls[0].get('coord')!r}")


@case('T.R05.09')
def node_class_inventory(c):
    c_ast = ast()
    c.equal(len(TABLE), 49, 'instruction lists 49 node classes')
    for name in TABLE:
        cls = getattr(c_ast, name, None)
        c.require(isinstance(cls, type) and issubclass(cls, c_ast.Node), f'c_ast.{name} subclasses Node')
        c.require('__slots__' in vars(cls), f'c_ast.{name} defines __slots__')


@case('T.R05.10')
def constructors_keyword_and_positional(c):
    c_ast = ast()
    c.equal(c_ast.IdentifierType(names=['int']).names, c_ast.IdentifierType(['int']).names, 'IdentifierType kw/pos')
    t = c_ast.TypeDecl('x', [], [], c_ast.IdentifierType(['int']))
    values = dict(name='x', quals=['const'], align=[], storage=['static'], funcspec=['inline'], type=t, init=None, bitsize=None)
    by_keyword = c_ast.Decl(**values)
    by_position = c_ast.Decl(*values.values())
    for field, value in values.items():
        c.require(getattr(by_keyword, field) is value, f'Decl keyword {field}')
        c.require(getattr(by_position, field) is value, f'Decl positional {field}')
    co = named(parse('int x;'), 'x').coord
    c.require(c_ast.ID('x', coord=co).coord is co, 'coord= sets node.coord')
    c.raises(TypeError, lambda: c_ast.ID('x', co), 'coord passed positionally')


@case('T.R05.11')
def declaration_node_attributes(c):
    construction_table(c, DECLARATION_NODES)


@case('T.R05.12')
def statement_expression_node_attributes(c):
    construction_table(c, OTHER_NODES)
    c_ast = ast()
    for cls in (c_ast.Goto, c_ast.Label, c_ast.ID):
        c.require('name' in cls.attr_names, f'{cls.__name__}.name is a leaf')
    for cls in (c_ast.BinaryOp, c_ast.UnaryOp, c_ast.Assignment):
        c.require('op' in cls.attr_names, f'{cls.__name__}.op is a leaf')
    c.require('type' in c_ast.StructRef.attr_names and 'string' in c_ast.Pragma.attr_names, 'StructRef.type and Pragma.string are leaves')


@case('T.integration.json-export')
def json_export_integration(c):
    tree = parse('int a;\n#line 50 "gen.c"\n_Pragma("pack(push, 1)")\nstruct S { int v; } s;\nint f(void) { return s.v; }',
                 filename='j.c')
    data = json.loads(json.dumps(to_json(tree)))
    c.equal(data['_nodetype'], 'FileAST', 'root _nodetype')
    c.require(all(name in data for name, _ in tree.children()), 'root entries follow children() names')
    c.equal(sum(1 for key in data if key.startswith('ext[')), len(tree.children()), 'one entry per ext child')
    first = data[tree.children()[0][0]]
    c.require(first['_nodetype'] == 'Decl' and first['name'] == 'a', 'first item is Decl a')
    c.require(re.fullmatch(r'j\.c:1(:\d+)?', str(first['coord'])), f"a coord is 'j.c:1': {first['coord']!r}")
    later = [d for name, _ in tree.children()[1:] for d in json_nodes(data[name]) if d['coord'] is not None]
    c.require(later, 'nodes after the directive carry coords')
    c.require(all(d['coord'].startswith('gen.c:') for d in later), f"post-directive coords are 'gen.c:<line>': {[d['coord'] for d in later][:5]}")
    pragmas = [d for d in json_nodes(data) if d['_nodetype'] == 'Pragma']
    c.equal(len(pragmas), 1, 'one Pragma')
    string = pragmas[0].get('string')
    c.require(isinstance(string, dict) and string.get('_nodetype') == 'Constant', 'Pragma.string serializes as a Constant dict')
    c.equal(string.get('value'), '"pack(push, 1)"', 'Pragma Constant value')


@case('T.integration.build-from-scratch')
def build_from_scratch(c):
    c_ast = ast()

    def param(name):
        return c_ast.Decl(name, [], [], [], [], type=c_ast.TypeDecl(name, [], [], c_ast.IdentifierType(names=['int'])),
                          init=None, bitsize=None, coord=None)

    func = c_ast.FuncDecl(c_ast.ParamList([param('a'), param('b')]), type=c_ast.TypeDecl('add', [], [], c_ast.IdentifierType(['int'])))
    tree = c_ast.FuncDef(c_ast.Decl('add', [], [], [], [], func, None, None), None,
                         body=c_ast.Compound([c_ast.Return(c_ast.BinaryOp('+', c_ast.ID('a'), c_ast.ID(name='b')))]), coord=None)
    text = generate(tree)
    again = parse(text)
    defs = nodes(again, 'FuncDef')
    c.equal(len(defs), 1, f'generated text holds one function: {text!r}')
    c.equal(difference(tree, defs[0]), None, f're-parsed function equals the constructed one\n{text}')


# ----------------------------------------------------------------------------- ast-shape-conventions

@case('T.R05.17')
def unsized_array_dims(c):
    tree = parse('extern char buf[]; struct M { int n; char data[]; }; int k[4];')
    for name in ('buf', 'data'):
        t = named(tree, name).type
        c.require(is_a(t, 'ArrayDecl') and t.dim is None, f'{name} ArrayDecl dim is None')
    k = named(tree, 'k').type
    c.require(is_a(k, 'ArrayDecl') and is_a(k.dim, 'Constant') and k.dim.value == '4', 'k dim Constant 4')


@case('T.R05.19')
def struct_body_states(c):
    tree = parse('struct A; struct B {}; struct C { int x : 4; int y; }; union U;')
    found = {n.name: n for n in nodes(tree, 'Struct') + nodes(tree, 'Union')}
    c.require(set(found) >= {'A', 'B', 'C', 'U'}, f'all four aggregates found: {sorted(found)}')
    c.require(found['A'].decls is None, 'forward struct A has decls None')
    c.require(found['B'].decls == [] and isinstance(found['B'].decls, list), 'empty struct B has decls []')
    members = found['C'].decls
    c.require(isinstance(members, list) and [m.name for m in members] == ['x', 'y'], 'struct C has members x, y')
    c.require(is_a(members[0].bitsize, 'Constant') and members[0].bitsize.value == '4', 'x bitsize 4')
    c.require(members[1].bitsize is None, 'y bitsize None')
    c.require(is_a(found['U'], 'Union') and found['U'].decls is None, 'forward union U has decls None')


@case('T.R05.20')
def typedecl_interposition(c):
    tree = parse('int x; struct S { int a; }; struct S s; typedef struct rec { int v; } rec_t; enum E { A }; struct F; '
                 'struct G { struct { int q; }; }; int n = sizeof(struct { int z; }); struct S *ps;')
    x = named(tree, 'x').type
    c.require(is_a(x, 'TypeDecl') and x.declname == 'x' and is_a(x.type, 'IdentifierType'), 'x: TypeDecl over IdentifierType')
    s = named(tree, 's').type
    c.require(is_a(s, 'TypeDecl') and s.declname == 's' and is_a(s.type, 'Struct'), 's: TypeDecl over Struct')
    rec = named(tree, 'rec_t', 'Typedef').type
    c.require(is_a(rec, 'TypeDecl') and rec.declname == 'rec_t' and is_a(rec.type, 'Struct'), 'rec_t: TypeDecl over Struct')
    bare = [d for d in nodes(tree, 'Decl') if d.name is None]
    shapes = {(type(d.type).__name__, d.type.name, d.type.decls is None if hasattr(d.type, 'decls') else None) for d in bare
              if is_a(d.type, 'Struct') or is_a(d.type, 'Enum')}
    c.require(('Struct', 'S', False) in shapes, f'standalone struct S is a nameless Decl over the Struct: {shapes}')
    c.require(('Enum', 'E', None) in shapes, 'standalone enum E is a nameless Decl over the Enum')
    c.require(('Struct', 'F', True) in shapes, 'forward struct F is a nameless Decl over the Struct')
    g = [n for n in nodes(tree, 'Struct') if n.name == 'G' and n.decls]
    c.require(len(g) == 1 and g[0].decls[0].name is None and is_a(g[0].decls[0].type, 'Struct'), "G's anonymous member is a Decl over the Struct")
    operand = named(tree, 'n').init
    c.require(is_a(operand, 'UnaryOp') and operand.op == 'sizeof' and is_a(operand.expr, 'Typename'), 'sizeof operand is a Typename')
    c.require(is_a(operand.expr.type, 'TypeDecl') and is_a(operand.expr.type.type, 'Struct'), 'Typename: TypeDecl over Struct')
    ps = named(tree, 'ps').type
    c.require(is_a(ps, 'PtrDecl') and is_a(ps.type, 'TypeDecl') and is_a(ps.type.type, 'Struct'), 'ps: PtrDecl -> TypeDecl -> Struct')


@case('T.R05.21')
def string_list_specifiers(c):
    tree = parse('static const int a = 1; extern volatile int b; static inline int f(void) { return 0; } _Noreturn void g(void);')
    a, b, g = named(tree, 'a'), named(tree, 'b'), named(tree, 'g')
    f = nodes(tree, 'FuncDef')[0].decl
    for decl in (a, b, f, g):
        for field in ('quals', 'storage', 'funcspec'):
            value = getattr(decl, field)
            c.require(isinstance(value, list) and all(isinstance(v, str) for v in value), f'{decl.name}.{field} is a list of str')
    c.require(a.storage == ['static'] and 'const' in a.quals, 'a: static, const')
    c.require(b.storage == ['extern'] and 'volatile' in b.quals, 'b: extern, volatile')
    c.require(f.storage == ['static'] and f.funcspec == ['inline'], 'f: static inline')
    c.equal(g.funcspec, ['_Noreturn'], 'g funcspec')


@case('T.R05.23')
def pragma_string_forms(c):
    from pycparser import c_ast
    first = nodes(parse('_Pragma("pack(push, 1)")\nint x;'), 'Pragma')
    c.equal(len(first), 1, '_Pragma operator yields one Pragma')
    c.require(isinstance(first[0].string, c_ast.Constant), 'operator form string is a Constant')
    c.equal(first[0].string.value, '"pack(push, 1)"', 'payload keeps its quotes')
    second = nodes(parse('#pragma once\nint y;'), 'Pragma')
    c.equal(len(second), 1, '#pragma directive yields one Pragma')
    c.require(isinstance(second[0].string, str) and 'once' in second[0].string, 'directive form string is a str with once')


@case('T.R05.24')
def alignas_nodes(c):
    tree = parse('_Alignas(16) int a; int b;')
    a, b = named(tree, 'a'), named(tree, 'b')
    c.require(isinstance(a.align, list) and len(a.align) == 1 and is_a(a.align[0], 'Alignas'), 'a.align holds one Alignas')
    c.require(is_a(a.align[0].alignment, 'Constant') and a.align[0].alignment.value == '16', 'alignment Constant 16')
    c.equal(b.align, [], 'b.align is empty')
    c.require('_Alignas(16)' in generate(tree), 'generator emits _Alignas(16)')


@case('T.R05.25')
def source_order_words_and_atomic(c):
    tree = parse('unsigned long long int a; long unsigned b; volatile const int e; int _Atomic c; _Atomic(int) d;')
    c.equal(named(tree, 'a').type.type.names, ['unsigned', 'long', 'long', 'int'], 'a names')
    c.equal(named(tree, 'b').type.type.names, ['long', 'unsigned'], 'b names')
    c.equal(named(tree, 'e').quals, ['volatile', 'const'], 'e Decl.quals in source order')
    for name in 'cd':
        decl = named(tree, name)
        c.require('_Atomic' in list(decl.quals) + list(decl.type.quals), f"'_Atomic' in a quals list of {name}")


@case('T.R05.26')
def qualifier_placement(c):
    source = 'const int a; int const b; _Atomic int c; int _Atomic flag; const _Atomic(int) x;'
    tree = parse(source)
    d = {name: named(tree, name) for name in ('a', 'b', 'c', 'flag', 'x')}
    c.require('const' in d['a'].quals, 'a Decl.quals has const')
    c.require('const' in d['x'].quals and '_Atomic' in d['x'].quals, 'x Decl.quals has const and _Atomic')
    for name, qual in (('a', 'const'), ('b', 'const'), ('c', '_Atomic'), ('flag', '_Atomic'), ('x', '_Atomic')):
        c.require(qual in d[name].type.quals, f'{name} TypeDecl.quals has {qual}')
    again = parse(generate(tree))
    c.require('_Atomic' in named(again, 'flag').type.quals, 'flag keeps _Atomic on TypeDecl.quals after a roundtrip')


@case('T.R05.27')
def pointer_and_array_leading_qualifiers(c):
    tree = parse('const volatile int *p; const volatile int a[3];')
    p = named(tree, 'p').type
    c.require(is_a(p, 'PtrDecl'), 'p is a PtrDecl')
    c.require(not {'const', 'volatile'} & set(p.quals), 'PtrDecl.quals has neither const nor volatile')
    c.require({'const', 'volatile'} <= set(p.type.quals), 'pointed-to TypeDecl.quals has both')
    a = named(tree, 'a').type
    c.require(is_a(a, 'ArrayDecl') and {'const', 'volatile'} <= set(a.type.quals), 'element TypeDecl.quals has both')
    c.require(not {'const', 'volatile'} & set(a.dim_quals or []), 'ArrayDecl.dim_quals has neither')


# ----------------------------------------------------------------------------- lexer-coords

@case('T.R04.10')
def line_directive_updates_coord(c):
    tree = parse('int a;\n#line 100 "gen.c"\nint b;\nint c;', filename='orig.c')
    got = [(named(tree, n).coord.file, named(tree, n).coord.line) for n in 'abc']
    c.equal(got, [('orig.c', 1), ('gen.c', 100), ('gen.c', 101)], 'coords around #line')


@case('T.R04.13')
def dollar_identifiers(c):
    tree = parse('int a$b; int $x = 1; int y$;')
    c.equal([d.name for d in nodes(tree, 'Decl')], ['a$b', '$x', 'y$'], 'Decl names')
    c.equal([(t.type, t.value) for t in lex('a$b $x')], [('ID', 'a$b'), ('ID', '$x')], 'lexer yields two ID tokens')


@case('T.R04.14')
def coord_attributes(c):
    coord = named(parse('int x;', filename='c.c'), 'x').coord
    c.equal((coord.file, coord.line), ('c.c', 1), 'coord file and line')
    text = str(coord)
    if coord.column is None:
        c.equal(text, 'c.c:1', 'str(coord) without a column')
    elif coord.column == 0:
        c.require(text in ('c.c:1', 'c.c:1:0'), f'str(coord) with column 0: {text!r}')
    else:
        c.equal(text, f'c.c:1:{coord.column}', 'str(coord) with a column')


@case('T.R07.01')
def lexer_token_stream(c):
    from pycparser.c_lexer import Token
    tokens = lex('int x;\nx = 42;')
    c.require(tokens, 'tokens produced')
    for t in tokens:
        c.require(isinstance(t, Token) and all(hasattr(t, a) for a in ('type', 'value', 'lineno', 'column')),
                  f'{t!r} is a Token with type, value, lineno, column')
    c.equal([(t.type, t.value) for t in tokens[:2]], [('INT', 'int'), ('ID', 'x')], 'stream starts INT int, ID x')
    numbers = [t for t in tokens if t.type == 'INT_CONST_DEC']
    c.equal([(t.value, t.lineno) for t in numbers], [('42', 2)], 'INT_CONST_DEC 42 on line 2')


@case('T.R07.02')
def token_type_names(c):
    source = ('int void return if while for struct enum typedef switch case default sizeof static extern const volatile '
              '+ - * / % && || == != <= >= << >> -> ++ -- ... 42 0x2A 052 0b101 3.14 0x1.8p1 "s" \'c\' L"w" L\'w\' name')
    expected = ('INT VOID RETURN IF WHILE FOR STRUCT ENUM TYPEDEF SWITCH CASE DEFAULT SIZEOF STATIC EXTERN CONST VOLATILE '
                'PLUS MINUS TIMES DIVIDE MOD LAND LOR EQ NE LE GE LSHIFT RSHIFT ARROW PLUSPLUS MINUSMINUS ELLIPSIS '
                'INT_CONST_DEC INT_CONST_HEX INT_CONST_OCT INT_CONST_BIN FLOAT_CONST HEX_FLOAT_CONST STRING_LITERAL '
                'CHAR_CONST WSTRING_LITERAL WCHAR_CONST ID').split()
    c.equal([t.type for t in lex(source)], expected, 'token types in order')


@case('T.R07.03')
def type_lookup_hook(c):
    calls = []
    tokens = lex('T x; U y;', lookup=lambda name: name == 'T', calls=calls)
    c.equal([(t.type, t.value) for t in tokens if t.type in ('ID', 'TYPEID')],
            [('TYPEID', 'T'), ('ID', 'x'), ('ID', 'U'), ('ID', 'y')], 'identifier token types')
    c.require({'T', 'x', 'U', 'y'} <= set(calls), f'lookup called for every identifier: {calls}')


@case('T.integration.typedef-scope-lexer')
def typedef_scope_and_lexer(c):
    source = 'typedef int T; void f(void) { T * x; { int T = 0; T * 2; } T * y; }'
    tree = parse(source)
    for name in 'xy':
        c.require(is_a(named(tree, name).type, 'PtrDecl'), f'{name} is a PtrDecl Decl')
    inner = [s for s in statements(nodes(tree, 'FuncDef')[0]) if is_a(s, 'Compound')]
    c.equal(len(inner), 1, 'inner block')
    mul = [n for n in nodes(inner[0], 'BinaryOp') if n.op == '*']
    c.require(len(mul) == 1 and is_a(mul[0].left, 'ID') and mul[0].left.name == 'T', "'T * 2;' is BinaryOp '*' in the inner block")
    roundtrip(c, tree, 'typedef scope')
    types = [t.type for t in lex(source, lookup=lambda name: name == 'T') if t.value == 'T']
    c.equal(types, ['TYPEID'] * 5, 'scope-free lexer labels every T as TYPEID')


# ----------------------------------------------------------------------------- visitor-generator

def recording_visitor(handle_call=False, recurse_call=False):
    from pycparser.c_ast import NodeVisitor

    class Recorder(NodeVisitor):
        def __init__(self):
            self.seen = []

        def visit_ID(self, node):
            self.seen.append(node.name)

    if handle_call:
        def visit_FuncCall(self, node):
            self.seen.append('call')
            if recurse_call:
                self.generic_visit(node)
        Recorder.visit_FuncCall = visit_FuncCall
    return Recorder()


@case('T.R06.01')
def visitor_dispatch(c):
    visitor = recording_visitor()
    visitor.visit(parse('int f(int a) { return a + g(a); }'))
    c.equal(visitor.seen, ['a', 'g', 'a'], 'IDs reached through generic_visit in children() order')


@case('T.R06.02')
def handled_nodes_not_recursed(c):
    tree = parse('void f(void) { g(a); b; }')
    a = recording_visitor(handle_call=True)
    a.visit(tree)
    c.equal(a.seen, ['call', 'b'], 'visit_FuncCall without generic_visit stops recursion')
    b = recording_visitor(handle_call=True, recurse_call=True)
    b.visit(tree)
    c.equal(b.seen, ['call', 'g', 'a', 'b'], 'explicit generic_visit recurses')


@case('T.R08.01')
def generator_formatting(c):
    from pycparser import c_ast
    text = generate(parse('int x=5;int f(void){x=x+1;return x;}'))
    c.require(isinstance(text, str), 'visit returns a str')
    c.require('int x = 5;' in text, f"'int x = 5;' in output:\n{text}")
    c.require('x = x + 1;' in text, f"'x = x + 1;' in output:\n{text}")
    c.equal(generate(c_ast.ID('x')), 'x', 'visiting an ID')


@case('T.R08.02')
def default_full_parenthesization(c):
    text = generate(parse('void f(void) { x = p * q * r; y = a + b * c; }'))
    c.require('x = (p * q) * r;' in text, f"'x = (p * q) * r;' in output:\n{text}")
    c.require('y = a + (b * c);' in text, f"'y = a + (b * c);' in output:\n{text}")


@case('T.R08.03')
def reduced_parentheses(c):
    text = generate(parse('void f(void) { x = p * q * r; y = a + b * c; z = (a + b) * c; w = a - (b - c); }'), True)
    for expected in ('x = p * q * r;', 'y = a + b * c;', 'z = (a + b) * c;', 'w = a - (b - c);'):
        c.require(expected in text, f'{expected!r} in output:\n{text}')


@case('T.R08.04')
def roundtrip_both_modes(c):
    tree = parse('void f(void) { y = - -x; y = a - (b - c); y = (a = b) + 1; y = (char)(a + b); y = a ? b : (c ? d : e); '
                 'y = *p++; y = (*p)++; y = sizeof(int) * 2; y = f((a, b)); }')
    original = statements(nodes(tree, 'FuncDef')[0])
    c.equal(len(original), 9, 'nine statements')
    for mode in (False, True):
        text = generate(tree, mode)
        again = statements(nodes(parse(text), 'FuncDef')[0])
        c.equal(len(again), 9, f'reduce_parentheses={mode}: statement count')
        for before, after in zip(original, again):
            c.equal(difference(before, after), None, f'reduce_parentheses={mode}: statement re-parses equal\n{text}')


@case('T.integration.parse-generate-reparse')
def full_roundtrip(c):
    source = '''
typedef unsigned long long int u64;
struct rec { unsigned flag : 1; union { int i; float f; }; char data[]; };
enum color { RED, GREEN = 2, BLUE };
_Static_assert(sizeof(int) == 4, "int size");
_Alignas(16) int aligned;
_Noreturn void die(void);
_Atomic int counter;
const _Atomic(int) shared;
int (*handler)(int, double);
int grid[3][4];
const volatile int *cv;
struct point { int x, y; };
struct point origin = { .y = 2, .x = 1 };
int table[4] = { [2] = 5, 6 };
int *lit = (int []){ 1, 2 };
int kr(a, b) int a; char b; { return a + b; }
void vla(int n, const int a[const n]) { int v[n]; v[0] = a[0]; }
int all(int n)
{
    int i;
    u64 total = 0;
    if (n) i = 1; else i = 2;
    for (i = 0; i < n; i++) continue;
    while (n) break;
    do n--; while (n);
    switch (n) { case 1: n = 2; break; default: n = 3; }
    total = (total + 1) * 2;
    n = - -n;
    n = n - (n - 1);
    n = n ? n : (n ? 1 : 2);
    goto end;
end:
    return n;
}
'''
    tree = parse(source)
    c.require(len(tree.ext) >= 18, 'translation unit parsed')
    roundtrip(c, tree, 'reduce_parentheses=False', False)
    roundtrip(c, tree, 'reduce_parentheses=True', True)


@case('T.integration.visitor-rewrite-generate')
def visitor_rewrite(c):
    from pycparser.c_ast import NodeVisitor

    class Rewrite(NodeVisitor):
        def visit_ID(self, node):
            if node.name == 'a':
                node.name = 'b'

        def visit_BinaryOp(self, node):
            if node.op == '*':
                node.op = '+'
            self.generic_visit(node)

    tree = parse('int f(int a, int b) { int t = a * b; return t + a; }')
    Rewrite().visit(tree)
    again = parse(generate(tree))
    f = nodes(again, 'FuncDef')[0]
    init = named(f, 't').init
    c.require(is_a(init, 'BinaryOp') and init.op == '+', "t's init is BinaryOp '+'")
    c.equal((init.left.name, init.right.name), ('b', 'b'), "t's init operands")
    ret = nodes(f, 'Return')[0].expr
    c.require(is_a(ret, 'BinaryOp') and ret.op == '+', "return is BinaryOp '+'")
    c.equal((ret.left.name, ret.right.name), ('t', 'b'), 'return operands')
    c.equal([p.name for p in f.decl.type.args.params], ['a', 'b'], 'parameter Decls keep their names')


# ----------------------------------------------------------------------------- parse-errors

@case('T.R09.01')
def structural_parse_errors(c):
    from pycparser.c_parser import ParseError
    for source in ('int x = 1\nint y;', 'int f(void) {', 'int x; )'):
        error = c.raises(ParseError, lambda: parse(source, filename='bad.c'), f'{source!r} raises ParseError')
        c.require(re.match(r'bad\.c:\d+: \S', str(error)), f"{source!r}: message starts 'bad.c:<line>: ': {error}")
    error = c.raises(ParseError, lambda: parse('int x; )', filename='bad.c'), 'stray token raises ParseError')
    c.require(str(error).startswith('bad.c:1: '), f"stray token reported at 'bad.c:1: ': {error}")


@case('T.R09.02')
def invalid_specifier_combinations(c):
    from pycparser.c_parser import ParseError
    for source in ('int int x;', 'char double y;', 'void int z;'):
        c.raises(ParseError, lambda: parse(source), f'{source!r} raises ParseError')
    c.equal(named(parse('unsigned long long int w;'), 'w').type.type.names, ['unsigned', 'long', 'long', 'int'], 'legal w')
    c.equal(named(parse('long double d;'), 'd').type.type.names, ['long', 'double'], 'legal d')
