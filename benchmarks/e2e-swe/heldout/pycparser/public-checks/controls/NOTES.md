# pycparser public checks: control notes

Sources used: `.benchmarks/E2E-SWE/tasks/pycparser/instruction.md`, `atoms.json`, `obligations.json`,
`public-checks.plan.json`. The task's tests/, solution/ and environment/ directories, `grade.json`
and upstream pycparser/ply source were not read. The reference is a hand-written, stdlib-only
recursive-descent parser covering the snippets the cases use. It validates the checker and never
certifies a candidate.

## Deviations from the plan

All 53 planned defects are kept with the planned suites and `expected_failed_ids`, unchanged. Only
some mutation sentences were reworded so that each matches the edit that is actually applied:

- `setup_requires_network`: setup.sh installs with build isolation from an explicit index URL.
  PIP_NO_INDEX=1 and network none make the backend fetch fail.
- `typedef_shadow_ignored`: the sentence now says why the snippet fails. Inside the block, `T`
  stays a type name, so `T = T + 1;` is a syntax error. (`int T = 3;` itself still parses, because a
  type name after a base type is read as the declarator.)
- `frozen_nodes`: `__setattr__` raises only for an attribute that already holds a non-None value.
  Freezing every assignment would also break the reference parser, which links declarator chains
  after construction. The case would then fail for an unrelated reason.
- `generator_requires_coord`: the generator reads `node.coord.line` and does not format it.
- `missing_node_classes`: only `EmptyStatement` and `Alignas` are removed. The plan's extra
  "other classes omit __slots__" was dropped because the two missing classes already fail both
  targeted ids.
- `coord_positional`: a trailing positional coord is accepted, while keyword `coord=` still
  works, and Decl's storage/align order is swapped.
- `unspaced_operators`: the initializer `=` is also unspaced. This matters for R08.01's
  `int x = 5;`.
- `reduce_mode_drops_all_parens`: binary operands are never wrapped in reduce mode. Assignment and
  ternary operands are still wrapped.
- `unary_minus_merged`: the sentence now names the actual edit, which is that a unary operand is
  not parenthesized.

## Points asserted although an atom lists a related gap

- R04.10: `#line 100 "gen.c"` makes the next source line 100 and the line after it 101. The
  instruction says `#line` updates file/line in `Coord`, and the number given is the next line's
  number under C99 6.10.4. The atom's expected value states the same.

## Instruction gaps deliberately not asserted

- How `int x, *p;` is grouped in `FileAST.ext`. Decls are found by walking `children()`.
- The K&R identifier-list representation in `FuncDecl.args`, and the designator node class inside
  `NamedInitializer.name`. Only the designated name or index value is checked, among leaf values.
- The `show()` line format, the indent width, and whether attribute values appear by default. The
  checks cover the FileAST first line, deeper indentation, and the presence or absence of
  `x` / `ext[0]` / `s.c:1`.
- The order inside multi-name `attr_names`, which is compared as a set. Whether `align` Alignas
  nodes appear in `children()`: construction tests pass `[]` for align.
- Prefix `++`/`--` op spelling and the `sizeof(type)` node shape beyond `op == 'sizeof'`.
  `Constant.type` for combined suffixes (UL/LL/ULL) and for wide literals.
- Whether the parser sets `Coord.column`, its base, and the `Coord` constructor. `str(coord)` is
  checked conditionally on `column`, and both forms are accepted for column 0. No case constructs
  `Coord` directly.
- `ParseError` base class and description wording, and the line reported for errors at end of
  input. The checks require only the `bad.c:<digits>: <text>` prefix, plus exact `bad.c:1: ` for
  the single-line stray-token case.
- Whether a trailing qualifier or a bare leading `_Atomic` also lands in `Decl.quals`, and
  whether pointer/array leading qualifiers also appear in `Decl.quals`. `TypeDecl.align` contents.
- Whether an empty `;` adds an `ext` entry, where `_Pragma` may appear beyond file scope, whether
  the `_Static_assert` message is optional, and the exact text of `#pragma` directives (only
  `'once' in string` is checked).
- Lexer column base, when brace callbacks fire, the `error_func` signature, and the names of
  assignment and punctuation token types.
- The distribution name. It is resolved with `importlib.metadata.packages_distributions()`,
  falling back to `pycparser`. Missing metadata is not a failure, and only non-extra
  `Requires-Dist` entries count.
- Whether the candidate must author `setup.sh`, and whether build isolation is disabled. R02.02
  requires only a successful offline install (PIP_NO_INDEX=1) and an import that resolves into the
  project copy.
- Whether `__slots__` must remove `__dict__` across the hierarchy. Only a class-level `__slots__`
  is required. The "~50 node types" count is approximate; the 49 enumerated classes are checked.

## Reference ceilings (ponytail)

The reference does not concatenate adjacent string literals and does not support `_Atomic(T *)`.
It does not enter function parameters into the typedef scope, emits a multi-declaration
`for`-init only once, and does not brace a dangling `if` without `else` on generation. None of
these appear in the cases.
