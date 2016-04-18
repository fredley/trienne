from django.db import models
from django.conf import settings


class Organisation(models.Model):
  name = models.CharField(max_length=200)
  domain = models.CharField(max_length=200)
  admins = models.ManyToManyField(settings.AUTH_USER_MODEL)

  def __unicode__(self):
    return self.name


class Room(models.Model):
  name = models.CharField(max_length=100)
  topic = models.CharField(max_length=200)
  organisation = models.ForeignKey(Organisation)
  creator = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='creator')
  created = models.DateTimeField(auto_now_add=True)
  owners = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='owners')

  def __unicode__(self):
    return self.name


class Post(models.Model):
  room = models.ForeignKey(Room)
  author = models.ForeignKey(settings.AUTH_USER_MODEL)
  created = models.DateTimeField(auto_now_add=True)
  pinned = models.BooleanField(default=False)
  deleted = models.BooleanField(default=False)

  def get_content(self):
    if self.deleted:
      return "(deleted)"
    return self.author.username + ' - ' + PostContent.objects.filter(post=self).order_by('-created')[0].content

  content = property(get_content)

  def __unicode__(self):
    return self.content


class PostContent(models.Model):
  post = models.ForeignKey(Post)
  author = models.ForeignKey(settings.AUTH_USER_MODEL)
  content = models.CharField(max_length=512)
  created = models.DateTimeField(auto_now_add=True)

  def __unicode__(self):
    return self.content
