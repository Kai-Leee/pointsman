"""Checker-authored taggit models (loaded only for cases that need tags)."""
from django.db import models
from taggit.managers import TaggableManager
from taggit.models import TaggedItemBase

from modelcluster.contrib.taggit import ClusterTaggableManager
from modelcluster.fields import ParentalKey, ParentalManyToManyField
from modelcluster.models import ClusterableModel


class TaggedShop(TaggedItemBase):
    content_object = ParentalKey("Shop", related_name="tagged_items", on_delete=models.CASCADE)


class Shop(ClusterableModel):
    name = models.CharField(max_length=255)
    tags = ClusterTaggableManager(through=TaggedShop, blank=True)


class ShopReview(models.Model):
    shop = ParentalKey(Shop, related_name="reviews", on_delete=models.CASCADE)
    text = models.CharField(max_length=255)


class PlainTagged(ClusterableModel):
    name = models.CharField(max_length=255)
    tags = TaggableManager(blank=True)


class TaggedPost(TaggedItemBase):
    content_object = ParentalKey("Post", related_name="tagged_items", on_delete=models.CASCADE)


class Post(ClusterableModel):
    title = models.CharField(max_length=255)
    authors = ParentalManyToManyField("heldout_checker_app.Author", related_name="posts", blank=True)
    tags = ClusterTaggableManager(through=TaggedPost, blank=True)
    links = models.ManyToManyField("heldout_checker_app.Link", related_name="posts", blank=True)


class PostComment(models.Model):
    post = ParentalKey(Post, related_name="comments", on_delete=models.CASCADE)
    text = models.CharField(max_length=255)
