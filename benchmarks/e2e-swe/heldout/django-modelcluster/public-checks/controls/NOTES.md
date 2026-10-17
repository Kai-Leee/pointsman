# django-modelcluster public-check controls: notes and deviations

Sources: `instruction.md` only, plus the obligations/atoms test specs and `public-checks.plan.json`.
Nothing under the task's `tests/`, `solution/` or `environment/` was read. Django 5.2 and taggit 6.1
source in the pinned image was read for API details (prefetch protocol, taggit manager internals).

## Execution model

- Every case runs its body in a fresh interpreter of the candidate venv (`c.run_python`), with
  `support/heldout_checker_app/settings.py` (in-memory SQLite, `USE_TZ=True`, `TIME_ZONE="Asia/Seoul"`,
  per-process `MEDIA_ROOT`) and `migrate --run-syncdb`. The child reports passed assertions plus the
  first failure; the wrapper replays them through `c`, so assertion counts are real.
- Checker models are split into apps that load only when a case needs them: `heldout_checker_app`
  (core, always), `heldout_checker_tags` (taggit cases and T.R08.16), `heldout_checker_probe` (T.R03.02),
  `heldout_checker_default` (T.R04.01). A broken taggit integration or a missing `on_delete` default
  therefore fails only its own cases, not every suite.
- `modelcluster` is **not** in `INSTALLED_APPS` (instruction silent; plan default). No case asserts
  either way.

## Case-design deviations from the plan / test specs

- T.R04.01: the omitted-`on_delete` ParentalKey lives in its own app (`DefaultBand`/`DefaultMember`)
  instead of on the shared `BandMember`, so a missing default cannot break other cases. Child rows are
  created through the ORM so the case does not depend on assignment/commit.
- T.R03.02: the probe subclasses define `_cache`, `_items`, `_parent`, `_field` as plain methods (not
  data descriptors). Storing instance data under those names stays legal; only code that reads or calls
  a class-level private name of that spelling collides. The manager subclass is installed by assigning
  `__class__` on the manager returned by `band.members` (how tests install one is unspecified).
- T.R06.08: no positive "same unsaved instance matches" control (instruction only says distinct unsaved
  instances differ). MTI is checked in both directions with Visit/Review (FK to Place) and Diner (FK to
  Restaurant), plus a different-Place negative control.
- T.R06.11: datetimes are aware in the current zone (Asia/Seoul) so `date`/`time`/`hour` agree whether a
  candidate derives them in the current zone or the value's own zone (gap: the zone is unspecified).
- T.R06.18 / T.R09.04 / tags-and-prefetch: only "count does not grow with parents" and "fewer than
  without prefetch" are asserted, never exact counts. `FakeQuerySet.prefetch_related` may return a new
  queryset, itself, or None; the case iterates whichever is returned.
- T.R07.08: the serialize=False parental m2m and serialize=False ParentalKey relation live on a
  separate `Studio` cluster rather than `Band`, so `Band` keeps exactly `members`/`albums` (needed by the
  exclude_formsets case). A visible `engineers` relation is the control.
- T.R07.10: uses `Tour`/`TourStop`/`Company` (dedicated FKs per on_delete variant); referenced rows are
  removed with `QuerySet.delete()` after serializing.
- T.R08.02: besides `fields=['name']` (where the FK is absent anyway), an `exclude=[]` factory is checked,
  which is what makes automatic FK exclusion observable.
- T.R08.06 / clusterform-nested-save: nested prefixes are read from an unbound form
  (`form.formsets['songs'].prefix`) instead of assuming a scheme (gap).
- T.R08.13: member forms use fields `name` + `age`, so a form with a blank required name but a filled age
  counts as changed (a blank-only extra form is legitimately skipped). Uniqueness errors are asserted
  only as "reported somewhere in the formset" (message and placement are gaps). Distinct names act as a
  control for both unique_together and UniqueConstraint.
