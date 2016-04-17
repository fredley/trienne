from django.db import models
from django.conf import settings


class Organisation(models.Model):
  name = models.CharField(max_length=200)
  domain = models.CharField(max_length=200)
  admins = models.ManyToManyField(settings.AUTH_USER_MODEL)


class Room(models.Model):
  name = models.CharField(max_length=100)
  topic = models.CharField(max_length=200)
  organisation = models.ForeignKey(Organisation)
  creator = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='creator')
  created = models.DateTimeField(auto_now_add=True)
  owners = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='owners')


class Post(models.Model):
  room = models.ForeignKey(Room)
  author = models.ForeignKey(settings.AUTH_USER_MODEL)
  created = models.DateTimeField(auto_now_add=True)
  pinned = models.BooleanField(default=False)
  deleted = models.BooleanField(default=False)


class PostContent(models.Model):
  post = models.ForeignKey(Post)
  author = models.ForeignKey(settings.AUTH_USER_MODEL)
  content = models.CharField(max_length=512)
  created = models.DateTimeField(auto_now_add=True)
