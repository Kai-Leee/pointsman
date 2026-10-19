"""Checker-authored test models (core). Written from the public instruction's examples only."""
from django.db import models

from modelcluster.fields import ParentalKey, ParentalManyToManyField
from modelcluster.models import ClusterableModel


class Genre(models.Model):
    name = models.CharField(max_length=255)


class Fan(models.Model):
    name = models.CharField(max_length=255)


class Chef(models.Model):
    name = models.CharField(max_length=255)


class Company(models.Model):
    name = models.CharField(max_length=255)


class Cuisine(models.Model):
    name = models.CharField(max_length=255)


class Band(ClusterableModel):
    name = models.CharField(max_length=255)
    genres = ParentalManyToManyField(Genre, blank=True)
    fans = models.ManyToManyField(Fan, blank=True)


class Place(ClusterableModel):
    name = models.CharField(max_length=255)


class Restaurant(Place):
    serves_hot_dogs = models.BooleanField(default=False)
    proprietor = models.ForeignKey(Chef, null=True, blank=True, on_delete=models.SET_NULL, related_name="restaurants")
    head_chef = models.OneToOneField(Chef, null=True, blank=True, on_delete=models.SET_NULL, related_name="restaurant_headed")
    opened_at = models.DateTimeField(null=True, blank=True)
    cuisines = ParentalManyToManyField(Cuisine, blank=True)


class BandMember(models.Model):
    band = ParentalKey("Band", related_name="members", on_delete=models.CASCADE)
    name = models.CharField(max_length=255, null=True)
    age = models.IntegerField(null=True, blank=True)
    joined = models.DateField(null=True, blank=True)
    favourite_restaurant = models.ForeignKey(Restaurant, null=True, blank=True, on_delete=models.SET_NULL)
    secret = models.CharField(max_length=255, blank=True, default="", serialize=False)


class Album(ClusterableModel):
    band = ParentalKey(Band, related_name="albums", on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    release_date = models.DateField(null=True, blank=True)


class Song(models.Model):
    album = ParentalKey(Album, related_name="songs", on_delete=models.CASCADE)
    title = models.CharField(max_length=255)


class Choir(ClusterableModel):
    name = models.CharField(max_length=255)


class Singer(models.Model):
    choir = ParentalKey(Choir, related_name="singers", on_delete=models.CASCADE)
    name = models.CharField(max_length=255)

    class Meta:
        ordering = ["name"]


class Author(models.Model):
    name = models.CharField(max_length=255)

    class Meta:
        ordering = ["name"]


class Link(models.Model):
    url = models.CharField(max_length=255)


class Category(models.Model):
    name = models.CharField(max_length=255)


class Article(ClusterableModel):
    title = models.CharField(max_length=255)
    authors = ParentalManyToManyField(Author, related_name="articles_by_author", blank=True)
    links = models.ManyToManyField(Link, blank=True)


class FeatureArticle(Article):
    categories = ParentalManyToManyField(Category, blank=True)


class Review(models.Model):
    place = ParentalKey(Place, related_name="reviews", on_delete=models.CASCADE)
    author = models.CharField(max_length=255)


class MenuItem(ClusterableModel):
    restaurant = ParentalKey(Restaurant, related_name="menu_items", on_delete=models.CASCADE)
    name = models.CharField(max_length=255)

    class Meta:
        ordering = ["name"]


class Ingredient(models.Model):
    item = ParentalKey(MenuItem, related_name="ingredients", on_delete=models.CASCADE)
    name = models.CharField(max_length=255)


class Visit(models.Model):
    place = models.ForeignKey(Place, on_delete=models.CASCADE)
    note = models.CharField(max_length=255, blank=True, default="")


class Diner(models.Model):
    name = models.CharField(max_length=255)
    favourite_restaurant = models.ForeignKey(Restaurant, null=True, blank=True, on_delete=models.SET_NULL)


class Log(models.Model):
    name = models.CharField(max_length=255, null=True, blank=True)
    score = models.IntegerField(null=True, blank=True)
    time = models.DateTimeField(null=True, blank=True)
    d = models.DateField(null=True, blank=True)
    flag = models.BooleanField(default=False)


class Alarm(models.Model):
    t = models.TimeField()


class RangeRow(models.Model):
    range = models.IntegerField()


class Venue(models.Model):
    name = models.CharField(max_length=255)
    city = models.CharField(max_length=255)


class Event(ClusterableModel):
    name = models.CharField(max_length=255)
    when = models.DateTimeField(null=True, blank=True)


class Document(ClusterableModel):
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to="docs", blank=True)


class Tour(ClusterableModel):
    name = models.CharField(max_length=255)
    sponsor = models.ForeignKey(Company, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    headliner = models.ForeignKey(Company, null=True, blank=True, on_delete=models.CASCADE, related_name="+")


class TourStop(models.Model):
    tour = ParentalKey(Tour, related_name="stops", on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    venue = models.ForeignKey(Company, null=True, on_delete=models.CASCADE, related_name="+")
    sponsor = models.ForeignKey(Company, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")


class Studio(ClusterableModel):
    name = models.CharField(max_length=255)
    hidden_genres = ParentalManyToManyField(Genre, blank=True, serialize=False, related_name="+")


class StudioNote(models.Model):
    studio = ParentalKey(Studio, related_name="notes", on_delete=models.CASCADE, serialize=False)
    text = models.CharField(max_length=255)


class StudioEngineer(models.Model):
    studio = ParentalKey(Studio, related_name="engineers", on_delete=models.CASCADE)
    name = models.CharField(max_length=255)


class Gig(ClusterableModel):
    name = models.CharField(max_length=255)


class GigSong(models.Model):
    gig = ParentalKey(Gig, related_name="gig_songs", on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    sort_order = models.IntegerField(null=True, blank=True, editable=False)
    sort_order_field = "sort_order"


class Gallery(ClusterableModel):
    name = models.CharField(max_length=255)


class Photo(models.Model):
    gallery = ParentalKey(Gallery, related_name="photos", on_delete=models.CASCADE)
    image = models.FileField(upload_to="photos", blank=True)


class UBand(ClusterableModel):
    name = models.CharField(max_length=255)


class UTMember(models.Model):
    band = ParentalKey(UBand, related_name="ut_members", on_delete=models.CASCADE)
    name = models.CharField(max_length=255)

    class Meta:
        unique_together = [("band", "name")]


class UCMember(models.Model):
    band = ParentalKey(UBand, related_name="uc_members", on_delete=models.CASCADE)
    name = models.CharField(max_length=255)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["band", "name"], name="heldout_uc_member_unique")]
