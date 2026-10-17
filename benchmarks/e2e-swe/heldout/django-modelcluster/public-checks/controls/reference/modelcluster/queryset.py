"""FakeQuerySet: the read side of Django's QuerySet API over an in-memory list."""
import datetime
import random
import re

from django.conf import settings
from django.core.exceptions import FieldDoesNotExist, FieldError, ObjectDoesNotExist
from django.db import models
from django.db.models import Model, Q, prefetch_related_objects
from django.db.models.fields.reverse_related import ForeignObjectRel
from django.utils import timezone

from .utils import ManyToManyTraversalError

LOOKUPS = {
    "exact", "iexact", "contains", "icontains", "startswith", "istartswith", "endswith",
    "iendswith", "in", "lt", "lte", "gt", "gte", "range", "isnull", "regex", "iregex",
}
TEXT_LOOKUPS = {"iexact", "contains", "icontains", "startswith", "istartswith", "endswith", "iendswith", "regex", "iregex"}
TRANSFORMS = {
    "year", "iso_year", "month", "day", "week", "week_day", "iso_week_day", "quarter",
    "date", "time", "hour", "minute", "second",
}
MISSING = object()


def apply_transform(name, value):
    if value is None:
        return None
    if isinstance(value, datetime.datetime) and settings.USE_TZ and timezone.is_aware(value):
        value = timezone.localtime(value)
    if name == "iso_year":
        return value.isocalendar()[0]
    if name == "week":
        return value.isocalendar()[1]
    if name == "week_day":
        return value.isoweekday() % 7 + 1
    if name == "iso_week_day":
        return value.isoweekday()
    if name == "quarter":
        return (value.month - 1) // 3 + 1
    if name == "date":
        return value.date()
    if name == "time":
        return value.time()
    return getattr(value, name)


def related_object(obj, field):
    name = field.get_accessor_name() if isinstance(field, ForeignObjectRel) else field.name
    try:
        return getattr(obj, name)
    except ObjectDoesNotExist:
        return None


def plain(value):
    return value.pk if isinstance(value, Model) else value


def instances_match(a, b):
    if a is b:
        return True
    if a.pk is None or b.pk is None or a.pk != b.pk:
        return False
    return isinstance(a, type(b)) or isinstance(b, type(a))


class LookupPath:
    """A parsed `field__field__transform__lookup` key."""

    def __init__(self, model, key, allow_lookup=True):
        parts = key.split("__")
        self.key = key
        self.fields = []
        current = model
        index = 0
        while index < len(parts) and current is not None:
            name = parts[index]
            try:
                field = current._meta.pk if name == "pk" else current._meta.get_field(name)
            except FieldDoesNotExist:
                break
            if field.many_to_many or field.one_to_many:
                raise ManyToManyTraversalError(f"Cannot traverse the multi-valued relation {name!r} in {key!r}")
            self.fields.append(field)
            index += 1
            current = field.related_model if field.is_relation else None
        if not self.fields:
            raise FieldError(f"Cannot resolve keyword {parts[0]!r} on {model.__name__}")
        rest = parts[index:]
        self.transforms = []
        while rest and rest[0] in TRANSFORMS:
            self.transforms.append(rest.pop(0))
        self.lookup = "exact"
        if allow_lookup and len(rest) == 1 and rest[0] in LOOKUPS:
            self.lookup = rest.pop()
        if rest:
            raise FieldError(f"Unsupported lookup {key!r}")
        self.last = self.fields[-1]
        self.is_relation = self.last.is_relation and not self.transforms

    def value(self, obj):
        for field in self.fields[:-1]:
            obj = related_object(obj, field)
            if obj is None:
                return MISSING
        value = related_object(obj, self.last) if self.last.is_relation else getattr(obj, self.last.attname)
        for name in self.transforms:
            value = apply_transform(name, value)
        return value

    def plain_value(self, obj):
        value = self.value(obj)
        return None if value is MISSING else plain(value)

    def coerce_one(self, raw):
        if raw is None or isinstance(raw, Model):
            return raw
        if self.transforms:
            name = self.transforms[-1]
            if name == "date":
                return models.DateField().to_python(raw)
            if name == "time":
                return models.TimeField().to_python(raw)
            return int(raw)
        if self.is_relation:
            target = self.last.related_model._meta.pk
            return target.to_python(raw)
        return self.last.to_python(raw)

    def coerce(self, raw):
        if raw is None or self.lookup == "isnull" or self.lookup in TEXT_LOOKUPS:
            return raw
        if self.lookup in ("in", "range"):
            return [self.coerce_one(item) for item in raw]
        return self.coerce_one(raw)

    def matches(self, obj, wanted):
        value = self.value(obj)
        if value is MISSING:
            return False
        if self.is_relation:
            return relation_matches(self.lookup, value, wanted)
        return compare(self.lookup, value, wanted)