- integration.json-round-trip: m2m pk lists are sorted before comparing (database read order is not
  specified), and it also asserts the inherited `name` survives a save of the rebuilt instance.
- integration.queryset-db-parity: battery avoids case-sensitive LIKE lookups (SQLite `contains`/
  `startswith` are case-insensitive) and the documented `in`-with-None divergence.

## Defective-control deviations from the plan

All 88 planned defect names are kept, one per plan row, with the plan's expected ids. Changes
in how a defect is realised:

- `setup_uses_index`: as planned, the mutation would *succeed* offline, because the harness exports
  `PIP_NO_INDEX=1` and django-taggit is already satisfied. It now appends
  `pip install --force-reinstall django-taggit`, which needs a download and fails offline.
- `private_name_collision`: realised as `all()` delegating to a private method `_items`. A data
  attribute `self._items` cannot collide with a subclass method, so the plan's wording would not fail.
- `results_reordered`: results are stored reversed, not sorted by pk. Sorting unsaved instances by a
  None pk would raise a TypeError rather than reorder.
- `count_reads_db`: `count()` returns the whole child table's row count (0 before save). That is
  equivalent for the unsaved parent used in T.R04.06.
- `e001_on_unresolved`: E001 is emitted for anything that is not a resolved ClusterableModel class,
  including a string target. The reference's E001 hint no longer interpolates the target, so this
  mutation raises the E001 error instead of crashing.
- `m2m_manager_no_model`: the attribute is renamed to `target_model`.
- `flat_multi_allowed`: yields the first field's values instead of raising.
- `prefetch_noop`: also renames the managers' `get_prefetch_querysets`, matching the plan's
  "child relation descriptors expose no prefetch support".
- `strict_fks_ignored`: the base object is always deserialized with `strict_fks=False`.
- `commit_false_defers_parental`: parental m2m and tag fields are applied only in the deferred
  `save_m2m()`, so with `commit=True` they are never applied either. T.R08.16 fails on its first step.
- `inherited_relations_skipped`: implemented as "only relations whose ParentalKey targets the form's
  model itself".
- `child_commit_false_writes`: in T.integration.clusterform-nested-save the premature commit reaches
  the nested songs relation of a still-unsaved album and raises IntegrityError. The case fails on that
  error rather than on the DB-unchanged assertion, which it reaches only in T.R08.03.
- `transient_commit_false_saves`: `save()` saves every returned instance. In T.R08.01 that raises a
  NOT NULL IntegrityError, which fails the case.

## Instruction ambiguities deliberately not asserted

Return type of `all()` on a saved untouched parent; equality of distinct unsaved instances in `add()`;
whether commit() writes in-memory edits of stored children (only membership is checked); exact prefetch
query counts; whether `FakeQuerySet.prefetch_related` acts in place; `qs.all() is qs` (only equivalence
is checked); FK key name in no-argument `values()` (name or attname accepted); `values_list()` with no
fields; which duplicate `distinct()` keeps; None placement under descending `order_by`; `first()/last()` on
empty querysets; behaviour on coercion failure; XOR over more than two operands; chained comparisons after
transforms; whether `serializable_data()` already holds UTC strings (only `to_json()` output is checked);
microsecond ISO formatting; `check_fks=False` and PROTECT; the key type of copy maps (relation object or
accessor string both accepted); the meaning of `copy_cluster(exclude_fields=...)`; the error for a
non-ParentalKey relation in `copy_child_relation`; `formset_name`'s effect (only acceptance is checked);
nested prefix scheme; uniqueness error text and placement; exact `as_p()` markup (only parent-before-child
order and SafeString); when a plain TaggableManager is applied under `save(commit=False)`; whether Tag rows
may be created during `add()` (only tagged-item rows are counted); name of the taggit extra and whether
django-taggit may also appear unconditionally (only "some requirement conditioned on an extra" is
asserted); whether `setup.sh` must be authored by the candidate (absence is tolerated by the harness);
INSTALLED_APPS needs for `modelcluster`.
