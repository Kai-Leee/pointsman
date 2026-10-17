"""A ParentalKey declared without on_delete (T.R04.01)."""
from django.db import models

from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel


class DefaultBand(ClusterableModel):
    name = models.CharField(max_length=255)


class DefaultMember(models.Model):
    band = ParentalKey("DefaultBand", related_name="members")
    name = models.CharField(max_length=255)