def same_related(rel, wanted):
    if rel is None or wanted is None:
        return rel is None and wanted is None
    if isinstance(wanted, Model):
        return instances_match(rel, wanted)
    return rel.pk is not None and rel.pk == wanted


def relation_matches(lookup, rel, wanted):
    if lookup == "isnull":
        return (rel is None) == bool(wanted)
    if lookup == "in":
        return any(same_related(rel, item) for item in wanted)
    if lookup == "exact":
        return same_related(rel, wanted)
    return compare(lookup, None if rel is None else rel.pk, plain(wanted))


def compare(lookup, value, wanted):
    if lookup == "isnull":
        return (value is None) == bool(wanted)
    if lookup == "in":
        return value in wanted
    if wanted is None and lookup in ("exact", "iexact"):
        return value is None
    if lookup == "exact":
        return value == wanted
    if value is None or wanted is None:
        return False
    if lookup in TEXT_LOOKUPS:
        text, needle = str(value), str(wanted)
        if lookup == "regex":
            return re.search(needle, text) is not None
        if lookup == "iregex":
            return re.search(needle, text, re.IGNORECASE) is not None
        if lookup.startswith("i"):
            text, needle, lookup = text.lower(), needle.lower(), lookup[1:]
        if lookup == "exact":
            return text == needle
        if lookup == "contains":
            return needle in text
        if lookup == "startswith":
            return text.startswith(needle)
        return text.endswith(needle)
    if lookup == "lt":
        return value < wanted
    if lookup == "lte":
        return value <= wanted
    if lookup == "gt":
        return value > wanted
    if lookup == "gte":
        return value >= wanted
    if lookup == "range":
        return wanted[0] <= value <= wanted[1]
    raise FieldError(f"Unsupported lookup {lookup!r}")


def compile_q(model, q):
    children = []
    for child in q.children:
        if isinstance(child, Q):
            children.append(("q", compile_q(model, child)))
        else:
            key, raw = child
            path = LookupPath(model, key)
            children.append(("leaf", (path, path.coerce(raw))))
    return q.connector, q.negated, children


def evaluate(compiled, obj):
    connector, negated, children = compiled
    results = [
        evaluate(payload, obj) if kind == "q" else payload[0].matches(obj, payload[1])
        for kind, payload in children
    ]
    if connector == Q.OR:
        result = any(results)
    elif connector == getattr(Q, "XOR", "XOR"):
        result = sum(results) % 2 == 1
    else:
        result = all(results)
    return not result if negated else result


def sort_key(value):
    value = plain(value)
    return (value is not None, value)


def sort_by_ordering(model, items):
    ordering = [item for item in model._meta.ordering if isinstance(item, str)]
    if not ordering:
        return list(items)
    return FakeQuerySet(model, items).order_by(*ordering).results


