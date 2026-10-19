"""Held-out public checks for django-modelcluster, authored from the task's public instruction.md only.

Every case runs its body in a fresh interpreter of the candidate venv (one in-memory SQLite database
per case, configured by support/heldout_checker_app/settings.py). The child process reports each
passed assertion and the first failure; the harness-side wrapper replays them through `c`.
This module imports only the standard library at top level.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

HERE = Path(__file__).resolve().parent
RESULT_MARKER = "HELDOUT_CASE_RESULT "
CHILD_TIMEOUT_SECONDS = 55
PUBLIC_NAMES = {
    "modelcluster.models": ["ClusterableModel", "get_all_child_relations", "get_all_child_m2m_relations"],
    "modelcluster.fields": ["ParentalKey", "ParentalManyToManyField"],
    "modelcluster.queryset": ["FakeQuerySet"],
    "modelcluster.utils": ["ManyToManyTraversalError"],
    "modelcluster.forms": ["ClusterForm", "childformset_factory", "transientmodelformset_factory"],
    "modelcluster.contrib.taggit": ["ClusterTaggableManager"],
}

CASES = {}
BODIES = {}


def case(test_id, apps=()):
    def register(body):
        BODIES[test_id] = body
        CASES[test_id] = lambda c: _run_isolated(c, test_id, apps)
        return body
    return register


# ----------------------------------------------------------------------------- harness side

def _run_isolated(c, test_id, apps):
    code = (
        "import sys; sys.path.insert(0, {support!r}); import importlib.util as u; "
        "s = u.spec_from_file_location('heldout_public_cases_child', {cases!r}); "
        "m = u.module_from_spec(s); s.loader.exec_module(m); m.child_main({test_id!r})"
    ).format(support=str(c.support), cases=str(HERE / "cases.py"), test_id=test_id)
    env = {
        "DJANGO_SETTINGS_MODULE": "heldout_checker_app.settings",
        "HELDOUT_CHECKER_APPS": ",".join(apps),
        "HELDOUT_CHECKER_CONTEXT": json.dumps(c.ctx),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    try:
        finished = c.run_python(code, timeout=CHILD_TIMEOUT_SECONDS, env=env)
    except subprocess.TimeoutExpired:
        c.require(False, f"case process exceeded {CHILD_TIMEOUT_SECONDS} seconds")
        return
    lines = [line for line in finished.stdout.splitlines() if line.startswith(RESULT_MARKER)]
    c.require(bool(lines), f"case process ended without a result (exit {finished.returncode}): {finished.stderr[-1500:]}")
    result = json.loads(lines[-1][len(RESULT_MARKER):])
    for message in result["passed"]:
        c.require(True, message)
    if result["failure"] is not None:
        c.require(False, result["failure"])


# ----------------------------------------------------------------------------- child side

class _Failure(AssertionError):
    pass


class _ChildChecks:
    def __init__(self, context):
        self.ctx = context
        self.passed = []

    def require(self, condition, message):
        if not condition:
            raise _Failure(message)
        self.passed.append(message)

    def equal(self, actual, expected, message):
        self.require(actual == expected, f"{message}: expected {expected!r}, got {actual!r}")

    def raises(self, exception_type, call, message):
        try:
            call()
        except exception_type as exc:
            self.passed.append(message)
            return exc
        except Exception as exc:
            raise _Failure(f"{message}: expected {exception_type!r}, got {type(exc).__name__}: {exc}") from exc
        raise _Failure(f"{message}: no exception raised")

    def same(self, actual, expected, message):
        """Identity comparison of two sequences of objects, in order."""
        actual, expected = list(actual), list(expected)
        ok = len(actual) == len(expected) and all(a is e for a, e in zip(actual, expected))
        self.require(ok, f"{message}: expected {expected!r}, got {actual!r}")

    def same_set(self, actual, expected, message):
        actual, expected = list(actual), list(expected)
        ok = len(actual) == len(expected) and {id(o) for o in actual} == {id(o) for o in expected}
        self.require(ok, f"{message}: expected {expected!r} in any order, got {actual!r}")


def child_main(test_id):
    checks = _ChildChecks(json.loads(os.environ.get("HELDOUT_CHECKER_CONTEXT") or "{}"))
    failure = None
    try:
        import django
        from django.core.management import call_command

        django.setup()
        call_command("migrate", run_syncdb=True, verbosity=0, interactive=False)
        BODIES[test_id](checks)
        if not checks.passed:
            failure = "case made no assertions"
    except _Failure as exc:
        failure = str(exc)
    except BaseException as exc:  # noqa: BLE001 - candidate code may raise anything
        frames = traceback.extract_tb(exc.__traceback__)[-3:]
        where = " <- ".join(f"{Path(f.filename).name}:{f.lineno}" for f in reversed(frames))
        failure = f"{type(exc).__name__}: {exc} (at {where})"
    sys.stdout.write("\n" + RESULT_MARKER + json.dumps({"passed": checks.passed, "failure": failure}) + "\n")
    sys.stdout.flush()


def _names(items):
    return [getattr(item, "name", item) for item in items]


def _sorted_names(items):
    return sorted(_names(items), key=lambda name: (name is None, name))


def _rows(model, **filters):
    return model._default_manager.filter(**filters)


def _through(model, field_name):
    return model._meta.get_field(field_name).remote_field.through


def _relation_name(key_part):
    if isinstance(key_part, str):
        return key_part
    accessor = getattr(key_part, "get_accessor_name", None)
    return accessor() if accessor else None


def _map_entries(child_map, relation_name, old_pk):
    return [value for key, value in child_map.items()
            if isinstance(key, tuple) and len(key) == 2 and _relation_name(key[0]) == relation_name and key[1] == old_pk]


def _query_count(call):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as queries:
        result = call()
    return result, len(queries)


# ============================================================================ packaging-imports

@case("T.R02.01")
def _offline_editable_install(t):
    import django
    import modelcluster
    import taggit

    install = t.ctx["install"]
    t.equal(install.get("returncode"), 0, "the offline install (setup.sh) exit code")
    t.equal(install.get("pip_no_index"), "1", "the install ran with PIP_NO_INDEX=1")
    project = Path(t.ctx["project"]).resolve()
    origin = Path(modelcluster.__file__).resolve()
    t.require(project in origin.parents, f"modelcluster resolves into the copied candidate tree (editable): {origin} is not under {project}")
    prefix = Path(sys.prefix).resolve()
    for module in (django, taggit):
        location = Path(module.__file__).resolve()
        t.require(prefix not in location.parents, f"{module.__name__} is the preinstalled copy, not one installed by setup: {location}")


@case("T.R02.02")
def _django52_compatibility(t):
    import datetime
    import importlib

    for module in PUBLIC_NAMES:
        importlib.import_module(module)
        t.require(True, f"import {module}")
    from heldout_checker_app.models import Event

    event = Event(name="e", when=datetime.datetime(2024, 1, 1, 12, 0, tzinfo=datetime.timezone.utc))
    event.save()
    data = json.loads(event.to_json())
    t.require(isinstance(data.get("when"), str), f"to_json() serializes the aware datetime as a string: {data!r}")
    parsed = datetime.datetime.fromisoformat(data["when"].replace("Z", "+00:00"))
    t.equal(parsed, event.when, "the serialized instant equals the aware datetime")


@case("T.R02.03")
def _taggit_extra(t):
    import importlib.metadata as metadata
    import re

    import taggit.managers

    found = []
    for dist in metadata.distributions():
        top_level = (dist.read_text("top_level.txt") or "").split()
        files = [str(path) for path in (dist.files or [])]
        name = re.sub(r"[-_.]", "", (dist.metadata["Name"] or "").lower())
        if "modelcluster" in top_level or any(path.startswith("modelcluster/") for path in files) or "modelcluster" in name:
            found.append(dist)
    t.require(found, "an installed distribution provides the modelcluster package")
    dist = found[0]
    requires = list(dist.requires or [])
    taggit_requirements = [req for req in requires if re.match(r"\s*django[-_.]?taggit\b", req, re.IGNORECASE)]
    t.require(taggit_requirements, f"django-taggit appears in Requires-Dist: {requires}")
    t.require(any("extra" in req for req in taggit_requirements),
              f"django-taggit is conditioned on an extra: {taggit_requirements}")
    t.require(dist.metadata.get_all("Provides-Extra"), "the distribution declares an extra (Provides-Extra)")
    from modelcluster.contrib.taggit import ClusterTaggableManager

    t.require(issubclass(ClusterTaggableManager, taggit.managers.TaggableManager),
              "modelcluster.contrib.taggit builds on the preinstalled taggit TaggableManager")


@case("T.R03.01")
def _public_import_surface(t):
    import importlib

    for module_name, names in PUBLIC_NAMES.items():
        module = importlib.import_module(module_name)
        for name in names:
            t.require(hasattr(module, name), f"from {module_name} import {name}")


@case("T.R03.02", apps=("probe",))
def _subclass_private_names(t):
    from heldout_checker_app.models import Genre
    from heldout_checker_probe.models import ProbeBand, ProbeMember, with_private_names

    from modelcluster.fields import ParentalKey, ParentalManyToManyField

    t.require(isinstance(ProbeMember._meta.get_field("band"), ParentalKey), "checker ParentalKey subclass is a ParentalKey")
    t.require(isinstance(ProbeBand._meta.get_field("genres"), ParentalManyToManyField),
              "checker ParentalManyToManyField subclass is a ParentalManyToManyField")
    g1, g2 = Genre.objects.create(name="g1"), Genre.objects.create(name="g2")
    band = ProbeBand(name="b")
    m1, m2 = ProbeMember(name="a"), ProbeMember(name="b")
    band.members = [m1]
    t.same(band.members.all(), [m1], "assignment through the subclassed ParentalKey")
    manager = band.members
    manager.__class__ = with_private_names(type(manager))
    manager.add(m2)
    t.same_set(manager.all(), [m1, m2], "add()/all() on a manager subclass defining _cache/_items/_parent/_field")
    t.equal(manager.count(), 2, "count() on the manager subclass")
    band.genres = [g1]
    band.genres.add(g2)
    t.equal(sorted(g.pk for g in band.genres.all()), [g1.pk, g2.pk], "assign/add through the subclassed ParentalManyToManyField")
    band.save()
    t.equal(sorted(_rows(ProbeMember, band=band).values_list("name", flat=True)), ["a", "b"], "save() writes the children")
    through = _through(ProbeBand, "genres")
    t.equal(through.objects.filter(probeband=band).count(), 2, "save() writes the parental m2m rows")


# ============================================================================ parentalkey-deferring-manager

@case("T.R01.01")
def _band_cluster_example(t):
    from heldout_checker_app.models import Band, BandMember

    beatles = Band(name="The Beatles")
    beatles.members = [BandMember(name="John Lennon"), BandMember(name="Paul McCartney")]
    t.equal(beatles.members.count(), 2, "members.count() before save")
    t.equal(Band.objects.filter(name="The Beatles").count(), 0, "no Band row before save")
    t.equal(BandMember.objects.count(), 0, "no BandMember row before save")
    beatles.save()
    t.equal(Band.objects.filter(name="The Beatles").count(), 1, "one Band row after save")
    t.equal(sorted(BandMember.objects.values_list("band_id", flat=True)), [beatles.pk, beatles.pk],
            "two BandMember rows pointing at the band after save")


@case("T.R04.01", apps=("default",))
def _parentalkey_default_cascade(t):
    from django.db import models
    from heldout_checker_default.models import DefaultBand, DefaultMember

    field = DefaultMember._meta.get_field("band")
    t.require(isinstance(field, models.ForeignKey), "ParentalKey is a django ForeignKey")
    t.require(field.remote_field.on_delete is models.CASCADE, f"omitted on_delete defaults to CASCADE, got {field.remote_field.on_delete!r}")
    band = DefaultBand(name="b")
    band.save()
    DefaultMember.objects.create(band=band, name="x")
    DefaultMember.objects.create(band=band, name="y")
    band.delete()
    t.equal(DefaultMember.objects.count(), 0, "deleting the parent cascades to its children")


@case("T.R04.02")
def _assignment_replaces(t):
    from heldout_checker_app.models import Band, BandMember

    band = Band(name="b")
    m1, m2, m3 = BandMember(name="m1"), BandMember(name="m2"), BandMember(name="m3")
    band.members = [m1, m2]
    t.require(m1.band is band and m2.band is band, "assigned children point back at the parent instance")
    band.members = [m3]
    t.same(band.members.all(), [m3], "the second assignment replaces the in-memory set")
    t.require(m3.band is band, "m3.band is the parent instance")
    t.equal(BandMember.objects.count(), 0, "assignment writes nothing")


@case("T.R04.03")
def _all_sources(t):
    from heldout_checker_app.models import Band, BandMember

    from modelcluster.queryset import FakeQuerySet

    t.equal(list(Band(name="u").members.all()), [], "(a) unsaved untouched parent: empty all()")
    band = Band(name="b")
    m1 = BandMember(name="m1")
    band.members = [m1]
    result = band.members.all()
    t.require(isinstance(result, FakeQuerySet), f"(b) touched relation returns a FakeQuerySet, got {type(result)!r}")
    t.same(result, [m1], "(b) FakeQuerySet holds the assigned child")
    saved = Band(name="s")
    saved.save()
    BandMember.objects.create(band=saved, name="x")
    BandMember.objects.create(band=saved, name="y")
    fresh = Band.objects.get(pk=saved.pk)
    t.equal(_sorted_names(fresh.members.all()), ["x", "y"], "(c) saved untouched parent reads the database children")


@case("T.R04.04")
def _add_replaces_equal(t):
    from heldout_checker_app.models import Band, BandMember

    band = Band(name="b")
    m1, m2 = BandMember(name="m1"), BandMember(name="m2")
    band.members = [m1, m2]
    band.save()
    m1_copy = BandMember.objects.get(pk=m1.pk)
    m1_copy.name = "renamed"
    m3 = BandMember(name="m3")
    band.members.add(m1_copy, m3)
    band.members.add(m2, m2)
    items = list(band.members.all())
    t.equal(len(items), 3, "no duplicates after re-adding")
    t.equal(_sorted_names(items), ["m2", "m3", "renamed"], "the mutated instance replaced the equal one")
    t.require(any(item is m1_copy for item in items) and not any(item is m1 for item in items),
              "the re-added instance itself is held in place of the old one")


@case("T.R04.05")
def _remove_create_set_clear(t):
    from heldout_checker_app.models import Band, BandMember

    band = Band(name="b")
    m1, m2, m3, m4 = (BandMember(name=f"m{i}") for i in range(1, 5))
    band.members = [m1, m2, m3]
    band.members.remove(m2)
    t.same_set(band.members.all(), [m1, m3], "remove()")
    t.equal(BandMember.objects.count(), 0, "no row after remove()")
    created = band.members.create(name="Ringo")
    t.require(isinstance(created, BandMember) and created.name == "Ringo", "create() returns the new child")
    t.require(created.band is band and created.pk is None, "create() points at the parent and does not save")
    t.require(any(item is created for item in band.members.all()), "create() appends the child")
    t.equal(BandMember.objects.count(), 0, "no row after create()")
    band.members.set([m4])
    t.same(band.members.all(), [m4], "set()")
    band.members.clear()
    t.equal(list(band.members.all()), [], "clear()")
    t.equal(BandMember.objects.count(), 0, "no row after set()/clear()")


@case("T.R04.06")
def _manager_read_api(t):
    from heldout_checker_app.models import Band, BandMember

    band = Band(name="b")
    a, b, c = BandMember(name="a"), BandMember(name="b"), BandMember(name="c")
    band.members = [a, b, c]
    manager, everything = band.members, band.members.all()
    t.equal(manager.count(), 3, "count()")
    t.same(manager.filter(name="b"), [b], "filter()")
    t.same(manager.exclude(name="b"), everything.exclude(name="b"), "exclude() matches all().exclude()")
    t.require(manager.get(name="c") is c, "get()")
    t.same(manager.order_by("-name"), [c, b, a], "order_by('-name')")
    t.require(manager.first() is everything.first(), "first() matches all().first()")
    t.equal(manager.exists(), True, "exists()")
    t.equal(list(manager.values_list("name", flat=True)), list(everything.values_list("name", flat=True)),
            "values_list(flat=True) matches all()")


@case("T.R04.07")
def _commit(t):
    from django.db import IntegrityError
    from heldout_checker_app.models import Band, BandMember

    band = Band(name="b")
    m1, m2, m3 = BandMember(name="m1"), BandMember(name="m2"), BandMember(name="m3")
    band.members = [m1, m2]
    band.save()
    band.members = [m1, m3]
    band.members.commit()
    t.equal(sorted(_rows(BandMember, band=band).values_list("name", flat=True)), ["m1", "m3"], "commit() writes the in-memory set")
    t.require(not BandMember.objects.filter(pk=m2.pk).exists(), "commit() deletes rows no longer in the set")
    t.equal(set(BandMember.objects.values_list("band_id", flat=True)), {band.pk}, "committed rows point at the band")
    unsaved = Band(name="u")
    unsaved.members = [BandMember(name="m4")]
    before = BandMember.objects.count()
    t.raises(IntegrityError, unsaved.members.commit, "commit() on an unsaved parent raises IntegrityError")
    t.equal(BandMember.objects.count(), before, "the failed commit wrote nothing")


@case("T.R04.08")
def _child_ordering(t):
    from heldout_checker_app.models import Choir, Singer

    choir = Choir(name="c")
    choir.singers = [Singer(name="Zed"), Singer(name="Amy")]
    t.equal(_names(choir.singers.all()), ["Amy", "Zed"], "in-memory children follow Meta.ordering after assignment")
    choir.singers.add(Singer(name="Kim"))
    t.equal(_names(choir.singers.all()), ["Amy", "Kim", "Zed"], "in-memory children follow Meta.ordering after add()")


@case("T.R04.09")
def _check_e001(t):
    from django.core import checks
    from django.db import models
    from django.test.utils import isolate_apps

    from modelcluster.fields import ParentalKey
    from modelcluster.models import ClusterableModel

    with isolate_apps("heldout_checker_app"):
        class PlainModel(models.Model):
            class Meta:
                app_label = "heldout_checker_app"

        class ClusterParent(ClusterableModel):
            class Meta:
                app_label = "heldout_checker_app"

        class BadChild(models.Model):
            parent = ParentalKey(PlainModel, related_name="bad_children", on_delete=models.CASCADE)

            class Meta:
                app_label = "heldout_checker_app"

        class GoodChild(models.Model):
            parent = ParentalKey(ClusterParent, related_name="good_children", on_delete=models.CASCADE)

            class Meta:
                app_label = "heldout_checker_app"

        bad = BadChild._meta.get_field("parent").check()
        good = GoodChild._meta.get_field("parent").check()
    e001 = [error for error in bad if error.id == "modelcluster.E001"]
    t.require(e001, f"modelcluster.E001 for a ParentalKey to a plain model: {bad!r}")
    t.require(isinstance(e001[0], checks.Error), "E001 is a checks.Error")
    t.equal(e001[0].msg, "ParentalKey must point to a subclass of ClusterableModel.", "E001 message")
    t.require(not any(error.id == "modelcluster.E001" for error in good), "no E001 for a ParentalKey to a ClusterableModel")


@case("T.R04.10")
def _check_e002(t):
    from django.core import checks
    from django.db import models
    from django.test.utils import isolate_apps

    from modelcluster.fields import ParentalKey
    from modelcluster.models import ClusterableModel

    with isolate_apps("heldout_checker_app"):
        class HiddenParent(ClusterableModel):
            class Meta:
                app_label = "heldout_checker_app"

        class HiddenChild(models.Model):
            parent = ParentalKey(HiddenParent, related_name="+", on_delete=models.CASCADE)

            class Meta:
                app_label = "heldout_checker_app"

        errors = HiddenChild._meta.get_field("parent").check()
    e002 = [error for error in errors if error.id == "modelcluster.E002"]
    t.require(e002, f"modelcluster.E002 for related_name='+': {errors!r}")
    t.require(isinstance(e002[0], checks.Error), "E002 is a checks.Error")
    t.equal(e002[0].msg, "related_name='+' is not allowed on ParentalKey fields", "E002 message")


@case("T.R04.11")
def _check_unresolved(t):
    from django.db import models
    from django.test.utils import isolate_apps

    from modelcluster.fields import ParentalKey

    with isolate_apps("heldout_checker_app"):
        class OrphanChild(models.Model):
            parent = ParentalKey("NoSuchModel", on_delete=models.CASCADE)

            class Meta:
                app_label = "heldout_checker_app"

        errors = OrphanChild.check()
    ids = [error.id for error in errors]
    t.require("fields.E300" in ids, f"Django's fields.E300 for an unresolved target: {ids}")
    t.require("modelcluster.E001" not in ids, f"no modelcluster.E001 for an unresolved target: {ids}")


@case("T.integration.cluster-lifecycle")
def _cluster_lifecycle(t):
    from heldout_checker_app.models import Band, BandMember, Genre

    g1, g2 = Genre.objects.create(name="g1"), Genre.objects.create(name="g2")
    through = _through(Band, "genres")
    m1, m2 = BandMember(name="m1"), BandMember(name="m2")
    band = Band(name="B", members=[m1, m2], genres=[g1])
    t.same(band.members.filter(name="m1"), [m1], "in-memory filter before save")
    t.same(band.members.order_by("-name"), [m2, m1], "in-memory order_by before save")
    t.require(band.members.get(name="m2") is m2, "in-memory get before save")
    t.equal([g.pk for g in band.genres.all()], [g1.pk], "in-memory genres before save")
    t.equal((Band.objects.count(), BandMember.objects.count(), through.objects.count()), (0, 0, 0), "database empty before save")
    band.save()
    t.equal(Band.objects.count(), 1, "band row after first save")
    t.equal(sorted(_rows(BandMember, band=band).values_list("name", flat=True)), ["m1", "m2"], "member rows after first save")
    t.equal(list(through.objects.filter(band=band).values_list("genre_id", flat=True)), [g1.pk], "genre link after first save")
    band.members.remove(m1)
    band.members.create(name="m3")
    band.genres.set([g2])
    t.equal(_names(band.members.order_by("name")), ["m2", "m3"], "in-memory members after mutations")
    t.equal([g.pk for g in band.genres.all()], [g2.pk], "in-memory genres after mutations")
    t.equal(sorted(_rows(BandMember, band=band).values_list("name", flat=True)), ["m1", "m2"], "database still holds the old members")
    t.equal(list(through.objects.filter(band=band).values_list("genre_id", flat=True)), [g1.pk], "database still holds the old link")
    band.save()
    t.equal(sorted(_rows(BandMember, band=band).values_list("name", flat=True)), ["m2", "m3"], "member rows after second save")
    t.require(not BandMember.objects.filter(pk=m1.pk).exists(), "m1's row deleted by the second save")
    t.equal(list(through.objects.filter(band=band).values_list("genre_id", flat=True)), [g2.pk], "only the g2 link after second save")


# ============================================================================ parental-m2m

@case("T.R05.01")
def _parental_m2m_in_memory(t):
    from django.db import models
    from heldout_checker_app.models import Article, Author

    t.require(isinstance(Article._meta.get_field("authors"), models.ManyToManyField), "ParentalManyToManyField subclasses ManyToManyField")
    a1, a2, a3 = (Author.objects.create(name=f"a{i}") for i in range(1, 4))
    through = _through(Article, "authors")
    article = Article(title="x")
    article.authors.add(a1, a2)
    t.equal(sorted(a.pk for a in article.authors.all()), [a1.pk, a2.pk], "add()")
    article.authors.remove(a1)
    t.equal([a.pk for a in article.authors.all()], [a2.pk], "remove()")
    article.authors.set([a2, a3])
    t.equal(sorted(a.pk for a in article.authors.all()), [a2.pk, a3.pk], "set()")
    t.equal(article.authors.count(), 2, "count()")
    t.equal(through.objects.count(), 0, "no through rows before save")
    article.save()
    t.equal(sorted(through.objects.filter(article=article).values_list("author_id", flat=True)), [a2.pk, a3.pk], "through rows after save")
    article.authors.clear()
    t.equal(list(article.authors.all()), [], "clear() in memory")
    t.equal(through.objects.filter(article=article).count(), 2, "clear() writes nothing before save")
    article.save()
    t.equal(through.objects.filter(article=article).count(), 0, "no through rows after the second save")


@case("T.R05.02")
def _parental_m2m_assignment(t):
    from heldout_checker_app.models import Article, Author

    alice, bob, anne = Author.objects.create(name="Alice"), Author.objects.create(name="Bob"), Author.objects.create(name="Anne")
    through = _through(Article, "authors")
    article = Article(title="x")
    article.authors = [alice, bob]
    t.equal(sorted(a.pk for a in article.authors.all()), sorted([alice.pk, bob.pk]), "list assignment on an unsaved parent")
    article.authors = Author.objects.filter(name__startswith="A")
    t.equal(sorted(a.pk for a in article.authors.all()), sorted([alice.pk, anne.pk]), "queryset assignment replaces the set")
    t.equal(through.objects.count(), 0, "assignment writes nothing")
    article.save()
    t.equal(sorted(through.objects.filter(article=article).values_list("author_id", flat=True)), sorted([alice.pk, anne.pk]),
            "through rows match the last assignment")


@case("T.R05.03")
def _parental_m2m_fresh(t):
    from heldout_checker_app.models import Article, Author

    article = Article(title="x")
    t.require(article.authors.model is Author, "the manager's model attribute is the target model")
    t.equal(list(article.authors.all()), [], "fresh unsaved instance reads empty")
    t.equal(article.authors.count(), 0, "fresh unsaved instance count() == 0")


@case("T.R05.04")
def _parental_m2m_add_unsaved(t):
    from heldout_checker_app.models import Article, Author

    article = Article(title="x")
    t.raises(ValueError, lambda: article.authors.add(Author(name="unsaved")), "add() of an object without a pk raises ValueError")


@case("T.R05.05")
def _parental_m2m_ordering(t):
    from heldout_checker_app.models import Article, Author

    zed, amy = Author.objects.create(name="Zed"), Author.objects.create(name="Amy")
    article = Article(title="x")
    article.authors.set([zed, amy])
    t.equal(_names(article.authors.all()), ["Amy", "Zed"], "in-memory set follows the target's Meta.ordering")


@case("T.R05.06")
def _parental_m2m_reverse(t):
    from heldout_checker_app.models import Article, Author

    a1 = Author.objects.create(name="a1")
    article = Article(title="x")
    article.authors = [a1]
    t.equal(list(a1.articles_by_author.all()), [], "reverse accessor ignores unsaved parents")
    article.save()
    fresh = Author.objects.get(pk=a1.pk)
    t.equal([a.pk for a in fresh.articles_by_author.all()], [article.pk], "reverse accessor includes the saved parent")
    t.equal(fresh.articles_by_author.filter(title="x").count(), 1, "reverse accessor supports filter()/count()")


@case("T.R05.07")
def _parental_m2m_value_from_object(t):
    from heldout_checker_app.models import Article, Author

    a1, a2 = Author.objects.create(name="a1"), Author.objects.create(name="a2")
    article = Article(title="x")
    article.authors = [a1, a2]
    value = Article._meta.get_field("authors").value_from_object(article)
    t.equal(sorted(obj.pk for obj in value), sorted([a1.pk, a2.pk]), "value_from_object returns the in-memory set before save")


@case("T.R05.08")
def _parental_m2m_update_fields(t):
    from heldout_checker_app.models import Article, Author

    a1, a2 = Author.objects.create(name="a1"), Author.objects.create(name="a2")
    through = _through(Article, "authors")
    article = Article(title="old")
    article.authors = [a1]
    article.save()
    article.title = "new"
    article.authors = [a2]
    article.save(update_fields=["authors"])
    t.equal(list(through.objects.filter(article=article).values_list("author_id", flat=True)), [a2.pk],
            "update_fields=['authors'] commits the m2m")
    t.equal(Article.objects.get(pk=article.pk).title, "old", "update_fields=['authors'] leaves the title unsaved")


# ============================================================================ fakequeryset-filtering

@case("T.R06.01")
def _fakequeryset_construction(t):
    from heldout_checker_app.models import Log

    from modelcluster.queryset import FakeQuerySet

    l1, l2, l3 = Log(name="a", score=1), Log(name="b", score=2), Log(name="c", score=3)
    qs = FakeQuerySet(Log, [l1, l2, l3])
    t.same(qs, [l1, l2, l3], "iteration yields the wrapped list in order")
    t.equal(len(qs), 3, "len()")
    t.same(qs.filter(score=2), [l2], "filter() over unsaved instances")


@case("T.R06.02")
def _filter_exclude(t):
    from heldout_checker_app.models import BandMember

    from modelcluster.queryset import FakeQuerySet

    john, paul, george, ringo = (BandMember(name=name) for name in ("John", "Paul", "George", "Ringo"))
    qs = FakeQuerySet(BandMember, [john, paul, george, ringo])
    f, e = qs.filter(name="John"), qs.exclude(name="John")
    t.require(isinstance(f, FakeQuerySet) and isinstance(e, FakeQuerySet), "filter()/exclude() return FakeQuerySets")
    t.require(f is not qs and e is not qs, "filter()/exclude() return new querysets")
    t.same(f, [john], "filter(name='John')")
    t.same(e, [paul, george, ringo], "exclude(name='John') is the complement")
    t.same(qs, [john, paul, george, ringo], "the original queryset is unchanged")


@case("T.R06.03")
def _text_lookups(t):
    from heldout_checker_app.models import Log

    from modelcluster.queryset import FakeQuerySet

    john, paul, george = Log(name="John Lennon"), Log(name="Paul McCartney"), Log(name="george harrison")
    qs = FakeQuerySet(Log, [john, paul, george])
    expectations = [
        ({"name": "John Lennon"}, [john]),
        ({"name__exact": "John Lennon"}, [john]),
        ({"name__exact": "john lennon"}, []),
        ({"name__iexact": "JOHN LENNON"}, [john]),
        ({"name__contains": "Mc"}, [paul]),
        ({"name__contains": "MC"}, []),
        ({"name__icontains": "MC"}, [paul]),
        ({"name__startswith": "Pa"}, [paul]),
        ({"name__startswith": "pa"}, []),
        ({"name__istartswith": "GEO"}, [george]),
        ({"name__endswith": "Lennon"}, [john]),
        ({"name__endswith": "LENNON"}, []),
        ({"name__iendswith": "HARRISON"}, [george]),
        ({"name__regex": "^J.*n$"}, [john]),
        ({"name__regex": "^g"}, [george]),
        ({"name__iregex": "^G"}, [george]),
    ]
    for lookup, expected in expectations:
        t.same(qs.filter(**lookup), expected, f"filter({lookup})")


@case("T.R06.04")
def _comparison_lookups(t):
    import datetime

    from heldout_checker_app.models import Log

    from modelcluster.queryset import FakeQuerySet

    dates = [None, datetime.date(2019, 12, 31), datetime.date(2020, 1, 1), None, datetime.date(2021, 5, 5)]
    rows = [Log(name=str(score), score=score, d=d) for score, d in zip(range(1, 6), dates)]
    qs = FakeQuerySet(Log, rows)
    expectations = [
        ({"score__lt": 3}, [1, 2]), ({"score__lte": 3}, [1, 2, 3]), ({"score__gt": 3}, [4, 5]),
        ({"score__gte": 3}, [3, 4, 5]), ({"score__range": (2, 4)}, [2, 3, 4]), ({"score__in": [1, 5]}, [1, 5]),
        ({"d__isnull": True}, [1, 4]), ({"d__isnull": False}, [2, 3, 5]),
        ({"d__gte": datetime.date(2020, 1, 1)}, [3, 5]),
    ]
    for lookup, scores in expectations:
        t.equal([row.score for row in qs.filter(**lookup)], scores, f"filter({lookup})")


@case("T.R06.05")
def _coercion_and_none(t):
    from heldout_checker_app.models import Log

    from modelcluster.queryset import FakeQuerySet

    r1, r2, r3 = Log.objects.create(name=None), Log.objects.create(name=""), Log.objects.create(name="Flood")
    qs = FakeQuerySet(Log, [r1, r2, r3])
    t.same(qs.filter(id=str(r2.pk)), [r2], "string id coerced to the integer pk")
    t.same(qs.filter(name=None), [r1], "name=None")
    t.same(qs.filter(name=""), [r2], "name=''")
    t.same(qs.filter(name__isnull=True), [r1], "name__isnull=True")
    t.same(qs.filter(name__isnull=False), [r2, r3], "name__isnull=False")
    t.require(qs.get(name__in=[None, "Mink Car"]) is r1, "get(name__in=[None, 'Mink Car']) returns the None row")
    t.same(qs.filter(name__in=[None, "Flood"]), [r1, r3], "in matches None by Python membership")


@case("T.R06.06")
def _field_named_like_lookup(t):
    from heldout_checker_app.models import RangeRow

    from modelcluster.queryset import FakeQuerySet

    low, high = RangeRow(range=3), RangeRow(range=7)
    qs = FakeQuerySet(RangeRow, [low, high])
    t.same(qs.filter(range=3), [low], "range=3 is an exact match on the field named range")
    t.same(qs.filter(range__gt=5), [high], "range__gt=5 applies gt to the field named range")


@case("T.R06.07")
def _relation_traversal(t):
    from heldout_checker_app.models import Band, BandMember, Chef, Diner, Restaurant

    from modelcluster.queryset import FakeQuerySet

    gordon, other = Chef.objects.create(name="Gordon"), Chef.objects.create(name="Other")
    r1 = Restaurant(name="r1", proprietor=gordon, head_chef=gordon)
    r2 = Restaurant(name="r2")
    r3 = Restaurant(name="r3", proprietor=other, head_chef=other)
    for restaurant in (r1, r2, r3):
        restaurant.save()
    d1 = Diner(name="d1", favourite_restaurant=r1)
    d2 = Diner(name="d2", favourite_restaurant=None)
    d3 = Diner(name="d3", favourite_restaurant=r2)
    d4 = Diner(name="d4", favourite_restaurant=r3)
    qs = FakeQuerySet(Diner, [d1, d2, d3, d4])
    t.same(qs.filter(favourite_restaurant__proprietor__name="Gordon"), [d1], "forward FK chain; None intermediates excluded")
    t.same(qs.filter(favourite_restaurant__head_chef__name="Gordon"), [d1], "forward one-to-one chain; None intermediates excluded")
    band = Band(name="The Beatles")
    member = BandMember(name="x")
    band.members = [member]
    t.same(band.members.filter(band__name="The Beatles"), [member], "band__name traverses to the in-memory parent")
    t.same(band.members.filter(band__name="Other"), [], "band__name non-match")


@case("T.R06.08")
def _instance_matching(t):
    from heldout_checker_app.models import Band, BandMember, Diner, Place, Restaurant, Review, Visit

    from modelcluster.queryset import FakeQuerySet

    b1 = Band(name="b1")
    b1.members = [BandMember(name="x"), BandMember(name="y")]
    b1.save()
    b1_again = Band.objects.get(pk=b1.pk)
    t.equal(len(b1.members.filter(band=b1_again)), 2, "saved instances match by pk")
    u1, u2 = Band(name="u1"), Band(name="u2")
    u1.members = [BandMember(name="z")]
    t.equal(len(u1.members.filter(band=u2)), 0, "two distinct unsaved instances do not match")
    restaurant = Restaurant(name="R")
    restaurant.save()
    other = Place(name="other")
    other.save()
    place = Place.objects.get(pk=restaurant.pk)
    visits = FakeQuerySet(Visit, [Visit(place=place, note="v")])
    t.equal(len(visits.filter(place=restaurant)), 1, "FK to Place matched by the Restaurant subclass instance")
    t.equal(len(visits.filter(place=other)), 0, "FK to Place does not match a different Place")
    reviews = FakeQuerySet(Review, [Review(place=restaurant, author="a")])
    t.equal(len(reviews.filter(place=place)), 1, "ParentalKey to Place holding a Restaurant matched by the Place instance")
    diners = FakeQuerySet(Diner, [Diner(name="d", favourite_restaurant=restaurant)])
    t.equal(len(diners.filter(favourite_restaurant=place)), 1, "FK to Restaurant matched by the Place superclass instance")


@case("T.R06.09")
def _q_objects(t):
    from django.db.models import Q
    from heldout_checker_app.models import Log

    from modelcluster.queryset import FakeQuerySet

    a, b, c = Log(name="a", flag=True), Log(name="b", flag=False), Log(name="c", flag=True)
    qs = FakeQuerySet(Log, [a, b, c])
    t.same(qs.filter(Q(name="a") | Q(name="b")), [a, b], "OR")
    t.same(qs.filter(Q(name="a") & Q(flag=True)), [a], "AND")
    t.same(qs.filter(Q(name="a") ^ Q(flag=True)), [c], "XOR")
    t.same(qs.filter(~Q(name="a")), [b, c], "negation")
    t.same(qs.exclude(Q(name="a") | Q(name="b")), [c], "exclude with OR")
    t.same(qs.filter(Q(name="a") | Q(name="b"), flag=True), [a], "positional Q with keyword lookups")


@case("T.R06.10")
def _m2m_traversal_error(t):
    from heldout_checker_app.models import Article, Author

    from modelcluster.queryset import FakeQuerySet
    from modelcluster.utils import ManyToManyTraversalError

    author = Author.objects.create(name="x")
    article = Article(title="t")
    article.authors = [author]
    qs = FakeQuerySet(Article, [article])
    t.raises(ManyToManyTraversalError, lambda: list(qs.filter(authors__name="x")),
             "traversing a many-to-many relation raises ManyToManyTraversalError")


def _date_components(value):
    iso = value.isocalendar()
    return {
        "year": value.year, "iso_year": iso[0], "month": value.month, "day": value.day, "week": iso[1],
        "week_day": value.isoweekday() % 7 + 1, "iso_week_day": value.isoweekday(), "quarter": (value.month - 1) // 3 + 1,
    }


@case("T.R06.11")
def _date_transforms(t):
    import datetime
    from zoneinfo import ZoneInfo

    from django.utils import timezone
    from heldout_checker_app.models import Alarm, Album, Log

    from modelcluster.queryset import FakeQuerySet

    albums = [Album(title="a1", release_date=datetime.date(1999, 3, 15)), Album(title="a2", release_date=datetime.date(2021, 1, 1)),
              Album(title="a3", release_date=datetime.date(1999, 12, 31))]
    qs = FakeQuerySet(Album, albums)
    t.same(qs.filter(release_date__year=1999), [albums[0], albums[2]], "release_date__year")
    for transform in ("year", "iso_year", "month", "day", "week", "week_day", "iso_week_day", "quarter"):
        for target in albums:
            wanted = _date_components(target.release_date)[transform]
            expected = [a for a in albums if _date_components(a.release_date)[transform] == wanted]
            t.same(qs.filter(**{f"release_date__{transform}": wanted}), expected, f"release_date__{transform}={wanted}")
    t.require(qs.get(release_date__month=3) is albums[0], "get(release_date__month=3)")
    t.equal(list(qs.values("release_date__year")), [{"release_date__year": a.release_date.year} for a in albums],
            "values('release_date__year')")
    local = ZoneInfo(timezone.get_current_timezone_name())
    logs = [Log(name="l1", time=datetime.datetime(2020, 1, 2, 10, 30, tzinfo=local)),
            Log(name="l2", time=datetime.datetime(2020, 1, 3, 8, 15, tzinfo=local)), Log(name="l3", time=None)]
    lq = FakeQuerySet(Log, logs)
    t.same(lq.filter(time__date=datetime.date(2020, 1, 2)), [logs[0]], "time__date")
    t.same(lq.filter(time__time=datetime.time(10, 30)), [logs[0]], "time__time")
    t.same(lq.filter(time__hour=8), [logs[1]], "datetime __hour")
    t.equal(list(lq.values_list("time__date", flat=True)), [datetime.date(2020, 1, 2), datetime.date(2020, 1, 3), None],
            "values_list('time__date', flat=True)")
    alarms = [Alarm(t=datetime.time(10, 5, 30)), Alarm(t=datetime.time(11, 20, 45))]
    aq = FakeQuerySet(Alarm, alarms)
    t.same(aq.filter(t__hour=10), [alarms[0]], "t__hour")
    t.same(aq.filter(t__minute=20), [alarms[1]], "t__minute")
    t.same(aq.filter(t__second=30), [alarms[0]], "t__second")


@case("T.R06.12")
def _week_conventions(t):
    import datetime

    from heldout_checker_app.models import Log

    from modelcluster.queryset import FakeQuerySet

    rows = [Log(d=datetime.date(2024, 6, 2)), Log(d=datetime.date(2024, 6, 3)), Log(d=datetime.date(2021, 1, 1)), Log(d=None)]
    keys = ["d__week_day", "d__iso_week_day", "d__week", "d__iso_year", "d__year"]
    values = list(FakeQuerySet(Log, rows).values(*keys))
    t.equal((values[0]["d__week_day"], values[0]["d__iso_week_day"]), (1, 7), "Sunday 2024-06-02: week_day 1, iso_week_day 7")
    t.equal((values[1]["d__week_day"], values[1]["d__iso_week_day"]), (2, 1), "Monday 2024-06-03: week_day 2, iso_week_day 1")
    t.equal((values[2]["d__iso_year"], values[2]["d__week"], values[2]["d__year"]), (2020, 53, 2021),
            "2021-01-01: iso_year 2020, week 53, year 2021")
    t.equal(values[3], {key: None for key in keys}, "every component of a None date is None")


@case("T.integration.queryset-db-parity")
def _queryset_db_parity(t):
    import datetime

    from django.db.models import Q
    from heldout_checker_app.models import Band, BandMember, Restaurant

    rosa, zeno = Restaurant(name="Rosa"), Restaurant(name="Zeno")
    rosa.save()
    zeno.save()
    band = Band(name="B")
    band.members = [
        BandMember(name="John Lennon", age=40, joined=datetime.date(1960, 7, 6), favourite_restaurant=rosa),
        BandMember(name="Paul McCartney", age=38, joined=datetime.date(1957, 7, 6), favourite_restaurant=zeno),
        BandMember(name="george harrison", age=25, joined=datetime.date(1958, 2, 6)),
        BandMember(name="Ringo Starr", age=40, joined=datetime.date(1962, 8, 18), favourite_restaurant=rosa),
        BandMember(name="Pete Best"),
    ]
    battery = [
        ("contains", lambda qs: qs.filter(name__contains="o").order_by("name").values_list("name", flat=True)),
        ("icontains", lambda qs: qs.filter(name__icontains="HAR").order_by("name").values_list("name", flat=True)),
        ("istartswith", lambda qs: qs.filter(name__istartswith="p").order_by("name").values_list("name", flat=True)),
        ("range", lambda qs: qs.filter(age__range=(30, 40)).order_by("name").values_list("name", flat=True)),
        ("lt", lambda qs: qs.filter(age__lt=40).order_by("name").values_list("name", flat=True)),
        ("gte", lambda qs: qs.filter(age__gte=38).order_by("name").values_list("name", flat=True)),
        ("in", lambda qs: qs.filter(age__in=[25, 38]).order_by("name").values_list("name", flat=True)),
        ("isnull", lambda qs: qs.filter(age__isnull=True).order_by("name").values_list("name", flat=True)),
        ("Q or", lambda qs: qs.filter(Q(age=40) | Q(name__istartswith="paul")).order_by("name").values_list("name", flat=True)),
        ("Q xor", lambda qs: qs.filter(Q(age=40) ^ Q(name__icontains="john")).order_by("name").values_list("name", flat=True)),
        ("Q negation", lambda qs: qs.filter(~Q(age=40)).order_by("name").values_list("name", flat=True)),
        ("relation", lambda qs: qs.filter(favourite_restaurant__name="Rosa").order_by("name").values_list("name", flat=True)),
        ("year transform", lambda qs: qs.filter(joined__year=1958).order_by("name").values_list("name", flat=True)),
        ("month transform", lambda qs: qs.filter(joined__month=7).order_by("name").values_list("name", flat=True)),
        ("order age,name", lambda qs: qs.order_by("age", "name").values_list("name", flat=True)),
        ("order -joined,name", lambda qs: qs.order_by("-joined", "name").values_list("name", flat=True)),
        ("values_list pair", lambda qs: qs.order_by("name").values_list("name", "age")),
        ("exclude", lambda qs: qs.exclude(name__istartswith="p").order_by("name").values_list("name", flat=True)),
        ("relation values", lambda qs: qs.order_by("name").values_list("favourite_restaurant__name", flat=True)),
    ]
    in_memory = [(label, list(chain(band.members.all()))) for label, chain in battery]
    band.save()
    stored = BandMember.objects.filter(band=band)
    for label, result in in_memory:
        chain = dict(battery)[label]
        t.equal([tuple(row) if isinstance(row, tuple) else row for row in result], list(chain(stored)),
                f"in-memory result equals SQLite for {label}")


# ============================================================================ fakequeryset-retrieval

@case("T.R06.13")
def _get_and_counts(t):
    from heldout_checker_app.models import Band, BandMember

    from modelcluster.queryset import FakeQuerySet

    shared, other = Band(name="shared"), Band(name="other")
    a, b, c = BandMember(name="a", band=other), BandMember(name="b", band=shared), BandMember(name="c", band=shared)
    qs = FakeQuerySet(BandMember, [a, b, c])
    t.require(qs.get(name="a") is a, "get() returns the single match")
    t.raises(BandMember.DoesNotExist, lambda: qs.get(name="zzz"), "get() with no match raises the model's DoesNotExist")
    t.raises(BandMember.MultipleObjectsReturned, lambda: qs.get(band=shared),
             "get() with two matches raises the model's MultipleObjectsReturned")
    t.equal(qs.values("name").get(name="a"), {"name": "a"}, "values().get() returns the shaped dict")
    t.equal(qs.values_list("name").get(name="a"), ("a",), "values_list().get() returns the shaped tuple")
    t.equal(qs.count(), 3, "count()")
    t.equal(qs.exists(), True, "exists() on a non-empty queryset")
    t.equal(qs.filter(name="zzz").exists(), False, "exists() on an empty queryset")
    t.require(qs.first() is a and qs.last() is c, "first()/last()")


@case("T.R06.14")
def _order_by(t):
    from heldout_checker_app.models import Band, BandMember

    from modelcluster.queryset import FakeQuerySet

    band_a, band_b = Band(name="A"), Band(name="B")
    x, y = BandMember(name="x", band=band_b), BandMember(name="y", band=band_a)
    nameless, w = BandMember(name=None, band=band_b), BandMember(name="w", band=band_a)
    qs = FakeQuerySet(BandMember, [x, y, nameless, w])
    t.same(qs.order_by("name"), [nameless, w, x, y], "ascending with the None name first")
    t.same([m for m in qs.order_by("-name") if m.name is not None], [y, x, w], "descending order of non-None names")
    ordered = list(qs.order_by("band__name", "-name"))
    t.same(ordered[:2], [y, w], "band__name then -name: band A rows first, y before w")
    t.same_set(ordered[2:], [x, nameless], "band__name then -name: band B rows last")
    t.same_set(qs.order_by("?"), [x, y, nameless, w], "'?' returns a permutation")


@case("T.R06.15")
def _values(t):
    from heldout_checker_app.models import Band, BandMember

    from modelcluster.queryset import FakeQuerySet

    band = Band(name="Bee")
    m1, m2 = BandMember(name="m1", age=30), BandMember(name="m2", age=31)
    band.members = [m1, m2]
    band.save()
    qs = FakeQuerySet(BandMember, [m1, m2])
    rows = list(qs.values())
    t.equal(len(rows), 2, "values() yields one dict per row")
    for field in BandMember._meta.concrete_fields:
        t.require(all(field.name in row or field.attname in row for row in rows), f"values() covers concrete field {field.name}")
    t.equal(rows[0].get("name"), "m1", "values() row content")
    t.equal(list(qs.values("name", "band", "band__name")),
            [{"name": "m1", "band": band.pk, "band__name": "Bee"}, {"name": "m2", "band": band.pk, "band__name": "Bee"}],
            "values() with FK and spanning names")
    t.equal(list(qs.values_list("name", "band")), [("m1", band.pk), ("m2", band.pk)], "values_list() tuples in field order")
    t.equal(list(qs.values_list("name", flat=True)), ["m1", "m2"], "values_list(flat=True)")
    t.raises(TypeError, lambda: list(qs.values_list("name", "band", flat=True)), "flat=True with two fields raises TypeError")


@case("T.R06.16")
def _distinct(t):
    from heldout_checker_app.models import Venue

    from modelcluster.queryset import FakeQuerySet

    v1, v2, v3 = Venue.objects.create(name="x", city="A"), Venue.objects.create(name="x", city="A"), Venue.objects.create(name="x", city="B")
    qs = FakeQuerySet(Venue, [v1, v2, v3])
    kept = list(qs.distinct())
    t.equal(len(kept), 2, "distinct() collapses rows differing only by pk")
    t.require(any(v is v3 for v in kept) and sum(1 for v in kept if v is v1 or v is v2) == 1, "distinct() keeps v3 and one of v1/v2")
    t.equal(len(list(qs.distinct("name"))), 1, "distinct('name')")


@case("T.R06.17")
def _none_all_sequence(t):
    from heldout_checker_app.models import Log

    from modelcluster.queryset import FakeQuerySet

    a, b, c = Log(name="a", score=1), Log(name="b", score=2), Log(name="c", score=3)
    qs = FakeQuerySet(Log, [a, b, c])
    t.equal(list(qs.none()), [], "none() is empty")
    t.equal(list(qs.none().filter(name="a").order_by("name").values("name")), [], "none() stays empty when chained")
    t.same(qs.all(), [a, b, c], "all() holds the same rows")
    t.equal(list(qs.filter(score__gt=0).order_by("-name").values_list("name", flat=True)), ["c", "b", "a"], "chains compose")
    t.same([row for row in qs], [a, b, c], "iteration")
    t.equal(len(qs), 3, "len()")
    t.require(qs[0] is a, "indexing")
    t.equal((bool(qs), bool(qs.none())), (True, False), "truthiness")


@case("T.R06.18")
def _prefetch_and_noops(t):
    from heldout_checker_app.models import Article, Author, Band, BandMember

    from modelcluster.queryset import FakeQuerySet

    loose = [BandMember(name="p"), BandMember(name="q")]
    qs = FakeQuerySet(BandMember, loose)
    for method, argument in (("select_related", "band"), ("only", "name"), ("defer", "name")):
        t.same(getattr(qs, method)(argument), loose, f"{method}() keeps the rows")

    def add_bands(start, stop):
        for i in range(start, stop):
            band = Band(name=f"band{i}")
            band.save()
            BandMember.objects.create(band=band, name=f"m{i}a")
            BandMember.objects.create(band=band, name=f"m{i}b")
            author = Author.objects.create(name=f"author{i}")
            article = Article(title=f"article{i}")
            article.save()
            _through(Article, "authors").objects.create(article=article, author=author)

    def members_loop(prefetch):
        bands = Band.objects.prefetch_related("members") if prefetch else Band.objects.all()
        return {band.name: _sorted_names(band.members.all()) for band in bands}

    def authors_loop(prefetch):
        articles = Article.objects.prefetch_related("authors") if prefetch else Article.objects.all()
        return {article.title: _names(article.authors.all()) for article in articles}

    counts = {}
    for size in (3, 5):
        add_bands(len(counts) and 3, size)
        counts[size] = {}
        for label, loop in (("members", members_loop), ("authors", authors_loop)):
            prefetched, with_prefetch = _query_count(lambda: loop(True))
            plain, without_prefetch = _query_count(lambda: loop(False))
            t.equal(prefetched, plain, f"prefetch_related('{label}') returns the right related objects for {size} parents")
            counts[size][label] = (with_prefetch, without_prefetch)
    for label in ("members", "authors"):
        t.equal(counts[3][label][0], counts[5][label][0], f"prefetch_related('{label}') query count does not grow with parents")
        t.require(counts[5][label][0] < counts[5][label][1], f"prefetch_related('{label}') issues fewer queries: {counts[5][label]}")
    bands = list(Band.objects.all())
    fake = FakeQuerySet(Band, bands)
    returned = fake.prefetch_related("members")
    target = list(returned if returned is not None else fake)
    names, queries = _query_count(lambda: {band.name: _sorted_names(band.members.all()) for band in target})
    t.equal(names, members_loop(False), "FakeQuerySet.prefetch_related populated the right members")
    t.equal(queries, 0, "reads after FakeQuerySet.prefetch_related issue no queries")


# ============================================================================ clusterable-model-save-copy

@case("T.R07.01")
def _constructor(t):
    from heldout_checker_app.models import Album, Article, Author, Band, BandMember

    from modelcluster.models import ClusterableModel

    t.require(ClusterableModel._meta.abstract, "ClusterableModel is abstract")
    m1, m2, al1 = BandMember(name="m1"), BandMember(name="m2"), Album(title="al1")
    band = Band(name="The Beatles", members=[m1, m2], albums=[al1])
    t.equal(band.name, "The Beatles", "normal field kwargs still apply")
    t.same_set(band.members.all(), [m1, m2], "members kwarg")
    t.require(m1.band is band and m2.band is band, "children point at the instance")
    t.same(band.albums.all(), [al1], "albums kwarg")
    a1, a2 = Author.objects.create(name="a1"), Author.objects.create(name="a2")
    article = Article(title="t", authors=[a1, a2])
    t.equal(sorted(a.pk for a in article.authors.all()), sorted([a1.pk, a2.pk]), "parental m2m kwarg")
    t.equal((Band.objects.count(), BandMember.objects.count(), Album.objects.count(), Article.objects.count(),
             _through(Article, "authors").objects.count()), (0, 0, 0, 0, 0), "the constructor writes nothing")


@case("T.R07.02")
def _save_commits_everything(t):
    from heldout_checker_app.models import Album, Band, BandMember, Genre

    g1 = Genre.objects.create(name="g1")
    band = Band(name="b")
    band.members = [BandMember(name="m1"), BandMember(name="m2")]
    band.albums = [Album(title="al1")]
    band.genres = [g1]
    band.save()
    t.equal(Band.objects.filter(pk=band.pk).count(), 1, "band row")
    t.equal(sorted(_rows(BandMember, band_id=band.pk).values_list("name", flat=True)), ["m1", "m2"], "member rows")
    t.equal(list(_rows(Album, band_id=band.pk).values_list("title", flat=True)), ["al1"], "album row")
    t.equal(list(_through(Band, "genres").objects.filter(band_id=band.pk).values_list("genre_id", flat=True)), [g1.pk], "genre link")


@case("T.R07.03")
def _save_update_fields(t):
    from heldout_checker_app.models import Album, Band, BandMember

    band = Band(name="old")
    band.members = [BandMember(name="m1")]
    band.albums = [Album(title="a1")]
    band.save()
    band.name = "new"
    band.members = [BandMember(name="m2")]
    band.albums = [Album(title="a2")]
    band.save(update_fields=["name", "members"])
    t.equal(Band.objects.get(pk=band.pk).name, "new", "update_fields writes name")
    t.equal(list(_rows(BandMember, band=band).values_list("name", flat=True)), ["m2"], "update_fields commits members")
    t.equal(list(_rows(Album, band=band).values_list("title", flat=True)), ["a1"], "albums untouched by the first call")
    band.save(update_fields=["albums"])
    t.equal(list(_rows(Album, band=band).values_list("title", flat=True)), ["a2"], "update_fields=['albums'] commits albums")


@case("T.R07.04")
def _child_relations_helper(t):
    from heldout_checker_app.models import MenuItem, Place, Restaurant, Review

    from modelcluster.models import get_all_child_relations

    relations = {rel.get_accessor_name(): rel for rel in get_all_child_relations(Restaurant)}
    t.equal(set(relations), {"reviews", "menu_items"}, "Restaurant: own and inherited ParentalKey relations, no plain FK")
    t.equal({rel.get_accessor_name() for rel in get_all_child_relations(Place)}, {"reviews"}, "Place: reviews only")
    t.require(relations["reviews"].related_model is Review and relations["menu_items"].related_model is MenuItem, "related_model")
    t.require(relations["reviews"].field is Review._meta.get_field("place"), "field is the ParentalKey")
    t.require(relations["menu_items"].field is MenuItem._meta.get_field("restaurant"), "field is the ParentalKey (menu_items)")
    t.require(all(getattr(rel, "name", None) for rel in relations.values()), "entries expose name")


@case("T.R07.05")
def _m2m_relations_helper(t):
    from heldout_checker_app.models import Article, FeatureArticle

    from modelcluster.fields import ParentalManyToManyField
    from modelcluster.models import get_all_child_m2m_relations

    article = get_all_child_m2m_relations(Article)
    feature = get_all_child_m2m_relations(FeatureArticle)
    t.equal(sorted(field.name for field in article), ["authors"], "Article: parental m2m only")
    t.equal(sorted(field.name for field in feature), ["authors", "categories"], "FeatureArticle: inherited and own")
    t.require(all(isinstance(field, ParentalManyToManyField) for field in article + feature), "entries are field instances")


@case("T.R07.14")
def _copy_cluster(t):
    from heldout_checker_app.models import Album, Band, BandMember, Fan, Genre, Song

    g1, f1 = Genre.objects.create(name="g1"), Fan.objects.create(name="f1")
    band = Band(name="B")
    m1, m2, al1 = BandMember(name="m1"), BandMember(name="m2"), Album(title="al1")
    al1.songs = [Song(title="s1")]
    band.members = [m1, m2]
    band.albums = [al1]
    band.genres = [g1]
    band.save()
    band.fans.add(f1)
    original_pks = sorted([m1.pk, m2.pk])
    copy, child_map = band.copy_cluster()
    t.require(copy.pk is None, "the copy is unsaved")
    t.equal(copy.name, "B", "field data copied")
    members = list(copy.members.all())
    t.equal(_sorted_names(members), ["m1", "m2"], "members copied")
    t.require(all(m.pk is None and m.band is copy and m is not m1 and m is not m2 for m in members),
              "copied members are new instances with pk None pointing at the copy")
    albums = list(copy.albums.all())
    t.require(len(albums) == 1 and albums[0].pk is None and albums[0].title == "al1", "album copied with pk None")
    songs = list(albums[0].songs.all())
    t.require(len(songs) == 1 and songs[0].pk is None and songs[0].title == "s1", "songs copied recursively with pk None")
    t.equal([g.pk for g in copy.genres.all()], [g1.pk], "parental m2m copied")
    t.equal(sorted(m.pk for m in band.members.all()), original_pks, "original members unchanged")
    t.equal(BandMember.objects.count(), 2, "copying wrote nothing")
    for member in (m1, m2):
        entries = _map_entries(child_map, "members", member.pk)
        t.require(len(entries) == 1 and any(entries[0] is m for m in members) and entries[0].name == member.name,
                  f"child map maps (members, {member.pk}) to the copy of {member.name}")
    copy.save()
    t.equal(list(copy.fans.all()), [], "plain m2m is not copied")


@case("T.R07.15")
def _copy_child_relation(t):
    from django.db import IntegrityError
    from heldout_checker_app.models import Band, BandMember

    from modelcluster.models import get_all_child_relations

    source = Band(name="S")
    m1, m2 = BandMember(name="m1"), BandMember(name="m2")
    source.members = [m1, m2]
    target = Band(name="T")
    target.members = [BandMember(name="t1")]
    source.copy_child_relation("members", target)
    copies = list(target.members.all())
    t.equal(_sorted_names(copies), ["m1", "m2"], "default overwrites the target relation")
    t.require(all(c.pk is None and c.band is target and c is not m1 and c is not m2 for c in copies), "copies are new, unsaved, on target")
    rel = [r for r in get_all_child_relations(Band) if r.get_accessor_name() == "members"][0]
    fresh = Band(name="T2")
    fresh.members = [BandMember(name="t1")]
    source.copy_child_relation(rel, fresh, append=True)
    t.equal(_sorted_names(fresh.members.all()), ["m1", "m2", "t1"], "append=True with a relation object keeps existing children")
    saved = Band(name="ST")
    saved.save()
    source.copy_child_relation("members", saved, commit=True)
    t.equal(sorted(_rows(BandMember, band=saved).values_list("name", flat=True)), ["m1", "m2"], "commit=True writes rows")
    t.raises(IntegrityError, lambda: source.copy_child_relation("members", Band(name="UT"), commit=True),
             "commit=True on an unsaved target raises IntegrityError")


@case("T.R07.16")
def _copy_child_relation_map(t):
    from heldout_checker_app.models import Band, BandMember

    source = Band(name="S")
    m_saved = BandMember(name="saved")
    source.members = [m_saved]
    source.save()
    m_new = BandMember(name="new")
    source.members.add(m_new)
    result = source.copy_child_relation("members", Band(name="T"))
    saved_entries = _map_entries(result, "members", m_saved.pk)
    t.require(len(saved_entries) == 1 and saved_entries[0].name == "saved" and saved_entries[0].pk is None,
              f"(members, {m_saved.pk}) maps to the copy of the stored member: {result!r}")
    none_entries = _map_entries(result, "members", None)
    t.require(len(none_entries) == 1 and isinstance(none_entries[0], list), f"(members, None) maps to a list: {result!r}")
    t.equal(_names(none_entries[0]), ["new"], "the list holds the copy of the unsaved member")


@case("T.R07.17")
def _copy_all_child_relations(t):
    from heldout_checker_app.models import Album, Band, BandMember

    source = Band(name="S")
    source.members = [BandMember(name="m1")]
    source.albums = [Album(title="al1")]
    target = Band(name="T")
    keep = Album(title="keep")
    target.albums = [keep]
    result = source.copy_all_child_relations(target, exclude=["albums"])
    t.equal(_names(target.members.all()), ["m1"], "members copied")
    t.same(target.albums.all(), [keep], "excluded albums untouched")
    t.require(result and {_relation_name(key[0]) for key in result} == {"members"}, f"map has members entries only: {result!r}")
    fresh = Band(name="F")
    result = source.copy_all_child_relations(fresh)
    t.equal(_names(fresh.members.all()), ["m1"], "members copied without exclude")
    t.equal([a.title for a in fresh.albums.all()], ["al1"], "albums copied without exclude")
    t.equal({_relation_name(key[0]) for key in result}, {"members", "albums"}, "map merges both relations")


@case("T.integration.copy-then-save")
def _copy_then_save(t):
    from heldout_checker_app.models import Album, Band, BandMember, Genre, Song

    g1 = Genre.objects.create(name="g1")
    band = Band(name="B")
    album = Album(title="al1")
    album.songs = [Song(title="s1"), Song(title="s2")]
    band.members = [BandMember(name="m1"), BandMember(name="m2")]
    band.albums = [album]
    band.genres = [g1]
    band.save()
    before = sorted(_rows(BandMember, band=band).values_list("pk", "name"))
    copy, child_map = band.copy_cluster()
    copy.name = "Copy"
    copy.save()
    t.equal(sorted(_rows(BandMember, band=band).values_list("pk", "name")), before, "original member rows unchanged")
    t.equal(sorted(_rows(BandMember, band=copy).values_list("name", flat=True)), ["m1", "m2"], "copied member rows")
    t.equal(list(_rows(Album, band=copy).values_list("title", flat=True)), ["al1"], "copied album row")
    t.equal(sorted(_rows(Song, album__band=copy).values_list("title", flat=True)), ["s1", "s2"], "copied song rows")
    t.equal(sorted(_rows(Song, album__band=band).values_list("title", flat=True)), ["s1", "s2"], "original song rows")
    t.equal(list(_through(Band, "genres").objects.filter(band=copy).values_list("genre_id", flat=True)), [g1.pk], "copied m2m link")
    t.require(child_map, "copy_cluster returned a non-empty child map")
    for key, value in child_map.items():
        values = value if isinstance(value, list) else [value]
        t.require(all(v.pk is not None and v.pk != key[1] for v in values), f"map value for {key!r} now has a new pk")
    other = Band(name="O")
    other.save()
    band.copy_all_child_relations(other, commit=True)
    t.equal(sorted(_rows(BandMember, band=other).values_list("name", flat=True)), ["m1", "m2"], "commit=True member rows")
    t.equal(_rows(Album, band=other).count(), 1, "commit=True album row")
    t.equal(_rows(Song, album__band=other).count(), 2, "commit=True song rows")


# ============================================================================ clusterable-model-serialization

@case("T.R07.06")
def _serializable_data(t):
    from django.core.serializers.json import DjangoJSONEncoder
    from heldout_checker_app.models import Album, Band, BandMember, Genre, Song

    g1, g2 = Genre.objects.create(name="g1"), Genre.objects.create(name="g2")
    band = Band(name="B")
    m1, al1, s1 = BandMember(name="m1"), Album(title="al1"), Song(title="s1")
    al1.songs = [s1]
    band.members = [m1]
    band.albums = [al1]
    band.genres = [g1, g2]
    band.save()
    data = band.serializable_data()
    t.equal((data.get("pk"), data.get("name")), (band.pk, "B"), "pk and name")
    members = data.get("members")
    t.require(isinstance(members, list) and len(members) == 1, f"members list: {members!r}")
    t.equal((members[0].get("pk"), members[0].get("name")), (m1.pk, "m1"), "member dict")
    albums = data.get("albums")
    t.require(isinstance(albums, list) and len(albums) == 1 and albums[0].get("title") == "al1", f"albums list: {albums!r}")
    songs = albums[0].get("songs")
    t.require(isinstance(songs, list) and len(songs) == 1, f"album dict recurses into songs: {albums[0]!r}")
    t.equal((songs[0].get("pk"), songs[0].get("title")), (s1.pk, "s1"), "song dict")
    t.equal(sorted(data.get("genres") or []), sorted([g1.pk, g2.pk]), "parental m2m as pks")
    t.require(isinstance(json.dumps(data, cls=DjangoJSONEncoder), str), "json.dumps with DjangoJSONEncoder")


@case("T.R07.07")
def _serializable_inherited(t):
    from heldout_checker_app.models import Place, Restaurant

    restaurant = Restaurant(name="Joes", serves_hot_dogs=True)
    restaurant.save()
    data = restaurant.serializable_data()
    t.equal(data.get("name"), "Joes", "field inherited from the multi-table parent")
    t.equal(data.get("serves_hot_dogs"), True, "own field")
    place_id = Place.objects.get(pk=restaurant.pk).pk
    t.equal(data.get("pk"), place_id, "pk is the id shared up the chain")


@case("T.R07.08")
def _serialize_keys(t):
    from heldout_checker_app.models import Band, BandMember, Genre, Studio, StudioEngineer, StudioNote

    band = Band(name="B")
    band.save()
    band.members = [BandMember(name="m", secret="s")]
    member = band.serializable_data()["members"][0]
    t.equal(member.get("band"), band.pk, "FK keyed by field name with the pk value")
    t.require("favourite_restaurant" in member and member["favourite_restaurant"] is None, f"null FK under its field name: {member!r}")
    t.require(not {"band_id", "favourite_restaurant_id", "secret"} & set(member), f"no attname keys and no serialize=False field: {member!r}")
    g1 = Genre.objects.create(name="g1")
    studio = Studio(name="S")
    studio.hidden_genres = [g1]
    studio.notes = [StudioNote(text="n")]
    studio.engineers = [StudioEngineer(name="e")]
    studio.save()
    data = studio.serializable_data()
    t.require("hidden_genres" not in data, "serialize=False parental m2m omitted")
    t.require("notes" not in data, "child relation whose ParentalKey is serialize=False omitted")
    t.require("engineers" in data, "ordinary child relation present")


@case("T.R07.09")
def _json_round_trip(t):
    from django.core.serializers.json import DjangoJSONEncoder
    from heldout_checker_app.models import Band, BandMember, Restaurant

    band = Band(name="B")
    band.members = [BandMember(name="m1"), BandMember(name="m2")]
    band.save()
    expected_members = sorted((m.pk, m.name) for m in band.members.all())
    text = band.to_json()
    t.equal(json.loads(text), json.loads(json.dumps(band.serializable_data(), cls=DjangoJSONEncoder)), "to_json() content")
    for label, rebuilt in (("from_json", Band.from_json(text)), ("from_serializable_data", Band.from_serializable_data(json.loads(text)))):
        t.equal((rebuilt.pk, rebuilt.name), (band.pk, "B"), f"{label}: pk and fields")
        t.equal(sorted((m.pk, m.name) for m in rebuilt.members.all()), expected_members, f"{label}: members")
    original = Restaurant(name="R", serves_hot_dogs=True)
    original.save()
    rebuilt = Restaurant.from_serializable_data(original.serializable_data())
    t.equal((rebuilt.pk, rebuilt.place_ptr_id, rebuilt.id), (original.id,) * 3, "pk, parent link and root pk attribute")


@case("T.R07.10")
def _dangling_fks(t):
    from heldout_checker_app.models import Company, Tour, TourStop

    keep = Company.objects.create(name="keep")
    gone = [Company.objects.create(name=f"gone{i}") for i in range(4)]
    tour_a = Tour(name="a")
    tour_a.stops = [TourStop(name="s", venue=keep, sponsor=gone[0])]
    tour_a.save()
    data_a = tour_a.serializable_data()
    tour_b = Tour(name="b")
    tour_b.stops = [TourStop(name="s1", venue=keep), TourStop(name="s2", venue=gone[1])]
    tour_b.save()
    data_b = tour_b.serializable_data()
    tour_c = Tour(name="c", sponsor=gone[2])
    tour_c.save()
    data_c = tour_c.serializable_data()
    tour_d = Tour(name="d", headliner=gone[3])
    tour_d.save()
    data_d = tour_d.serializable_data()
    Company.objects.filter(pk__in=[c.pk for c in gone]).delete()
    rebuilt = Tour.from_serializable_data(data_a, check_fks=True)
    stops = list(rebuilt.stops.all())
    t.require(len(stops) == 1 and stops[0].sponsor_id is None and stops[0].venue_id == keep.pk,
              "(a) child with a dangling SET_NULL FK kept with the FK None")
    rebuilt = Tour.from_serializable_data(data_b, check_fks=True)
    t.equal(_names(rebuilt.stops.all()), ["s1"], "(b) child with a dangling CASCADE FK dropped")
    t.equal(Tour.from_serializable_data(data_c, check_fks=True).sponsor_id, None, "(c) dangling SET_NULL base FK nullified")
    lenient = Tour.from_serializable_data(data_d, check_fks=True, strict_fks=False)
    t.require(lenient is not None and lenient.headliner_id is None, "(d) strict_fks=False nullifies a dangling CASCADE base FK")
    t.equal(Tour.from_serializable_data(data_d, check_fks=True, strict_fks=True), None, "(d) strict_fks=True returns None")


@case("T.R07.11")
def _deserialize_ordering(t):
    from heldout_checker_app.models import Choir

    data = {"pk": None, "name": "C", "singers": [{"pk": None, "name": "Zed"}, {"pk": None, "name": "Amy"}]}
    choir = Choir.from_serializable_data(data)
    t.equal(_names(choir.singers.all()), ["Amy", "Zed"], "deserialized children re-sorted by Meta.ordering")


@case("T.R07.12")
def _datetime_serialization(t):
    import datetime

    from heldout_checker_app.models import Event

    utc = datetime.timezone.utc
    cases = [
        ("naive", datetime.datetime(2024, 1, 1, 9, 0), datetime.datetime(2024, 1, 1, 0, 0, tzinfo=utc)),
        ("aware", datetime.datetime(2024, 1, 1, 12, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=2))),
         datetime.datetime(2024, 1, 1, 10, 0, tzinfo=utc)),
    ]
    for label, value, instant in cases:
        text = Event(name=label, when=value).to_json()
        stored = json.loads(text)["when"]
        t.require(isinstance(stored, str) and stored.endswith("Z"), f"{label}: ISO string ending in Z, got {stored!r}")
        t.equal(datetime.datetime.fromisoformat(stored[:-1] + "+00:00"), instant, f"{label}: stored UTC instant")
        back = Event.from_json(text).when
        t.equal(back, instant, f"{label}: deserialized instant")
        t.equal(back.utcoffset(), datetime.timedelta(hours=9), f"{label}: deserialized in the current zone (Asia/Seoul)")
    text = Event(name="none", when=None).to_json()
    t.equal(json.loads(text)["when"], None, "None datetime serializes as null")
    t.equal(Event.from_json(text).when, None, "null deserializes as None")


@case("T.R07.13")
def _filefield_round_trip(t):
    from django.core.files.base import ContentFile
    from heldout_checker_app.models import Document

    document = Document(title="d")
    document.file.save("a.txt", ContentFile(b"hello"), save=False)
    t.equal(document.file.name, "docs/a.txt", "file stored under upload_to")
    rebuilt = Document.from_json(document.to_json())
    t.equal(rebuilt.file.name, "docs/a.txt", "file name survives the round trip")
    with rebuilt.file.open("rb") as handle:
        t.equal(handle.read(), b"hello", "file contents readable after the round trip")


def _normalize_cluster(data):
    """Sort m2m pk lists so database read order cannot matter."""
    if isinstance(data, dict):
        return {key: _normalize_cluster(value) for key, value in data.items()}
    if isinstance(data, list):
        items = [_normalize_cluster(item) for item in data]
        return sorted(items) if all(isinstance(item, int) for item in items) else items
    return data


@case("T.integration.json-round-trip")
def _json_round_trip_integration(t):
    import datetime

    from django.core.serializers.json import DjangoJSONEncoder
    from heldout_checker_app.models import Chef, Cuisine, Ingredient, MenuItem, Place, Restaurant, Review

    chef = Chef.objects.create(name="c")
    cu1, cu2 = Cuisine.objects.create(name="cu1"), Cuisine.objects.create(name="cu2")
    restaurant = Restaurant(name="R", serves_hot_dogs=True, proprietor=chef,
                            opened_at=datetime.datetime(2023, 5, 1, 12, 0, tzinfo=datetime.timezone.utc))
    zed, amy = MenuItem(name="Zed"), MenuItem(name="Amy")
    zed.ingredients = [Ingredient(name="i1")]
    amy.ingredients = [Ingredient(name="i2"), Ingredient(name="i3")]
    restaurant.menu_items = [zed, amy]
    restaurant.reviews = [Review(author="x")]
    restaurant.cuisines = [cu1, cu2]
    restaurant.save()
    text = restaurant.to_json()
    expected = _normalize_cluster(json.loads(text))
    t.equal(expected.get("name"), "R", "inherited field serialized")
    rebuilt = Restaurant.from_json(text)
    as_json = _normalize_cluster(json.loads(json.dumps(rebuilt.serializable_data(), cls=DjangoJSONEncoder)))
    t.equal(as_json, expected, "the rebuilt instance serializes identically")
    t.equal(_names(rebuilt.menu_items.all()), ["Amy", "Zed"], "children follow Meta.ordering")
    t.equal((rebuilt.pk, rebuilt.place_ptr_id, rebuilt.id), (restaurant.pk,) * 3, "every pk attribute equals the original id")
    counts = lambda: (Place.objects.count(), Restaurant.objects.count(), MenuItem.objects.count(), Ingredient.objects.count(),
                      Review.objects.count(), _through(Restaurant, "cuisines").objects.count())
    before = counts()
    rebuilt.save()
    t.equal(counts(), before, "saving the rebuilt cluster creates no duplicate rows")
    t.equal(Place.objects.get(pk=restaurant.pk).name, "R", "stored name unchanged")
    stored = _normalize_cluster(json.loads(json.dumps(Restaurant.objects.get(pk=restaurant.pk).serializable_data(), cls=DjangoJSONEncoder)))
    t.equal(stored, expected, "the stored cluster matches the original")


# ============================================================================ cluster-forms

def _management(prefix, total, initial=0):
    return {f"{prefix}-TOTAL_FORMS": str(total), f"{prefix}-INITIAL_FORMS": str(initial)}


def _model_fields(form):
    return {name for name in form.fields if name not in ("id", "DELETE", "ORDER")}


@case("T.R08.01")
def _transient_formset(t):
    from heldout_checker_app.models import BandMember

    from modelcluster.forms import transientmodelformset_factory

    FormSet = transientmodelformset_factory(BandMember, fields=["name"])
    formset = FormSet({**_management("form", 2), "form-0-name": "A", "form-1-name": "B"})
    t.require(formset.is_valid(), f"bound transient formset is valid: {formset.errors} {formset.non_form_errors()}")
    objects = formset.save(commit=False)
    t.equal(sorted(o.name for o in objects), ["A", "B"], "save(commit=False) returns the new instances")
    t.require(all(o.pk is None for o in objects), "returned instances are unsaved")
    t.equal(BandMember.objects.count(), 0, "save(commit=False) writes nothing")


@case("T.R08.02")
def _childformset_factory_signature(t):
    from django.forms import ModelForm, Textarea
    from heldout_checker_app.models import Band, BandMember

    from modelcluster.forms import childformset_factory

    every = childformset_factory(
        Band, BandMember, form=ModelForm, fk_name="band", fields=["name", "age"], exclude=["age"], extra=2, can_order=True,
        can_delete=True, max_num=5, validate_max=False, min_num=0, validate_min=False, widgets={"name": Textarea},
        inherit_kwargs=[], formsets=None, exclude_formsets=None, formfield_callback=None)
    t.require(every is not None, "childformset_factory accepts the documented keywords")
    FS = childformset_factory(Band, BandMember, fields=["name"])
    everything = childformset_factory(Band, BandMember, exclude=[])
    band = Band(name="b")
    band.save()
    BandMember.objects.create(band=band, name="x")
    BandMember.objects.create(band=band, name="y")
    for label, factory in (("fields=['name']", FS), ("exclude=[]", everything)):
        formset = factory(instance=band)
        t.require(all("band" not in form.fields for form in formset.forms), f"{label}: the ParentalKey is not a form field")
    formset = FS(instance=band)
    t.equal(len(formset.forms), 5, "two existing children plus three extra forms")
    t.equal(sorted(form.instance.name for form in formset.forms[:2]), ["x", "y"], "existing children come first")
    t.require(all(form.instance.pk is None for form in formset.forms[2:]), "followed by blank extra forms")


def _child_data(m1, m2):
    return {**_management("form", 3, 2), "form-0-id": str(m1.pk), "form-0-name": "m1-edited",
            "form-1-id": str(m2.pk), "form-1-name": "m2", "form-1-DELETE": "on", "form-2-name": "m3"}


@case("T.R08.03")
def _child_formset_save(t):
    from heldout_checker_app.models import Band, BandMember

    from modelcluster.forms import childformset_factory

    FS = childformset_factory(Band, BandMember, fields=["name"])
    band = Band(name="b")
    m1, m2 = BandMember(name="m1"), BandMember(name="m2")
    band.members = [m1, m2]
    band.save()
    formset = FS(_child_data(m1, m2), instance=band)
    t.require(formset.is_valid(), f"child formset valid: {formset.errors} {formset.non_form_errors()}")
    formset.save(commit=False)
    t.equal(sorted(_rows(BandMember, band=band).values_list("name", flat=True)), ["m1", "m2"], "commit=False leaves the DB unchanged")
    t.equal(_sorted_names(band.members.all()), ["m1-edited", "m3"], "commit=False stages edit, add and delete in memory")
    band.save()
    t.equal(sorted(_rows(BandMember, band=band).values_list("name", flat=True)), ["m1-edited", "m3"], "band.save() applies them")
    other = Band(name="o")
    n1, n2 = BandMember(name="m1"), BandMember(name="m2")
    other.members = [n1, n2]
    other.save()
    formset = FS(_child_data(n1, n2), instance=Band.objects.get(pk=other.pk))
    t.require(formset.is_valid(), f"second child formset valid: {formset.errors}")
    formset.save(commit=True)
    t.equal(sorted(_rows(BandMember, band=other).values_list("name", flat=True)), ["m1-edited", "m3"], "commit=True writes immediately")


@case("T.R08.04")
def _validate_max_min(t):
    from heldout_checker_app.models import Band, BandMember

    from modelcluster.forms import childformset_factory

    three = {**_management("form", 3), "form-0-name": "a", "form-1-name": "b", "form-2-name": "c"}
    one = {**_management("form", 1), "form-0-name": "a"}

    def bound(data, **options):
        return childformset_factory(Band, BandMember, fields=["name"], **options)(data, instance=Band(name="b"))

    t.require(bound(three, max_num=2).is_valid(), "max_num without validate_max does not invalidate")
    formset = bound(three, max_num=2, validate_max=True)
    t.require(not formset.is_valid(), "validate_max invalidates three forms over max_num=2")
    t.require("too_many_forms" in [e.code for e in formset.non_form_errors().as_data()], "non-form error code too_many_forms")
    t.require(bound(one, min_num=2).is_valid(), "min_num without validate_min does not invalidate")
    formset = bound(one, min_num=2, validate_min=True)
    t.require(not formset.is_valid(), "validate_min invalidates one form under min_num=2")
    t.require("too_few_forms" in [e.code for e in formset.non_form_errors().as_data()], "non-form error code too_few_forms")


@case("T.R08.05")
def _sort_order_field(t):
    from heldout_checker_app.models import Gig, GigSong

    from modelcluster.forms import childformset_factory

    FS = childformset_factory(Gig, GigSong, fields=["title"])
    gig = Gig(name="g")
    t.require("ORDER" in FS(instance=gig).forms[0].fields, "sort_order_field enables an ORDER field")
    formset = FS({**_management("form", 2), "form-0-title": "first", "form-0-ORDER": "2",
                  "form-1-title": "second", "form-1-ORDER": "1"}, instance=gig)
    t.require(formset.is_valid(), f"formset valid: {formset.errors}")
    formset.save(commit=False)
    t.equal({song.title: song.sort_order for song in gig.gig_songs.all()}, {"first": 2, "second": 1}, "ORDER written to sort_order")


@case("T.R08.06")
def _nested_childformset(t):
    from heldout_checker_app.models import Album, Band, Song

    from modelcluster.forms import ClusterForm, childformset_factory

    band = Band(name="b")
    band.save()
    FS = childformset_factory(Band, Album, form=ClusterForm, formsets=["songs"], fields=["title"])
    unbound = FS(instance=band)
    album_form = unbound.forms[0]
    t.require("songs" in getattr(album_form, "formsets", {}), "album forms expose a songs formset")
    songs_prefix = album_form.formsets["songs"].prefix
    data = {**_management(unbound.prefix, 1), album_form.add_prefix("title"): "LP", **_management(songs_prefix, 2),
            f"{songs_prefix}-0-title": "s1", f"{songs_prefix}-1-title": "s2"}
    formset = FS(data, instance=band)
    t.require(all("songs" in form.formsets for form in formset.forms), "every bound album form exposes songs")
    t.require(formset.is_valid(), f"nested formset valid: {formset.errors}")
    formset.save(commit=False)
    band.save()
    t.equal(list(_rows(Album, band=band).values_list("title", flat=True)), ["LP"], "album row")
    t.equal(sorted(_rows(Song, album__band=band).values_list("title", flat=True)), ["s1", "s2"], "nested song rows")


@case("T.R08.07")
def _default_prefixes(t):
    from heldout_checker_app.models import Band, BandMember

    from modelcluster.forms import ClusterForm, childformset_factory

    FS = childformset_factory(Band, BandMember, fields=["name"])
    formset = FS({**_management("form", 1), "form-0-name": "x"}, instance=Band(name="b"))
    t.equal(formset.prefix, "form", "standalone child formset prefix")
    t.require(formset.is_valid(), f"bound with form- keys: {formset.errors} {formset.non_form_errors()}")
    t.equal(formset.forms[0].cleaned_data.get("name"), "x", "reads form-0-name")

    class BandForm(ClusterForm):
        class Meta:
            model = Band
            fields = ["name"]
            formsets = ["members"]

    form = BandForm({"name": "b", **_management("members", 1), "members-0-name": "y"}, instance=Band())
    t.equal(form.formsets["members"].prefix, "members", "ClusterForm-managed formset prefix is the accessor name")
    t.require(form.is_valid(), "ClusterForm bound with members- keys is valid")
    t.equal(form.formsets["members"].forms[0].cleaned_data.get("name"), "y", "reads members-0-name")


@case("T.R08.08")
def _clusterform_meta_formsets(t):
    from django.forms import Textarea
    from heldout_checker_app.models import Album, Band

    from modelcluster.forms import ClusterForm

    class AlbumClusterForm(ClusterForm):
        class Meta:
            model = Album
            fields = ["title"]

    class FormA(ClusterForm):
        class Meta:
            model = Band
            fields = ["name"]
            formsets = ["members"]

    class FormB(ClusterForm):
        class Meta:
            model = Band
            fields = ["name"]
            formsets = {"members": {"fields": ["name"], "widgets": {"name": Textarea}},
                        "albums": {"form": AlbumClusterForm, "formsets": ["songs"]}}

    class FormC(ClusterForm):
        class Meta:
            model = Band
            fields = ["name"]
            formsets = {"members": {"formset_name": "records"}}

    class FormD(ClusterForm):
        class Meta:
            model = Band
            fields = ["name"]

    t.equal(set(FormA.formsets), {"members"}, "list option builds members only")
    form_b = FormB(instance=Band(name="x"))
    member_form = form_b.formsets["members"].forms[0]
    t.equal(_model_fields(member_form), {"name"}, "dict option fields")
    t.require(isinstance(member_form.fields["name"].widget, Textarea), "dict option widgets")
    album_form = form_b.formsets["albums"].forms[0]
    t.require(isinstance(album_form, AlbumClusterForm), "dict option form")
    t.require("songs" in album_form.formsets, "dict option formsets nests songs")
    t.require(FormC(instance=Band(name="x")) is not None, "formset_name option accepted")
    t.equal(FormD.formsets, {}, "no formsets configured builds none")
    t.equal(FormD(instance=Band()).formsets, {}, "instance formsets empty when none configured")


@case("T.R08.09")
def _exclude_formsets(t):
    from heldout_checker_app.models import Band

    from modelcluster.forms import ClusterForm

    class BandForm(ClusterForm):
        class Meta:
            model = Band
            fields = ["name"]
            exclude_formsets = ["albums"]

    t.equal(set(BandForm.formsets), {"members"}, "exclude_formsets builds every other child relation")
    t.equal(set(BandForm(instance=Band()).formsets), {"members"}, "instance formsets match")


@case("T.R08.10")
def _child_widgets(t):
    from django.forms import Textarea, TextInput
    from heldout_checker_app.models import Band

    from modelcluster.forms import ClusterForm

    class BandForm(ClusterForm):
        class Meta:
            model = Band
            fields = ["name"]
            formsets = ["members"]
            widgets = {"name": TextInput(attrs={"class": "parent"}), "members": {"name": Textarea}}

    form = BandForm(instance=Band())
    widget = form.fields["name"].widget
    t.require(isinstance(widget, TextInput) and widget.attrs.get("class") == "parent", "parent widget override")
    t.require(all(isinstance(f.fields["name"].widget, Textarea) for f in form.formsets["members"].forms),
              "child-relation key in Meta.widgets applies to the member forms")


@case("T.R08.11")
def _inherited_relations_in_form(t):
    from heldout_checker_app.models import Restaurant

    from modelcluster.forms import ClusterForm

    class ExcludingForm(ClusterForm):
        class Meta:
            model = Restaurant
            fields = ["name"]
            exclude_formsets = ["menu_items"]

    class ListingForm(ClusterForm):
        class Meta:
            model = Restaurant
            fields = ["name"]
            formsets = ["reviews", "menu_items"]

    t.equal(set(ExcludingForm.formsets), {"reviews"}, "inherited reviews relation included")
    t.equal(set(ListingForm.formsets), {"reviews", "menu_items"}, "inherited and own relations by name")
    t.equal(set(ListingForm(instance=Restaurant()).formsets), {"reviews", "menu_items"}, "instance formsets")


@case("T.R08.12")
def _formsets_attributes(t):
    from django.forms.formsets import BaseFormSet
    from heldout_checker_app.models import Band

    from modelcluster.forms import ClusterForm

    class BandForm(ClusterForm):
        class Meta:
            model = Band
            fields = ["name"]
            formsets = ["members", "albums"]

    class NoFormsetForm(ClusterForm):
        class Meta:
            model = Band
            fields = ["name"]

    t.require(isinstance(BandForm.formsets, dict) and set(BandForm.formsets) == {"members", "albums"}, "class formsets keys")
    t.require(all(isinstance(v, type) and issubclass(v, BaseFormSet) for v in BandForm.formsets.values()), "class formsets are classes")
    t.require(NoFormsetForm.formsets == {} and not NoFormsetForm.formsets, "no configured formsets: empty and falsy")
    form = BandForm(instance=Band())
    t.equal(set(form.formsets), {"members", "albums"}, "instance formsets keys")
    t.require(all(isinstance(v, BaseFormSet) for v in form.formsets.values()), "instance formsets are formset instances")
    t.equal(len(form.formsets["members"].forms), 3, "three extra forms by default")


@case("T.R08.13")
def _composite_validation(t):
    from heldout_checker_app.models import Band, UBand

    from modelcluster.forms import ClusterForm

    class BandForm(ClusterForm):
        class Meta:
            model = Band
            fields = ["name"]
            formsets = {"members": {"fields": ["name", "age"]}}

    def band_data(name, members, deleted=()):
        data = {"name": name, **_management("members", len(members))}
        for index, (member_name, age) in enumerate(members):
            data[f"members-{index}-name"], data[f"members-{index}-age"] = member_name, age
            if index in deleted:
                data[f"members-{index}-DELETE"] = "on"
        return data

    t.require(not BandForm(band_data("b", [("ok", "1"), ("", "2")]), instance=Band()).is_valid(), "(a) invalid member form")
    t.require(not BandForm(band_data("", [("ok", "1")]), instance=Band()).is_valid(), "(b) invalid parent form")
    for relation in ("ut_members", "uc_members"):
        class UForm(ClusterForm):
            class Meta:
                model = UBand
                fields = ["name"]
                formsets = [relation]

        def u_data(first, second):
            return {"name": "u", **_management(relation, 2), f"{relation}-0-name": first, f"{relation}-1-name": second}

        form = UForm(u_data("dup", "dup"), instance=UBand())
        t.require(not form.is_valid(), f"({relation}) duplicate child names rejected")
        formset = form.formsets[relation]
        t.require(bool(formset.non_form_errors()) or any(f.errors for f in formset.forms), f"({relation}) the duplicate is reported")
        t.require(UForm(u_data("one", "two"), instance=UBand()).is_valid(), f"({relation}) distinct child names accepted")
    t.require(BandForm(band_data("b", [("ok", "1"), ("", "2")], deleted=(1,)), instance=Band()).is_valid(),
              "(e) a form marked DELETE is not validated")
    t.require(BandForm(band_data("b", [("x", "1"), ("y", "2")]), instance=Band()).is_valid(), "(f) all valid")


@case("T.R08.14")
def _render_media_multipart(t):
    from django import forms
    from django.utils.safestring import SafeString
    from heldout_checker_app.models import Band, Gallery

    from modelcluster.forms import ClusterForm

    class ParentWidget(forms.TextInput):
        class Media:
            js = ["parent.js"]

    class ChildWidget(forms.TextInput):
        class Media:
            js = ["child.js"]

    class BandForm(ClusterForm):
        class Meta:
            model = Band
            fields = ["name"]
            widgets = {"name": ParentWidget}
            formsets = {"members": {"fields": ["name"], "widgets": {"name": ChildWidget}}}

    class GalleryForm(ClusterForm):
        class Meta:
            model = Gallery
            fields = ["name"]
            formsets = ["photos"]

    form = BandForm(instance=Band())
    html = form.as_p()
    t.require(isinstance(html, SafeString), f"as_p() returns a SafeString, got {type(html)!r}")
    parent_at, child_at = html.find('id="id_name"'), html.find('id="id_members-0-name"')
    t.require(0 <= parent_at < child_at, "as_p() renders the parent fields before the member forms")
    media = str(form.media)
    t.require("parent.js" in media and "child.js" in media, f"media aggregates parent and child widgets: {media}")
    t.equal(form.is_multipart(), False, "no file fields: not multipart")
    t.equal(GalleryForm(instance=Gallery()).is_multipart(), True, "a child FileField makes the form multipart")


@case("T.R08.15")
def _inherit_kwargs(t):
    from heldout_checker_app.models import Band, BandMember

    from modelcluster.forms import ClusterForm

    band = Band(name="b")
    band.save()
    BandMember.objects.create(band=band, name="x")

    class PlainForm(ClusterForm):
        class Meta:
            model = Band
            fields = ["name"]
            formsets = {"members": {"fields": ["name"]}}

    class InheritingForm(ClusterForm):
        class Meta:
            model = Band
            fields = ["name"]
            formsets = {"members": {"fields": ["name"], "inherit_kwargs": ["label_suffix"]}}

    plain = PlainForm(instance=band, label_suffix="!!")
    t.equal(plain.label_suffix, "!!", "parent form receives the kwarg")
    t.require(all(f.label_suffix != "!!" for f in plain.formsets["members"].forms), "kwargs not propagated by default")
    inheriting = InheritingForm(instance=band, label_suffix="!!")
    t.require(all(f.label_suffix == "!!" for f in inheriting.formsets["members"].forms), "inherit_kwargs propagates label_suffix")


@case("T.R08.16", apps=("tags",))
def _clusterform_save(t):
    from heldout_checker_app.models import Author, Link
    from heldout_checker_tags.models import Post, PostComment, TaggedPost

    from modelcluster.forms import ClusterForm

    a1, a2, link = Author.objects.create(name="a1"), Author.objects.create(name="a2"), Link.objects.create(url="u")

    class PostForm(ClusterForm):
        class Meta:
            model = Post
            fields = ["title", "authors", "tags", "links"]
            formsets = {"comments": {"fields": ["text"]}}

    data = {"title": "T", "authors": [str(a1.pk), str(a2.pk)], "tags": "red, blue", "links": [str(link.pk)],
            **_management("comments", 1), "comments-0-text": "c1"}
    authors_through, links_through = _through(Post, "authors"), _through(Post, "links")
    form = PostForm(data, instance=Post())
    t.require(form.is_valid(), f"form valid: {form.errors}")
    obj = form.save(commit=False)
    t.equal((Post.objects.count(), PostComment.objects.count(), TaggedPost.objects.count(), authors_through.objects.count()),
            (0, 0, 0, 0), "save(commit=False) writes nothing")
    t.equal([c.text for c in obj.comments.all()], ["c1"], "children applied in memory")
    t.equal(sorted(a.pk for a in obj.authors.all()), sorted([a1.pk, a2.pk]), "parental m2m applied in memory")
    t.equal(sorted(tag.name for tag in obj.tags.all()), ["blue", "red"], "cluster tags applied in memory")
    obj.save()
    t.equal(list(_rows(PostComment, post=obj).values_list("text", flat=True)), ["c1"], "obj.save() writes children")
    t.equal(authors_through.objects.filter(post=obj).count(), 2, "obj.save() writes parental m2m")
    t.equal(sorted(_rows(TaggedPost, content_object=obj).values_list("tag__name", flat=True)), ["blue", "red"], "obj.save() writes tags")
    t.equal(links_through.objects.filter(post=obj).count(), 0, "plain m2m waits for save_m2m()")
    form.save_m2m()
    t.equal(list(links_through.objects.filter(post=obj).values_list("link_id", flat=True)), [link.pk], "save_m2m() writes plain m2m")
    form = PostForm(data, instance=Post())
    t.require(form.is_valid(), "second form valid")
    saved = form.save()
    t.require(saved.pk is not None, "save() writes the instance")
    t.equal(_rows(PostComment, post=saved).count(), 1, "save() writes children")
    t.equal(authors_through.objects.filter(post=saved).count(), 2, "save() writes parental m2m")
    t.equal(_rows(TaggedPost, content_object=saved).count(), 2, "save() writes tags")
    t.equal(links_through.objects.filter(post=saved).count(), 1, "save() writes plain m2m")


@case("T.R08.17")
def _clusterform_factory(t):
    from heldout_checker_app.models import Band

    from modelcluster.forms import ClusterForm, clusterform_factory

    band = Band(name="b")
    band.save()
    FormClass = clusterform_factory(Band, fields=["name"])
    t.require(isinstance(FormClass, type) and issubclass(FormClass, ClusterForm), "returns a ClusterForm subclass")
    form = FormClass(instance=band)
    t.require(form.instance is band, "bound to the given instance")
    t.equal(set(form.fields), {"name"}, "exposes the requested fields")
    t.equal(form["name"].value(), "b", "initial value from the instance")


@case("T.integration.clusterform-nested-save")
def _clusterform_nested_save(t):
    from heldout_checker_app.models import Album, Band, BandMember, Song

    from modelcluster.forms import ClusterForm

    class AlbumClusterForm(ClusterForm):
        class Meta:
            model = Album
            fields = ["title"]

    class BandForm(ClusterForm):
        class Meta:
            model = Band
            fields = ["name"]
            formsets = {"albums": {"form": AlbumClusterForm, "formsets": ["songs"]}, "members": {"fields": ["name"]}}

    band = Band(name="b")
    band.members = [BandMember(name="m1"), BandMember(name="m2")]
    band.save()
    unbound = BandForm(instance=band)
    members, albums = unbound.formsets["members"], unbound.formsets["albums"]
    kept, dropped = members.forms[0], members.forms[1]
    songs_prefix = albums.forms[0].formsets["songs"].prefix
    data = {"name": "b", **_management(members.prefix, 2, 2),
            kept.add_prefix("id"): str(kept.instance.pk), kept.add_prefix("name"): "edited",
            dropped.add_prefix("id"): str(dropped.instance.pk), dropped.add_prefix("name"): dropped.instance.name,
            dropped.add_prefix("DELETE"): "on",
            **_management(albums.prefix, 1), albums.forms[0].add_prefix("title"): "LP",
            **_management(songs_prefix, 2), f"{songs_prefix}-0-title": "s1", f"{songs_prefix}-1-title": "s2"}
    form = BandForm(data, instance=band)
    t.require(form.is_valid(), f"nested ClusterForm valid: {form.errors}")
    obj = form.save(commit=False)
    t.equal(sorted(_rows(BandMember, band=band).values_list("name", flat=True)), ["m1", "m2"], "commit=False: members unchanged in DB")
    t.equal((Album.objects.count(), Song.objects.count()), (0, 0), "commit=False: no album/song rows")
    t.equal(_names(obj.members.all()), ["edited"], "in-memory members")
    albums_in_memory = list(obj.albums.all())
    t.equal([a.title for a in albums_in_memory], ["LP"], "in-memory album")
    t.equal(sorted(s.title for s in albums_in_memory[0].songs.all()), ["s1", "s2"], "in-memory songs")
    obj.save()
    t.equal(list(_rows(BandMember, band=band).values_list("name", flat=True)), ["edited"], "member rows after save")
    t.require(not BandMember.objects.filter(pk=dropped.instance.pk).exists(), "deleted member row removed")
    t.equal(list(_rows(Album, band=band).values_list("title", flat=True)), ["LP"], "album row after save")
    t.equal(sorted(_rows(Song, album__band=band).values_list("title", flat=True)), ["s1", "s2"], "song rows after save")


# ============================================================================ taggit-cluster

@case("T.R09.01", apps=("tags",))
def _cluster_taggable_manager(t):
    from django.core import checks
    from heldout_checker_tags.models import Shop, TaggedShop
    from taggit.managers import TaggableManager

    from modelcluster.contrib.taggit import ClusterTaggableManager

    t.require(issubclass(ClusterTaggableManager, TaggableManager), "ClusterTaggableManager subclasses TaggableManager")
    errors = [e for e in Shop.check() + TaggedShop.check() if e.level >= checks.ERROR]
    t.equal(errors, [], "model checks pass")
    shop = Shop(name="p")
    shop.tags.add("a")
    t.equal([tag.name for tag in shop.tags.all()], ["a"], "tag held in memory on an unsaved instance")
    t.equal(TaggedShop.objects.count(), 0, "no tagged-item row before save")
    shop.save()
    t.equal(list(_rows(TaggedShop, content_object=shop).values_list("tag__name", flat=True)), ["a"], "tagged-item row after save")


@case("T.R09.02", apps=("tags",))
def _tags_in_memory(t):
    from heldout_checker_tags.models import Shop, TaggedShop
    from taggit.models import Tag

    shop = Shop(name="p")

    def tag_names():
        return sorted(tag.name for tag in shop.tags.all())

    def stored():
        return sorted(TaggedShop.objects.values_list("tag__name", flat=True))

    shop.tags.add("a", "b")
    shop.tags.remove("a")
    t.equal(tag_names(), ["b"], "add() then remove()")
    shop.tags.set(["b", "c"])
    t.equal(tag_names(), ["b", "c"], "set()")
    t.equal(shop.tags.count(), 2, "count()")
    t.require(all(isinstance(tag, Tag) for tag in shop.tags.all()), "all() yields taggit Tag instances")
    shop.tags.clear()
    t.equal(tag_names(), [], "clear()")
    shop.tags.set(["x"])
    t.equal(tag_names(), ["x"], "set() after clear()")
    t.equal(stored(), [], "no tagged-item rows before save")
    shop.save()
    t.equal(stored(), ["x"], "rows match the final tag set after save")
    shop.tags.add("y")
    shop.tags.remove("x")
    t.equal(tag_names(), ["y"], "changes on the saved instance are in memory")
    t.equal(stored(), ["x"], "rows unchanged before the second save")
    shop.save()
    t.equal(stored(), ["y"], "rows updated by the second save")


@case("T.R09.03", apps=("tags",))
def _tags_value_error(t):
    from heldout_checker_tags.models import Shop
    from taggit.models import Tag

    shop = Shop(name="p")
    t.raises(ValueError, lambda: shop.tags.add(1), "add(1) raises ValueError")
    shop.tags.add(Tag.objects.create(name="t"))
    t.equal([tag.name for tag in shop.tags.all()], ["t"], "adding a Tag instance is accepted")


def _make_tagged_shops(start, stop):
    from heldout_checker_tags.models import Shop, TaggedShop
    from taggit.models import Tag

    for i in range(start, stop):
        shop = Shop(name=f"s{i}")
        shop.save()
        for suffix in ("a", "b"):
            TaggedShop.objects.create(content_object=shop, tag=Tag.objects.create(name=f"t{i}{suffix}"))


@case("T.R09.04", apps=("tags",))
def _tags_prefetch(t):
    from heldout_checker_tags.models import Shop

    def loop():
        return {shop.name: sorted(tag.name for tag in shop.tags.all()) for shop in Shop.objects.prefetch_related("tags")}

    _make_tagged_shops(0, 3)
    got3, queries3 = _query_count(loop)
    t.equal(got3, {f"s{i}": [f"t{i}a", f"t{i}b"] for i in range(3)}, "each shop yields its own tags (3 shops)")
    _make_tagged_shops(3, 5)
    got5, queries5 = _query_count(loop)
    t.equal(got5, {f"s{i}": [f"t{i}a", f"t{i}b"] for i in range(5)}, "each shop yields its own tags (5 shops)")
    t.equal(queries3, queries5, "prefetch_related('tags') query count independent of the number of shops")


@case("T.R09.05", apps=("tags",))
def _tags_in_clusterform(t):
    from heldout_checker_tags.models import PlainTagged, Shop, TaggedShop

    from modelcluster.forms import ClusterForm

    class ShopForm(ClusterForm):
        class Meta:
            model = Shop
            fields = ["name", "tags"]

    form = ShopForm({"name": "p", "tags": "a, b"}, instance=Shop())
    t.require(form.is_valid(), f"ShopForm valid: {form.errors}")
    obj = form.save(commit=False)
    t.equal(sorted(tag.name for tag in obj.tags.all()), ["a", "b"], "tags applied in memory by save(commit=False)")
    t.equal(TaggedShop.objects.count(), 0, "no tagged-item rows before obj.save()")
    obj.save()
    t.equal(sorted(_rows(TaggedShop, content_object=obj).values_list("tag__name", flat=True)), ["a", "b"], "rows after obj.save()")

    class PlainForm(ClusterForm):
        class Meta:
            model = PlainTagged
            fields = ["name", "tags"]

    form = PlainForm({"name": "q", "tags": "x, y"}, instance=PlainTagged())
    t.require(form.is_valid(), f"PlainForm valid: {form.errors}")
    saved = form.save()
    t.equal(sorted(PlainTagged.objects.get(pk=saved.pk).tags.names()), ["x", "y"], "plain TaggableManager works through ClusterForm")


@case("T.integration.tags-and-prefetch", apps=("tags",))
def _tags_and_prefetch(t):
    from heldout_checker_tags.models import Shop, ShopReview, TaggedShop

    def make(i):
        shop = Shop(name=f"s{i}")
        shop.tags.set([f"a{i}", f"b{i}"])
        shop.reviews = [ShopReview(text=f"r{i}")]
        shop.save()
        return shop

    first = make(0)
    t.equal(sorted(_rows(TaggedShop, content_object=first).values_list("tag__name", flat=True)), ["a0", "b0"], "tag rows after save")
    t.equal(list(_rows(ShopReview, shop=first).values_list("text", flat=True)), ["r0"], "review rows after save")

    def loop():
        return {shop.name: (sorted(tag.name for tag in shop.tags.all()), [r.text for r in shop.reviews.all()])
                for shop in Shop.objects.prefetch_related("tags", "reviews")}

    def expected(n):
        return {f"s{i}": ([f"a{i}", f"b{i}"], [f"r{i}"]) for i in range(n)}

    for i in (1, 2):
        make(i)
    got3, queries3 = _query_count(loop)
    t.equal(got3, expected(3), "prefetched tags and reviews (3 shops)")
    for i in (3, 4):
        make(i)
    got5, queries5 = _query_count(loop)
    t.equal(got5, expected(5), "prefetched tags and reviews (5 shops)")
    t.equal(queries3, queries5, "query count independent of the number of shops")
