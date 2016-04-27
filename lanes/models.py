import string
import random
import logging

from django.db import models
from django.db.models import Sum
from django.conf import settings
from django.contrib.auth.models import AbstractUser

logger = logging.getLogger('django')


class Organisation(models.Model):
  name = models.CharField(max_length=200)
  domain = models.CharField(max_length=200)
  admins = models.ManyToManyField(settings.AUTH_USER_MODEL)

  def get_users(self):
    return User.objects.filter(organisations__id__exact=self.id)

  users = property(get_users)

  def __unicode__(self):
    return self.name


def generate_token():
  return ''.join(random.SystemRandom().choice(
      string.ascii_uppercase + string.digits + string.ascii_lowercase
  ) for _ in range(20))


class Invitation(models.Model):
  organisation = models.ForeignKey(Organisation)
  email = models.EmailField()
  token = models.CharField(max_length=20, default=generate_token, unique=True)

  def __unicode__(self):
    return self.organisation.name + " - " + self.email


class User(AbstractUser):
  organisations = models.ManyToManyField(Organisation, through='OrgMembership')
  subscribed = models.ManyToManyField(Organisation, related_name='subscribed')
  current_organisation = models.ForeignKey(Organisation, related_name='current_org', null=True, blank=True)

  def is_admin(self):
    try:
      return self in self.current_organisation.admins.all()
    except:
      return False

  def __unicode__(self):
    return self.username


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

  def __unicode__(self):
    return str(self.organisation) + " - " + str(self.user)


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


class RoomPrefs(models.Model):

  QUIET = 0
  NORMAL = 1
  LOUD = 2

  NOTIFICATION_CHOICES = (
      (QUIET, "Quiet - Nothing"),
      (NORMAL, "Normal - Mentions"),
      (LOUD, "Loud - Every message"))

  user = models.ForeignKey(settings.AUTH_USER_MODEL)
  room = models.ForeignKey(Room)
  volume = models.IntegerField(choices=NOTIFICATION_CHOICES, default=NORMAL)

  class Meta:
    unique_together = ('user', 'room',)

  def __unicode__(self):
    return str(self.room) + " - " + str(self.user)


class Post(models.Model):
  room = models.ForeignKey(Room)
  author = models.ForeignKey(settings.AUTH_USER_MODEL)
  created = models.DateTimeField(auto_now_add=True)
  pinned = models.BooleanField(default=False)
  pinned_at = models.DateTimeField(null=True, default=None)
  deleted = models.BooleanField(default=False)

  def get_score(self):
    res = 0
    try:
      res = Vote.objects.filter(post=self).aggregate(total=Sum('score')).get('total')
      if res is None:
        res = 0
    except:
      logger.error("Could not get score for Post " + str(self.id))
    return res

  def get_raw(self):
    if self.deleted:
      return "(deleted)"
    return PostContent.objects.filter(post=self).order_by('-created')[0].raw

  def get_content(self):
    if self.deleted:
      return "(deleted)"
    return PostContent.objects.filter(post=self).order_by('-created')[0].content

  def is_edited(self):
    return PostContent.objects.filter(post=self).count() > 1

  def __unicode__(self):
    return str(self.author) + " in " + str(self.room) + " at " + str(self.created)

  content = property(get_content)
  raw = property(get_raw)
  edited = property(is_edited)
  score = property(get_score)

  def __unicode__(self):
    return self.author.username + ' - ' + self.content


class Vote(models.Model):
  post = models.ForeignKey(Post)
  user = models.ForeignKey(User)
  score = models.IntegerField()
  created = models.DateTimeField(auto_now_add=True)

  def __unicode__(self):
    return str(self.user) + " on " + str(self.post)


class PostContent(models.Model):
  post = models.ForeignKey(Post)
  author = models.ForeignKey(settings.AUTH_USER_MODEL)
  content = models.CharField(max_length=512)
  raw = models.CharField(max_length=512)
  created = models.DateTimeField(auto_now_add=True)

  def __unicode__(self):
    return self.content
