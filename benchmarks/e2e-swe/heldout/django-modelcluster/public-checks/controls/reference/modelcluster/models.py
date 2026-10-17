"""ClusterableModel: a model whose child relations and parental m2m sets are saved as one cluster."""
import datetime
import json

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, models
from django.db.models.fields.reverse_related import ManyToOneRel
from django.utils import timezone

from .fields import ParentalKey, ParentalManyToManyField


def get_all_child_relations(model):
    return [
        rel for rel in model._meta.get_fields()
        if isinstance(rel, ManyToOneRel) and isinstance(rel.field, ParentalKey)
    ]


def get_all_child_m2m_relations(model):
    return [field for field in model._meta.get_fields() if isinstance(field, ParentalManyToManyField)]


def serialize_field_value(field, obj):
    value = field.value_from_object(obj)
    if isinstance(field, models.DateTimeField) and value is not None and settings.USE_TZ:
        if timezone.is_naive(value):
            value = timezone.make_aware(value, timezone.get_current_timezone())
        return value.astimezone(datetime.timezone.utc)
    if isinstance(field, models.FileField):
        return value.name or None
    return value


def get_serializable_data_for_fields(obj):
    data = {"pk": obj.pk}
    for field in obj._meta.concrete_fields:
        if field.serialize:
            data[field.name] = serialize_field_value(field, obj)
    return data


def model_from_serializable_data(model, data, check_fks=True, strict_fks=False, exclude_fields=()):
    kwargs = {}
    for field in model._meta.concrete_fields:
        if not field.serialize or field.name in exclude_fields or field.name not in data:
            continue
        value = data[field.name]
        if field.is_relation:
            if value is not None and check_fks:
                target = field.related_model._default_manager.filter(**{field.target_field.attname: value})
                if not target.exists():
                    if field.remote_field.on_delete == models.CASCADE and strict_fks:
                        return None
                    value = None
            kwargs[field.attname] = value
        else:
            value = field.to_python(value)
            if isinstance(value, datetime.datetime) and settings.USE_TZ and timezone.is_aware(value):
                value = timezone.localtime(value)
            kwargs[field.name] = value
    obj = model(**kwargs)
    pk = data.get("pk")
    if pk is not None:
        obj.pk = pk
        for parent in model._meta.get_parent_list():
            setattr(obj, parent._meta.pk.attname, pk)
    return obj


def copy_field_values(source, exclude_fields=()):
    copy = source.__class__()
    for field in source._meta.concrete_fields:
        if field.primary_key or field.name in exclude_fields:
            continue
        setattr(copy, field.attname, getattr(source, field.attname))
        if field.is_relation and field.is_cached(source):
            setattr(copy, field.name, getattr(source, field.name))
    return copy


