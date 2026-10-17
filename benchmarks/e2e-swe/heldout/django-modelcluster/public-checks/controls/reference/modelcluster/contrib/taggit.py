"""ClusterTaggableManager: taggit tags held in memory through a ParentalKey tagged-item relation."""
from taggit.managers import TaggableManager, _TaggableManager

from modelcluster.fields import in_memory_objects
from modelcluster.queryset import FakeQuerySet


class _ClusterTaggableManager(_TaggableManager):
    def get_tagged_item_manager(self):
        rel = self.through._meta.get_field("content_object").remote_field
        return getattr(self.instance, rel.get_accessor_name()), rel.get_accessor_name()

    def get_queryset(self, extra_filters=None):
        if self.instance is None:
            return super().get_queryset(extra_filters)
        manager, name = self.get_tagged_item_manager()
        if self.instance.pk is None or in_memory_objects(self.instance, name) is not None:
            return FakeQuerySet(self.through.tag_model(), [item.tag for item in manager.all()])
        return super().get_queryset(extra_filters)

    def add(self, *tags, **kwargs):
        manager, _ = self.get_tagged_item_manager()
        current = [item.tag for item in manager.all()]
        new_items = [self.through(tag=tag) for tag in self._to_tag_model_instances(tags, {}) if tag not in current]
        manager.add(*new_items)

    def remove(self, *tags):
        manager, _ = self.get_tagged_item_manager()
        names = {tag if isinstance(tag, str) else tag.name for tag in tags}
        manager.set([item for item in manager.all() if item.tag.name not in names])

    def clear(self):
        manager, _ = self.get_tagged_item_manager()
        manager.clear()

    def set(self, tags, *, through_defaults=None, **kwargs):
        manager, _ = self.get_tagged_item_manager()
        wanted = self._to_tag_model_instances(tags, {})
        kept = [item for item in manager.all() if item.tag in wanted]
        kept_tags = [item.tag for item in kept]
        manager.set(kept + [self.through(tag=tag) for tag in wanted if tag not in kept_tags])


class ClusterTaggableManager(TaggableManager):
    def __get__(self, instance, model):
        return _ClusterTaggableManager(
            through=self.through, model=model, instance=instance,
            prefetch_cache_name=self.name, ordering=self.ordering)

    def value_from_object(self, obj):
        return list(getattr(obj, self.name).all())
