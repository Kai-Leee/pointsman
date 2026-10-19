"""Cluster-aware forms: transient/child formsets and ClusterForm."""
from itertools import chain

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.forms.formsets import BaseFormSet
from django.forms.models import (
    BaseModelFormSet,
    ModelForm,
    ModelFormMetaclass,
    _get_foreign_key,
    modelformset_factory,
)
from django.utils.safestring import mark_safe

from .fields import ParentalManyToManyField
from .models import get_all_child_relations


def is_parental_field(field):
    if isinstance(field, ParentalManyToManyField):
        return True
    try:
        from .contrib.taggit import ClusterTaggableManager
    except ImportError:
        return False
    return isinstance(field, ClusterTaggableManager)


class BaseTransientModelFormSet(BaseModelFormSet):
    """A model formset whose initial instances need not exist in the database."""

    def _construct_form(self, i, **kwargs):
        pk_name = self.model._meta.pk.name
        pk_key = f"{self.add_prefix(i)}-{pk_name}"
        if self.is_bound and i < self.initial_form_count() and not self.data.get(pk_key):
            objects = list(self.get_queryset())
            if i < len(objects):
                kwargs["instance"] = objects[i]
            form = BaseFormSet._construct_form(self, i, **kwargs)
        else:
            form = super()._construct_form(i, **kwargs)
        if pk_name in form.fields:
            form.fields[pk_name].required = False
        return form


def transientmodelformset_factory(model, formset=BaseTransientModelFormSet, **kwargs):
    return modelformset_factory(model, formset=formset, **kwargs)


class BaseChildFormSet(BaseTransientModelFormSet):
    fk = None
    inherit_kwargs = None

    def __init__(self, data=None, files=None, instance=None, queryset=None, **kwargs):
        self.instance = self.fk.remote_field.model() if instance is None else instance
        self.rel_name = self.fk.remote_field.get_accessor_name()
        if queryset is None:
            queryset = getattr(self.instance, self.rel_name).all()
        super().__init__(data, files, queryset=queryset, **kwargs)

    def _construct_form(self, i, **kwargs):
        form = super()._construct_form(i, **kwargs)
        setattr(form.instance, self.fk.name, self.instance)
        return form

    def clean(self):
        super().clean()
        fk_name = self.fk.name
        meta = self.model._meta
        groups = [tuple(group) for group in meta.unique_together]
        groups += [tuple(constraint.fields) for constraint in meta.total_unique_constraints]
        for group in groups:
            if fk_name not in group:
                continue
            names = [name for name in group if name != fk_name]
            seen = []
            for index, form in enumerate(self.forms):
                if not form.is_valid() or (self.can_delete and self._should_delete_form(form)):
                    continue
                if index >= self.initial_form_count() and not form.has_changed():
                    continue
                key = tuple(getattr(form.instance, meta.get_field(name).attname) for name in names)
                if key in seen:
                    raise ValidationError(
                        "Please correct the duplicate data for %(fields)s, which must be unique.",
                        code="unique", params={"fields": ", ".join(names)})
                seen.append(key)

    def save(self, commit=True):
        saved = super().save(commit=False)
        sort_order_field = getattr(self.model, "sort_order_field", None)
        kept = []
        for index, form in enumerate(self.forms):
            if self.can_delete and self._should_delete_form(form):
                continue
            if index >= self.initial_form_count() and not form.has_changed():
                continue
            if sort_order_field and self.can_order:
                setattr(form.instance, sort_order_field, form.cleaned_data.get("ORDER"))
            kept.append(form.instance)
        manager = getattr(self.instance, self.rel_name)
        manager.set(kept)
        if commit:
            manager.commit()
            self.save_m2m()
        return saved


def childformset_factory(
    parent_model, model, form=ModelForm, formset=BaseChildFormSet, fk_name=None, fields=None, exclude=None,
    extra=3, can_order=False, can_delete=True, max_num=None, validate_max=False, min_num=None,
    validate_min=False, widgets=None, inherit_kwargs=None, formsets=None, exclude_formsets=None,
    formfield_callback=None,
):
    fk = _get_foreign_key(parent_model, model, fk_name=fk_name)
    exclude = list(exclude or []) + [fk.name]
    if fields is not None:
        fields = [name for name in fields if name != fk.name]
    if hasattr(model, "sort_order_field"):
        can_order = True
    if formsets is not None or exclude_formsets is not None:
        form = clusterform_factory(model, form=form, fields=fields, exclude=exclude,
                                   formsets=formsets, exclude_formsets=exclude_formsets)
    FormSet = transientmodelformset_factory(
        model, form=form, formset=formset, fields=fields, exclude=exclude, extra=extra, can_order=can_order,
        can_delete=can_delete, max_num=max_num, validate_max=validate_max, min_num=min_num,
        validate_min=validate_min, widgets=widgets, formfield_callback=formfield_callback)
    FormSet.fk = fk
    FormSet.inherit_kwargs = inherit_kwargs
    return FormSet