class FakeQuerySet:
    ordered = True

    def __init__(self, model, results):
        self.model = model
        self.results = list(results)
        self.shape = None

    def _clone(self, results=None):
        clone = self.__class__(self.model, self.results if results is None else results)
        clone.shape = self.shape
        return clone

    # filtering
    def filter(self, *args, **kwargs):
        compiled = compile_q(self.model, Q(*args, **kwargs))
        return self._clone([obj for obj in self.results if evaluate(compiled, obj)])

    def exclude(self, *args, **kwargs):
        compiled = compile_q(self.model, Q(*args, **kwargs))
        return self._clone([obj for obj in self.results if not evaluate(compiled, obj)])

    def all(self):
        return self

    def none(self):
        return self._clone([])

    def select_related(self, *fields):
        return self

    def only(self, *fields):
        return self

    def defer(self, *fields):
        return self

    def prefetch_related(self, *lookups):
        prefetch_related_objects(self.results, *lookups)
        return self

    def order_by(self, *fields):
        results = list(self.results)
        for name in reversed(fields):
            if name == "?":
                random.shuffle(results)
                continue
            descending = name.startswith("-")
            path = LookupPath(self.model, name.lstrip("-"), allow_lookup=False)
            results.sort(key=lambda obj: sort_key(path.plain_value(obj)), reverse=descending)
        return self._clone(results)

    def distinct(self, *fields):
        if fields:
            paths = [LookupPath(self.model, name, allow_lookup=False) for name in fields]
        else:
            paths = [LookupPath(self.model, f.name, allow_lookup=False)
                     for f in self.model._meta.concrete_fields if not f.primary_key]
        seen, kept = [], []
        for obj in self.results:  # ponytail: O(n^2) list scan; fine for in-memory clusters
            key = tuple(path.plain_value(obj) for path in paths)
            if key not in seen:
                seen.append(key)
                kept.append(obj)
        return self._clone(kept)

    # shaping
    def values(self, *fields):
        clone = self._clone()
        clone.shape = ("values", fields, False)
        return clone

    def values_list(self, *fields, flat=False):
        if flat and len(fields) > 1:
            raise TypeError("'flat' is not valid when values_list is called with more than one field.")
        clone = self._clone()
        clone.shape = ("values_list", fields, flat)
        return clone

    def _rows(self, objects):
        if self.shape is None:
            return list(objects)
        kind, fields, flat = self.shape
        if fields:
            names = list(fields)
            paths = [LookupPath(self.model, name, allow_lookup=False) for name in names]
        else:
            concrete = self.model._meta.concrete_fields
            names = [f.attname for f in concrete]
            paths = [LookupPath(self.model, f.name, allow_lookup=False) for f in concrete]
        rows = []
        for obj in objects:
            values = [path.plain_value(obj) for path in paths]
            if kind == "values":
                rows.append(dict(zip(names, values)))
            elif flat:
                rows.append(values[0])
            else:
                rows.append(tuple(values))
        return rows

    # retrieval
    def get(self, *args, **kwargs):
        matches = self.filter(*args, **kwargs) if (args or kwargs) else self
        if not matches.results:
            raise self.model.DoesNotExist(f"{self.model._meta.object_name} matching query does not exist.")
        if len(matches.results) > 1:
            raise self.model.MultipleObjectsReturned(
                f"get() returned more than one {self.model._meta.object_name} -- it returned {len(matches.results)}!")
        return matches._rows(matches.results)[0]

    def count(self):
        return len(self.results)

    def exists(self):
        return bool(self.results)

    def first(self):
        rows = self._rows(self.results[:1])
        return rows[0] if rows else None

    def last(self):
        rows = self._rows(self.results[-1:])
        return rows[0] if rows else None

    def __iter__(self):
        return iter(self._rows(self.results))

    def __len__(self):
        return len(self.results)

    def __bool__(self):
        return bool(self.results)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return self._clone(self.results[index])
        return self._rows([self.results[index]])[0]

    def __repr__(self):
        return f"<FakeQuerySet {self._rows(self.results)!r}>"
