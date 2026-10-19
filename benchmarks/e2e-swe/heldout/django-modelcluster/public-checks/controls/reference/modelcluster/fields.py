"""ParentalKey and ParentalManyToManyField: relations whose related sets live in memory until commit."""
from django.core import checks
from django.db import IntegrityError, models
from django.db.models.fields.related_descriptors import (
    create_forward_many_to_many_manager,
    create_reverse_many_to_one_manager,
)
from django.utils.functional import cached_property

from .queryset import FakeQuerySet, sort_by_ordering

STATE_ATTR = "_cluster_related_objects"
READ_METHODS = {
    "filter", "exclude", "get", "order_by", "first", "last", "exists", "count", "values",
    "values_list", "distinct", "none", "select_related", "prefetch_related", "only", "defer",
}


def in_memory_objects(instance, name):
    """The in-memory list held for relation `name` on `instance`, or None when untouched."""
    return instance.__dict__.get(STATE_ATTR, {}).get(name)


def store_in_memory_objects(instance, name, objects):
    instance.__dict__.setdefault(STATE_ATTR, {})[name] = objects


def drop_prefetched(instance, name):
    getattr(instance, "_prefetched_objects_cache", {}).pop(name, None)


class DeferringManagerBase:
    """Shared read API: in-memory FakeQuerySet when touched, live queryset when saved and untouched."""

    def __init__(self, instance, model, relation_name, live_manager_class):
        self.instance = instance
        self.model = model
        self.relation_name = relation_name
        self.live_manager_class = live_manager_class

    def get_live_queryset(self):
        return self.live_manager_class(self.instance).get_queryset()

    def get_object_list(self):
        objects = in_memory_objects(self.instance, self.relation_name)
        if objects is not None:
            return list(objects)
        if self.instance.pk is None:
            return []
        return list(self.get_live_queryset())

    def get_queryset(self):
        objects = in_memory_objects(self.instance, self.relation_name)
        if objects is not None:
            return FakeQuerySet(self.model, objects)
        if self.instance.pk is None:
            return FakeQuerySet(self.model, [])
        return self.get_live_queryset()

    def all(self):
        return self.get_queryset()

    def get_prefetch_querysets(self, instances, querysets=None):
        return self.live_manager_class(self.instance).get_prefetch_querysets(instances, querysets)

    def __getattr__(self, name):
        if name in READ_METHODS:
            return getattr(self.get_queryset(), name)
        raise AttributeError(name)

    def __iter__(self):
        return iter(self.get_queryset())

    def clear(self):
        self.set([])

    def remove(self, *objs):
        self.set([obj for obj in self.get_object_list() if obj not in objs])


class DeferringChildManager(DeferringManagerBase):
    """Manager for the reverse side of a ParentalKey."""

    def __init__(self, instance, rel, live_manager_class):
        super().__init__(instance, rel.related_model, rel.get_accessor_name(), live_manager_class)
        self.parental_key = rel.field

    def __store(self, objects):
        for obj in objects:
            setattr(obj, self.parental_key.name, self.instance)
        drop_prefetched(self.instance, self.relation_name)
        store_in_memory_objects(self.instance, self.relation_name, sort_by_ordering(self.model, objects))

    @staticmethod
    def __merge(current, objs):
        result = list(current)
        for obj in objs:
            for index, existing in enumerate(result):
                if existing == obj:
                    result[index] = obj
                    break
            else:
                result.append(obj)
        return result

    def add(self, *objs):
        self.__store(self.__merge(self.get_object_list(), objs))

    def set(self, objs):
        self.__store(self.__merge([], list(objs)))

    def create(self, **kwargs):
        obj = self.model(**kwargs)
        self.add(obj)
        return obj

    def commit(self):
        if self.instance.pk is None:
            raise IntegrityError(f"Cannot commit child relation {self.relation_name!r} on an unsaved model")
        objects = in_memory_objects(self.instance, self.relation_name)
        if objects is None:
            return
        kept = [obj.pk for obj in objects if obj.pk is not None]
        stored = self.model._default_manager.filter(**{self.parental_key.name: self.instance})
        stored.exclude(pk__in=kept).delete()
        for obj in objects:
            setattr(obj, self.parental_key.name, self.instance)
            obj.save()
        drop_prefetched(self.instance, self.relation_name)


class ChildObjectsDescriptor:
    def __init__(self, rel):
        self.rel = rel

    @cached_property
    def live_manager_class(self):
        return create_reverse_many_to_one_manager(self.rel.related_model._default_manager.__class__, self.rel)

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        return DeferringChildManager(instance, self.rel, self.live_manager_class)

    def __set__(self, instance, value):
        self.__get__(instance).set(value)


class ParentalKey(models.ForeignKey):
    related_accessor_class = ChildObjectsDescriptor

    def __init__(self, to, on_delete=models.CASCADE, **kwargs):
        super().__init__(to, on_delete, **kwargs)

    def check(self, **kwargs):
        from .models import ClusterableModel

        errors = super().check(**kwargs)
        target = self.remote_field.model
        if isinstance(target, type) and issubclass(target, models.Model) and not issubclass(target, ClusterableModel):
            errors.append(checks.Error(
                "ParentalKey must point to a subclass of ClusterableModel.",
                hint="Change the target into a ClusterableModel or use a ForeignKey instead.",
                obj=self,
                id="modelcluster.E001",
            ))
        if (self.remote_field.related_name or "").endswith("+"):
            errors.append(checks.Error(
                "related_name='+' is not allowed on ParentalKey fields",
                hint="Either change it to a valid name or remove it",
                obj=self,
                id="modelcluster.E002",
            ))
        return errors


class ParentalManyToManyManager(DeferringManagerBase):
    def __init__(self, instance, field, live_manager_class):
        super().__init__(instance, field.related_model, field.name, live_manager_class)

    def set(self, objs):
        objects = []
        for obj in objs:
            if obj.pk is None:
                raise ValueError(f"{obj!r} must be saved before it can be added to {self.relation_name!r}")
            if obj not in objects:
                objects.append(obj)
        drop_prefetched(self.instance, self.relation_name)
        store_in_memory_objects(self.instance, self.relation_name, sort_by_ordering(self.model, objects))

    def add(self, *objs):
        self.set(self.get_object_list() + list(objs))

    def commit(self):
        if self.instance.pk is None:
            raise IntegrityError(f"Cannot commit m2m relation {self.relation_name!r} on an unsaved model")
        objects = in_memory_objects(self.instance, self.relation_name)
        if objects is None:
            return
        self.live_manager_class(self.instance).set(objects)
        drop_prefetched(self.instance, self.relation_name)


class ParentalManyToManyDescriptor:
    def __init__(self, field):
        self.field = field

    @cached_property
    def live_manager_class(self):
        rel = self.field.remote_field
        return create_forward_many_to_many_manager(rel.model._default_manager.__class__, rel, reverse=False)

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        return ParentalManyToManyManager(instance, self.field, self.live_manager_class)

    def __set__(self, instance, value):
        self.__get__(instance).set(value)


class ParentalManyToManyField(models.ManyToManyField):
    def contribute_to_class(self, cls, name, **kwargs):
        super().contribute_to_class(cls, name, **kwargs)
        setattr(cls, self.name, ParentalManyToManyDescriptor(self))

    def value_from_object(self, obj):
        return list(getattr(obj, self.attname).all())
