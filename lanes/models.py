from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractUser


class Organisation(models.Model):
  name = models.CharField(max_length=200)
  domain = models.CharField(max_length=200)
  admins = models.ManyToManyField(settings.AUTH_USER_MODEL)

  def __unicode__(self):
    return self.name

class User(AbstractUser):
  organisations = models.ManyToManyField(Organisation, through='OrgMembership')

class OrgMembership(models.Model):
  ADMIN = 0
  USER = 1
  ROLES = (
    (ADMIN, 'Admin'),
    (USER, 'User')
  )
  user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
  organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE)
  role = models.IntegerField(choices=ROLES, default=USER)

class Room(models.Model):
  name = models.CharField(max_length=100)
  topic = models.CharField(max_length=200)
  organisation = models.ForeignKey(Organisation)
  creator = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='creator')
  created = models.DateTimeField(auto_now_add=True)
  owners = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='owners')

  def get_history(self):
    posts = Post.objects.filter(room=self).order_by('-created')[:100]
    return posts[::-1]

  history = property(get_history)

  def get_pinned(self):
    posts = Post.objects.filter(room=self, pinned=True).order_by('-pinned_at')[:20]
    return posts[::-1]

  pinned = property(get_pinned)

  def __unicode__(self):
    return self.name


class Post(models.Model):
  room = models.ForeignKey(Room)
  author = models.ForeignKey(settings.AUTH_USER_MODEL)
  created = models.DateTimeField(auto_now_add=True)
  pinned = models.BooleanField(default=False)
  pinned_at = models.DateTimeField(null=True, default=None)
  deleted = models.BooleanField(default=False)

  def get_content(self):
    if self.deleted:
      return "(deleted)"
    return PostContent.objects.filter(post=self).order_by('-created')[0].content

  content = property(get_content)

  def __unicode__(self):
    return self.author.username + ' - ' + self.content


class PostContent(models.Model):
  post = models.ForeignKey(Post)
  author = models.ForeignKey(settings.AUTH_USER_MODEL)
  content = models.CharField(max_length=512)
  raw = models.CharField(max_length=512)
  created = models.DateTimeField(auto_now_add=True)

  def __unicode__(self):
    return self.content
