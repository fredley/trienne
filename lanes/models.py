import string
import random
import logging

from django.db import models
from django.db.models import Sum
from django.conf import settings
from django.contrib.auth.models import AbstractUser

from autoslug import AutoSlugField

logger = logging.getLogger('django')


class Organisation(models.Model):

  PRIVACY_OPEN = 0       # Anyone can join, no approval
  PRIVACY_APPLY = 1      # Anyone can apply to join
  PRIVACY_INVITE = 2     # Must have an invitation to join

  PRIVACY_CHOICES = (
      (PRIVACY_OPEN, "Open"),
      (PRIVACY_APPLY, "Application Only"),
      (PRIVACY_INVITE, "Invitation Only")
  )

  VISIBILITY_PUBLIC = 0   # Visible in search
  VISIBILITY_LINK = 1     # Not visible in search, accessible by link
  VISIBILITY_PRIVATE = 2  # Only accessible by invite

  VISIBILITY_CHOICES = (
      (VISIBILITY_PUBLIC, "Public"),
      (VISIBILITY_LINK, "Link Only"),
      (VISIBILITY_PRIVATE, "Private"),
  )

  name = models.CharField(max_length=200)
  domain = models.CharField(max_length=200)
  admins = models.ManyToManyField(settings.AUTH_USER_MODEL)
  privacy = models.IntegerField(choices=PRIVACY_CHOICES, default=PRIVACY_APPLY)
  visibility = models.IntegerField(choices=VISIBILITY_CHOICES, default=VISIBILITY_LINK)
  slug = AutoSlugField(populate_from='name', unique=True)

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

  def is_admin(self, org):
    return self in org.admins.all()

  def is_member(self, org):
    return org in self.organisations.all()

  def is_subscribed(self, org):
    return org in self.subscribed.all()

  def get_rooms(self):
    return Room.objects.filter(members__in=[self])

  def get_orgs(self):
    memberships = OrgMembership.objects.filter(user=self).values_list('organisation__pk', flat=True)
    return Organisation.objects.filter(id__in=memberships)

  def get_status(self, org):
    return OrgMembership.objects.get(user=self, organisation=org).status

  def can_view(self, room):
    if room.organisation not in self.organisations.all() and \
        room.organisation.visibility == Organisation.VISIBILITY_PRIVATE:
      logger.debug("not a member of private org")
      return False
    if room.privacy == Room.PRIVACY_PUBLIC:
      return True
    if self.is_admin(room.organisation):
      return True
    if self in room.members.all():
      return True
    logger.debug("Not a member or admin of private room")
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

  STATUS_ONLINE = 0
  STATUS_AWAY = 1
  STATUS_BUSY = 2
  STATUS_INVISIBLE = 3
  STATUS_OFFLINE = 4

  STATUS_CHOICES = (
      (STATUS_ONLINE, "online"),
      (STATUS_AWAY, "away"),
      (STATUS_BUSY, "busy"),
      (STATUS_INVISIBLE, "invisible"),
      (STATUS_OFFLINE, "offline")
  )

  user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
  organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE)
  status = models.IntegerField(choices=STATUS_CHOICES, default=STATUS_OFFLINE)
  role = models.IntegerField(choices=ROLES, default=USER)

  def __unicode__(self):
    return str(self.organisation) + " - " + str(self.user)


class OrgApplication(models.Model):

  organisation = models.ForeignKey(Organisation)
  user = models.ForeignKey(User)
  created = models.DateTimeField(auto_now_add=True)
  rejected = models.BooleanField(default=False)

  class Meta:
    unique_together = ('user', 'organisation',)


class Room(models.Model):

  PRIVACY_PUBLIC = 0   # Anyone can see, chat
  PRIVACY_PRIVATE = 1  # Only members and mods can see

  PRIVACY_CHOICES = (
      (PRIVACY_PUBLIC, "Public"),
      (PRIVACY_PRIVATE, "Private")
  )

  name = models.CharField(max_length=100)
  topic = models.CharField(max_length=200)
  organisation = models.ForeignKey(Organisation)
  creator = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='creator')
  created = models.DateTimeField(auto_now_add=True)
  owners = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='owners')
  members = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='members')
  privacy = models.IntegerField(choices=PRIVACY_CHOICES, default=PRIVACY_PRIVATE)

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
    try:
      return self.get_history()[0].raw
    except:
      return "(error)"

  def get_content(self):
    if self.deleted:
      return "(deleted)"
    try:
      return self.get_history()[0].content
    except:
      return "(error)"

  def get_history(self):
    qs = PostContent.objects.filter(post=self).order_by('-created')
    if self.deleted:
      return [qs[0]]
    else:
      return qs

  def is_edited(self):
    return PostContent.objects.filter(post=self).count() > 1

  def __unicode__(self):
    return str(self.author) + " in " + str(self.room) + " at " + str(self.created)

  content = property(get_content)
  raw = property(get_raw)
  edited = property(is_edited)
  score = property(get_score)
  history = property(get_history)


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