class ClusterableModel(models.Model):
    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        relation_names = [rel.get_accessor_name() for rel in get_all_child_relations(self)]
        relation_names += [field.name for field in get_all_child_m2m_relations(self)]
        relations = {name: kwargs.pop(name) for name in relation_names if name in kwargs}
        super().__init__(*args, **kwargs)
        for name, value in relations.items():
            setattr(self, name, value)

    def save(self, *args, **kwargs):
        child_names = [rel.get_accessor_name() for rel in get_all_child_relations(self)]
        m2m_names = [field.name for field in get_all_child_m2m_relations(self)]
        relation_names = child_names + m2m_names
        update_fields = kwargs.pop("update_fields", None)
        if update_fields is None:
            committed = relation_names
            real_fields = None
        else:
            committed = [name for name in update_fields if name in relation_names]
            real_fields = [name for name in update_fields if name not in relation_names]
        if real_fields is None or real_fields:
            super().save(*args, update_fields=real_fields, **kwargs)
        for name in committed:
            getattr(self, name).commit()

    # serialization
    def serializable_data(self):
        data = get_serializable_data_for_fields(self)
        for rel in get_all_child_relations(self):
            if not rel.field.serialize:
                continue
            children = getattr(self, rel.get_accessor_name()).all()
            data[rel.get_accessor_name()] = [
                child.serializable_data() if isinstance(child, ClusterableModel) else get_serializable_data_for_fields(child)
                for child in children
            ]
        for field in get_all_child_m2m_relations(self):
            if field.serialize:
                data[field.name] = [obj.pk for obj in getattr(self, field.name).all()]
        return data

    def to_json(self):
        return json.dumps(self.serializable_data(), cls=DjangoJSONEncoder)

    @classmethod
    def from_serializable_data(cls, data, check_fks=True, strict_fks=False):
        obj = model_from_serializable_data(cls, data, check_fks=check_fks, strict_fks=strict_fks)
        if obj is None:
            return None
        for rel in get_all_child_relations(cls):
            name = rel.get_accessor_name()
            if name not in data:
                continue
            child_model = rel.related_model
            children = []
            for child_data in data[name]:
                if issubclass(child_model, ClusterableModel):
                    child = child_model.from_serializable_data(child_data, check_fks=check_fks, strict_fks=True)
                else:
                    child = model_from_serializable_data(
                        child_model, child_data, check_fks=check_fks, strict_fks=True, exclude_fields=[rel.field.name])
                if child is not None:
                    children.append(child)
            setattr(obj, name, children)
        for field in get_all_child_m2m_relations(cls):
            if field.name in data:
                setattr(obj, field.name, field.related_model._default_manager.filter(pk__in=data[field.name]))
        return obj

    @classmethod
    def from_json(cls, json_data, check_fks=True, strict_fks=False):
        return cls.from_serializable_data(json.loads(json_data), check_fks=check_fks, strict_fks=strict_fks)

    # copying
    def copy_child_relation(self, child_relation, target, commit=False, append=False):
        if isinstance(child_relation, str):
            matches = [rel for rel in get_all_child_relations(self) if rel.get_accessor_name() == child_relation]
            if not matches:
                raise LookupError(f"{child_relation!r} is not a child relation of {self._meta.label}")
            rel = matches[0]
        else:
            rel = child_relation
        if not isinstance(getattr(rel, "field", None), ParentalKey):
            raise LookupError(f"{child_relation!r} is not a ParentalKey relation")
        if commit and target.pk is None:
            raise IntegrityError("Cannot commit copied children to an unsaved target")
        name = rel.get_accessor_name()
        child_object_map = {}
        copies = []
        for child in getattr(self, name).all():
            if isinstance(child, ClusterableModel):
                copy, _ = child.copy_cluster(exclude_fields=[rel.field.name])
            else:
                copy = copy_field_values(child, exclude_fields=[rel.field.name])
            if child.pk is None:
                child_object_map.setdefault((child_relation, None), []).append(copy)
            else:
                child_object_map[(child_relation, child.pk)] = copy
            copies.append(copy)
        manager = getattr(target, name)
        if append:
            manager.add(*copies)
        else:
            manager.set(copies)
        if commit:
            manager.commit()
        return child_object_map

    def copy_all_child_relations(self, target, exclude=None, commit=False, append=False):
        exclude = exclude or []
        child_object_map = {}
        for rel in get_all_child_relations(self):
            if rel.get_accessor_name() in exclude:
                continue
            child_object_map.update(
                self.copy_child_relation(rel.get_accessor_name(), target, commit=commit, append=append))
        return child_object_map

    def copy_cluster(self, exclude_fields=None):
        exclude_fields = list(exclude_fields or [])
        copy = copy_field_values(self, exclude_fields=exclude_fields)
        for field in get_all_child_m2m_relations(self):
            if field.name not in exclude_fields:
                setattr(copy, field.name, list(getattr(self, field.name).all()))
        child_object_map = self.copy_all_child_relations(copy, exclude=exclude_fields)
        return copy, child_object_map
