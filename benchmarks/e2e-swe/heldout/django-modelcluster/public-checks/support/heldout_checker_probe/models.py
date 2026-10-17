"""Checker subclasses of the public fields carrying generic private attribute names (T.R03.02)."""
from django.db import models

from modelcluster.fields import ParentalKey, ParentalManyToManyField
from modelcluster.models import ClusterableModel

PRIVATE_NAMES = ("_cache", "_items", "_parent", "_field")


def checker_private(self, *args, **kwargs):
    return "checker-private-sentinel"


def with_private_names(base):
    """A subclass of `base` defining each generic private name as a checker method."""
    return type("Checker" + base.__name__, (base,), {name: checker_private for name in PRIVATE_NAMES})


CheckerParentalKey = with_private_names(ParentalKey)
CheckerParentalManyToManyField = with_private_names(ParentalManyToManyField)
CheckerParentalKey.__module__ = CheckerParentalManyToManyField.__module__ = __name__


class ProbeBand(ClusterableModel):
    name = models.CharField(max_length=255)
    genres = CheckerParentalManyToManyField("heldout_checker_app.Genre", related_name="probe_bands", blank=True)


class ProbeMember(models.Model):
    band = CheckerParentalKey(ProbeBand, related_name="members", on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
