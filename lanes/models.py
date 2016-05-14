import string
import random
import json
import logging
import math

from datetime import datetime, timedelta

from django.db import models
from django.db.models import Sum
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.utils import timezone

from django_gravatar.helpers import get_gravatar_url

from ws4redis.redis_store import RedisMessage
from ws4redis.publisher import RedisPublisher

from autoslug import AutoSlugField


logger = logging.getLogger('django')

epoch = timezone.make_aware(datetime(1970, 1, 1), timezone.get_current_timezone())


class Organisation(models.Model):
  """ An organisation or community """

  PRIVACY_OPEN = 0       # Anyone can join, no approval
  PRIVACY_APPLY = 1      # Anyone can apply to join
  PRIVACY_INVITE = 2     # Must have an invitation to join
  PRIVACY_ORG = 3        # Must be a member of an org

  PRIVACY_CHOICES = (
      (PRIVACY_OPEN, "Open"),
      (PRIVACY_APPLY, "Application Only"),
      (PRIVACY_INVITE, "Invitation Only"),
      (PRIVACY_ORG, "Your domain")
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
  domain = models.CharField(max_length=200, unique=True, null=True, blank=True)
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
  """ An invitation to join a specific org """
  organisation = models.ForeignKey(Organisation)
  email = models.EmailField()
  token = models.CharField(max_length=20, default=generate_token, unique=True)

  def __unicode__(self):
    return self.organisation.name + " - " + self.email


class Bot(models.Model):
  """ A profile for a bot, which belongs to a bot user """
  SCOPE_GLOBAL = 0
  SCOPE_LOCAL = 1

  SCOPES = ((SCOPE_GLOBAL, "All rooms"),
            (SCOPE_LOCAL, "Only certain rooms"),)

  notify_url = models.URLField()  # URL to hit with @pings
  notify_key = models.CharField(max_length=20, default=generate_token)  # Key to include in notifications
  organisation = models.ForeignKey(Organisation, related_name="org")
  rooms = models.ManyToManyField('Room', blank=True)
  scope = models.IntegerField(choices=SCOPES, default=SCOPE_LOCAL)
  owner = models.ForeignKey('User', related_name="owner")

  def responds_to(self, room):
    return room in self.rooms.all() or (room.organisation == self.organisation and
                                        self.scope == self.SCOPE_GLOBAL)

  def get_tokens(self):
    return BotToken.objects.filter(bot=self)

  def __unicode__(self):
    try:
      return self.organisation.name + ": " + self.user.username
    except:
      return self.organisation.name + " (no user yet)"


class BotToken(models.Model):
  """ A token used by bots to authenticate """
  bot = models.ForeignKey(Bot)
  token = models.CharField(max_length=20, default=generate_token, unique=True)
  created = models.DateTimeField(auto_now_add=True)


class User(AbstractUser):
  """ A user """

  is_bot = models.BooleanField(default=False)
  bot = models.OneToOneField(Bot, null=True)
  organisations = models.ManyToManyField(Organisation, through='OrgMembership')
  subscribed = models.ManyToManyField(Organisation, related_name='subscribed', blank=True)

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

  def notify(self, post):
    if self.is_bot and self.bot.responds_to(post.room):
      from .tasks import ping_bot
      ping_bot.delay(post, self)
    elif self.get_status(post.room.organisation) in [OrgMembership.STATUS_AWAY, OrgMembership.STATUS_OFFLINE]:
      Notification(post=post, user=self).save()

  def set_status(self, org, status):
    m = OrgMembership.objects.get(user=self, organisation=org)
    m.status = status
    m.save()
    message = {
        "type": "status",
        "id": self.id,
        "status": m.status,
        "username": self.username,
        "img": get_gravatar_url(self.email, size=32)
    }
    RedisPublisher(facility='org_' + org.slug, broadcast=True) \
        .publish_message(RedisMessage(json.dumps(message)))

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

  def ban_for(self, org, seconds):
    membership = OrgMembership.objects.get(user=self, organisation=org)
    membership.ban_expiry = timezone.now() + timedelta(0, seconds)
    membership.save()
    BanLog(user=self, organisation=org, duration=seconds).save()

  def unban(self, org):
    membership = OrgMembership.objects.get(user=self, organisation=org)
    membership.ban_expiry = None
    membership.save()
    BanLog(user=self, organisation=org, duration=0).save()

  def is_banned(self, org):
    membership = OrgMembership.objects.get(user=self, organisation=org)
    if membership.ban_expiry is not None:
      if timezone.now() < membership.ban_expiry:
        return True
      else:
        membership.ban_expiry = None
        membership.save()
        return False
    else:
      return False

  def __unicode__(self):
    return self.username


class OrgMembership(models.Model):
  """ through class for user membership of orgs """
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
  status = models.IntegerField(choices=STATUS_CHOICES, default=STATUS_ONLINE)
  role = models.IntegerField(choices=ROLES, default=USER)
  ban_expiry = models.DateTimeField(null=True, blank=True)

  class Meta:
    unique_together = ('user', 'organisation',)

  def __unicode__(self):
    return str(self.organisation) + " - " + str(self.user)


class OrgApplication(models.Model):
  """ An application by a user to an organisation """

  organisation = models.ForeignKey(Organisation)
  user = models.ForeignKey(User)
  created = models.DateTimeField(auto_now_add=True)
  rejected = models.BooleanField(default=False)

  class Meta:
    unique_together = ('user', 'organisation',)


class Room(models.Model):
  """ A chat room """

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
    posts = Post.objects.filter(room=self, pinned=True).order_by('-hotness')[:20]
    return posts[::-1]

  pinned = property(get_pinned)

  def __unicode__(self):
    return self.name


class RoomPrefs(models.Model):
  """ A user's preferences for a room """

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
  """ A chat post """
  room = models.ForeignKey(Room)
  author = models.ForeignKey(settings.AUTH_USER_MODEL)
  created = models.DateTimeField(auto_now_add=True)
  pinned = models.BooleanField(default=False)
  pinned_at = models.DateTimeField(null=True, default=None)
  deleted = models.BooleanField(default=False)
  hotness = models.FloatField(default=10000.0)

  def get_score(self):
    res = 0
    try:
      res = Vote.objects.filter(post=self).aggregate(total=Sum('score')).get('total')
      if res is None:
        res = 0
    except:
      logger.error("Could not get score for Post " + str(self.id))
    return res

  def get_flags(self):
    res = 0
    try:
      res = Flag.objects.filter(post=self).aggregate(total=Sum('score')).get('total')
      if res is None:
        res = 0
    except:
      logger.error("Could not get flags for Post " + str(self.id))
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

  def remove(self, user):
    self.deleted = True
    self.pinned = False
    self.save()
    content = PostContent(
        author=user,
        post=self,
        raw="(deleted)",
        content="(deleted)")
    content.save()

  def is_edited(self):
    return PostContent.objects.filter(post=self).count() > 1

  def update_hotness(self, score=None):
    if score is None:
      score = self.get_score()
    order = math.log(max(abs(score), 1), 10)
    sign = 1 if score > 0 else -1 if score < 0 else 0
    td = self.pinned_at - epoch
    seconds = td.days * 86400 + td.seconds + (float(td.microseconds) / 1000000) - 1134028003
    self.hotness = round(sign * order + seconds / 45000, 7)
    self.save()

  def __unicode__(self):
    return str(self.author) + " in " + str(self.room) + " at " + str(self.created)

  content = property(get_content)
  raw = property(get_raw)
  edited = property(is_edited)
  score = property(get_score)
  history = property(get_history)


class Vote(models.Model):
  """ A vote on a post """
  post = models.ForeignKey(Post)
  user = models.ForeignKey(User)
  score = models.IntegerField()
  created = models.DateTimeField(auto_now_add=True)

  class Meta:
    unique_together = ('post', 'user',)

  def __unicode__(self):
    return str(self.user) + " on " + str(self.post)


class PostContent(models.Model):
  """ The contents of a post """
  post = models.ForeignKey(Post)
  author = models.ForeignKey(settings.AUTH_USER_MODEL)
  content = models.CharField(max_length=512)
  raw = models.CharField(max_length=512)
  created = models.DateTimeField(auto_now_add=True)

  def __unicode__(self):
    return self.content


class Flag(models.Model):
  """ A flag against a post """
  post = models.ForeignKey(Post)
  flagger = models.ForeignKey(User)
  created = models.DateTimeField(auto_now_add=True)

  class Meta:
    unique_together = ('post', 'flagger',)


class Notification(models.Model):
  """ A notification that needs to be sent - deleted when sent """
  user = models.ForeignKey(settings.AUTH_USER_MODEL)
  post = models.ForeignKey(Post)
  created = models.DateTimeField(auto_now_add=True)


class ResetToken(models.Model):
  """ A token for resetting passwords """
  user = models.ForeignKey(settings.AUTH_USER_MODEL)
  token = models.CharField(max_length=20, default=generate_token, unique=True)


class BanLog(models.Model):
  """ A log of a ban given to a user """
  user = models.ForeignKey(User)
  organisation = models.ForeignKey(Organisation)
  duration = models.IntegerField()  # In seconds, if 0 is unban
  created = models.DateTimeField(auto_now_add=True)

class InvitationRequest(models.Model):
  """ A request for an invitation """
  email = models.EmailField()
  created = models.DateTimeField(auto_now_add=True)