class ClusterFormMetaclass(ModelFormMetaclass):
    extra_form_count = 3

    def __new__(mcs, name, bases, attrs):
        new_class = super().__new__(mcs, name, bases, attrs)
        new_class.formsets = {}
        meta = getattr(new_class, "Meta", None)
        model = new_class._meta.model
        formsets = getattr(meta, "formsets", None)
        exclude_formsets = getattr(meta, "exclude_formsets", None)
        if model is None or (formsets is None and exclude_formsets is None):
            return new_class
        relations = {rel.get_accessor_name(): rel for rel in get_all_child_relations(model)}
        if formsets is None:
            options = {rel_name: {} for rel_name in relations if rel_name not in exclude_formsets}
        elif isinstance(formsets, dict):
            options = dict(formsets)
        else:
            options = {rel_name: {} for rel_name in formsets}
        widgets = getattr(meta, "widgets", None) or {}
        for rel_name, formset_options in options.items():
            formset_options = dict(formset_options or {})
            rel = relations[rel_name]
            formset_name = formset_options.pop("formset_name", rel_name)
            if rel_name in widgets and "widgets" not in formset_options:
                formset_options["widgets"] = widgets[rel_name]
            formset_options.setdefault("extra", mcs.extra_form_count)
            if "fields" not in formset_options and "exclude" not in formset_options:
                formset_options["exclude"] = []
            formset_class = childformset_factory(model, rel.related_model, fk_name=rel.field.name, **formset_options)
            formset_class.formset_name = formset_name
            new_class.formsets[rel_name] = formset_class
        return new_class


class ClusterForm(ModelForm, metaclass=ClusterFormMetaclass):
    def __init__(self, data=None, files=None, instance=None, prefix=None, **kwargs):
        super().__init__(data, files, instance=instance, prefix=prefix, **kwargs)
        self.formsets = {}
        for rel_name, formset_class in type(self).formsets.items():
            formset_prefix = formset_class.formset_name if prefix is None else f"{prefix}-{formset_class.formset_name}"
            inherited = {key: kwargs[key] for key in (formset_class.inherit_kwargs or []) if key in kwargs}
            self.formsets[rel_name] = formset_class(
                data, files, instance=self.instance, prefix=formset_prefix, form_kwargs=inherited)

    def has_changed(self):
        return super().has_changed() or any(formset.has_changed() for formset in self.formsets.values())

    def is_valid(self):
        form_is_valid = super().is_valid()
        if self.empty_permitted and not self.has_changed():
            return form_is_valid
        formsets_are_valid = all([formset.is_valid() for formset in self.formsets.values()])
        return form_is_valid and formsets_are_valid

    def as_p(self):
        return mark_safe(super().as_p() + "".join(formset.as_p() for formset in self.formsets.values()))

    @property
    def media(self):
        media = super().media
        for formset in self.formsets.values():
            media = media + formset.media
        return media

    def is_multipart(self):
        return super().is_multipart() or any(formset.is_multipart() for formset in self.formsets.values())

    def __apply_m2m(self, parental):
        cleaned_data = self.cleaned_data
        opts = self.instance._meta
        for field in chain(opts.many_to_many, opts.private_fields):
            if not hasattr(field, "save_form_data") or field.name not in cleaned_data:
                continue
            if self._meta.fields and field.name not in self._meta.fields:
                continue
            if self._meta.exclude and field.name in self._meta.exclude:
                continue
            if is_parental_field(field) == parental:
                field.save_form_data(self.instance, cleaned_data[field.name])

    def save(self, commit=True):
        instance = super().save(commit=False)
        self.__apply_m2m(parental=True)
        for formset in self.formsets.values():
            formset.save(commit=False)
        if commit:
            instance.save()
            self.__apply_m2m(parental=False)
        else:
            self.save_m2m = lambda: self.__apply_m2m(parental=False)
        return instance


def clusterform_factory(model, form=ClusterForm, fields=None, exclude=None, formfield_callback=None,
                        widgets=None, formsets=None, exclude_formsets=None, **meta_options):
    attrs = {"model": model}
    for key, value in [("fields", fields), ("exclude", exclude), ("widgets", widgets), ("formsets", formsets),
                       ("exclude_formsets", exclude_formsets), *meta_options.items()]:
        if value is not None:
            attrs[key] = value
    if formfield_callback:
        attrs["formfield_callback"] = staticmethod(formfield_callback)
    bases = (form.Meta,) if hasattr(form, "Meta") else ()
    meta = type("Meta", bases, attrs)
    if getattr(meta, "fields", None) is None and getattr(meta, "exclude", None) is None:
        raise ImproperlyConfigured("Calling clusterform_factory without defining 'fields' or 'exclude' is prohibited.")
    return type(form)(model.__name__ + "Form", (form,), {"Meta": meta})
