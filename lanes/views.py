# -*- coding: utf-8 -*-
import json
import re
import collections
import logging

from cgi import escape
from urlparse import urlparse

from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.conf import settings
from django.contrib.auth import get_user_model, authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.core.urlresolvers import reverse
from django.utils import timezone
from django.views.generic import DetailView
from django.views.generic.base import TemplateView, View
from django.views.generic.edit import CreateView, UpdateView
from django.views.decorators.csrf import csrf_exempt

from django_gravatar.helpers import get_gravatar_url

from ws4redis.redis_store import RedisMessage
from ws4redis.publisher import RedisPublisher

from .models import *

url_dot_test = re.compile(ur'.+\..+')
logger = logging.getLogger('django')
User = get_user_model()


def valid_link(text, image=False):
  if len(text.split(" ")) != 1 or '"' in text or "'" in text:
    return False
  url = urlparse(text)
  if image and url.path.lower().split(".")[-1] not in ["jpg", "jpeg", "png", "gif"]:
    return False
  return url.scheme in ['http', 'https'] and len(re.findall(url_dot_test, url.netloc)) > 0


def link_formatter(match_obj):
  link = match_obj.group(2).strip()
  if valid_link(link):
    return r'[{}]({})'.format(match_obj.group(1), match_obj.group(2))
  return r'<a href="{}" rel="nofollow">{}</a>'.format(link, match_obj.group(1))


def onebox(text):
  return '<div class="ob">{}</div>'.format(text)

md_rules = collections.OrderedDict()
md_rules[re.compile(r'\[([^\[]+)\]\(([^\)]+)\)')] = link_formatter    # links
md_rules[re.compile(r'(\*\*|__)(.*?)\1')] = r'<strong>\2</strong>'    # bold
md_rules[re.compile(r'(\*|_)(.*?)\1')] = r'<em>\2</em>'               # emphasis
md_rules[re.compile(r'\-\-\-(.*?)\-\-\-')] = r'<del>\1</del>'         # del
md_rules[re.compile(r'^&gt; (.*)')] = r'<blockquote>\1</blockquote>'  # quote
md_rules[re.compile(r'`(.*?)`')] = r'<code>\1</code>'                 # inline code


def process_text(text):
  # Check that message is not blank
  if text.strip() == "":
    raise
  # Check for entire block indented by 4 spaces
  is_code = True
  code = ""
  for line in text.split("\n"):
    if line[0:4] == "  ":
      code += line[4:] + "\n"
    else:
      is_code = False
      break
  if is_code:
    return "<pre>{}</pre>".format(escape(code).replace("'", "&#39;"))
  # Check for oneboxes
  # Images - entire message is an image url
  if valid_link(text, image=True):
    return onebox('<a href="{0}" rel="nofollow" target="_blank"><img src="{0}" alt="" onload="scrolldown()"></a>'.format(text))
  text = escape(text).replace("'", "&#39;").replace("\n", "<br>")
  # Apply Markdown rules
  for regex, replacement in md_rules.items():
    text = re.sub(regex, replacement, text)
  return text.strip()


class AjaxResponseMixin(object):
  def form_invalid(self, form):
    response = super(AjaxResponseMixin, self).form_invalid(form)
    if self.request.is_ajax():
      return JsonResponse(form.errors, status=400)
    else:
      return response

  def form_valid(self, form):
    response = super(AjaxResponseMixin, self).form_valid(form)
    if self.request.is_ajax():
      data = {
          'id': self.object.id,
      }
      return JsonResponse(data)
    else:
      return response


class AdminOnlyMixin(LoginRequiredMixin):

  def dispatch(self, *args, **kwargs):
    response = super(AdminOnlyMixin, self).dispatch(*args, **kwargs)
    if self.request.user.is_anonymous() or not self.request.user.is_admin():
      raise PermissionDenied
    return response


class RoomPostView(LoginRequiredMixin, View):

  @csrf_exempt
  def dispatch(self, *args, **kwargs):
    return super(RoomPostView, self).dispatch(*args, **kwargs)

  def post(self, request, *args, **kwargs):
    self.room = Room.objects.get(id=kwargs['room_id'])
    if self.room.organisation not in request.user.organisations.all():
      raise PermissionDenied
    self.publisher = RedisPublisher(facility='room_' + str(kwargs['room_id']), broadcast=True)
    return self.generate_response(request)


class RoomView(LoginRequiredMixin, TemplateView):
  template_name = 'room.html'

  def get_context_data(self, **kwargs):
    context = super(RoomView, self).get_context_data(**kwargs)
    room = Room.objects.get(id=kwargs['room_id'])
    if room.organisation not in self.request.user.organisations.all():
      raise PermissionDenied
    publisher = RedisPublisher(facility='room_' + str(kwargs['room_id']), broadcast=True)
    pinned = []
    for post in room.pinned:
      vote = 0
      try:
        vote = Vote.objects.get(post=post, user=self.request.user).score
      except:
        pass
      pinned.append({
          "post": post,
          "vote": vote
          })
    users = room.organisation.users
    online = []
    for u in users:
      online.append({
          "username": u.username,
          "id": u.id,
          "online": (publisher.get_present(u) or u == self.request.user)
      })
    message = {
        'type': 'join',
        'id': self.request.user.id,
        # Add this in case user is brand new and not in list
        'username': self.request.user.username
    }
    publisher.publish_message(RedisMessage(json.dumps(message)))
    context.update(room=room,
                   pinned=pinned,
                   prefs=RoomPrefs.objects.get_or_create(room=room, user=self.request.user)[0],
                   users=online)
    return context


class RoomPrefsView(RoomPostView):

  def generate_response(self, request):
    volume = int(request.POST.get('volume'))
    prefs = RoomPrefs.objects.get(room=self.room, user=request.user)
    prefs.volume = volume
    prefs.save()
    return HttpResponse('OK')


class RoomPinView(RoomPostView):

  def generate_response(self, request):
    post = Post.objects.get(id=request.POST.get('id'))
    action = 'unpin' if post.pinned else 'pin'
    post.pinned = not post.pinned
    post.pinned_at = timezone.now()
    post.save()
    message = {
        'type': 'pin',
        'action': action,
        'content': post.id
    }
    self.publisher.publish_message(RedisMessage(json.dumps(message)))
    return HttpResponse('OK')


class RoomMessageView(RoomPostView):

  def generate_response(self, request):
    post = Post(room=self.room, author=request.user)
    post.save()
    raw = request.POST.get('message')
    try:
        processed = process_text(raw)
    except:
        return HttpResponse('Not OK')
    content = PostContent(
        author=request.user,
        post=post,
        raw=raw,
        content=processed)
    content.save()
    message = {
        'type': 'msg',
        'author': {
            'name': request.user.username,
            'id': request.user.id,
            'img': get_gravatar_url(request.user.email, size=32)
        },
        'content': post.content,
        'raw': raw,
        'id': post.id
    }
    self.publisher.publish_message(RedisMessage(json.dumps(message)))
    return HttpResponse('OK')


class RoomAddView(CreateView):
  model = Room
  fields = ['name', 'topic', 'organisation']
  template_name = "add_room.html"

  def form_valid(self, form):
    room = form.save(commit=False)
    room.creator = self.request.user
    room.save()
    room.owners = [self.request.user]
    self.object = room
    return HttpResponseRedirect(reverse("room", kwargs={"room_id": room.id}))


class RoomEditView(AdminOnlyMixin, UpdateView):
  template_name = "room_edit.html"
  fields = ['name', 'topic']
  model = Room
  pk_url_kwarg = 'room_id'

  def get_success_url(self):
    return reverse("room", kwargs={"room_id": self.object.id})


class PostEditView(LoginRequiredMixin, View):

  @csrf_exempt
  def dispatch(self, *args, **kwargs):
    return super(PostEditView, self).dispatch(*args, **kwargs)

  def post(self, request, *args, **kwargs):
    post = Post.objects.get(id=request.POST.get('id'))
    if post.author != request.user and not request.user.is_admin():
      raise PermissionDenied
    raw = request.POST.get('message')
    try:
        processed = process_text(raw)
    except:
        return HttpResponse('Not OK')
    content = PostContent(
        author=request.user,
        post=post,
        raw=raw,
        content=processed)
    content.save()
    message = {
        'type': 'edit',
        'content': processed,
        'raw': raw,
        'id': post.id
    }
    RedisPublisher(facility='room_' + str(post.room.id), broadcast=True) \
        .publish_message(RedisMessage(json.dumps(message)))
    return HttpResponse('OK')


class PostVoteView(LoginRequiredMixin, View):

  @csrf_exempt
  def dispatch(self, *args, **kwargs):
    return super(PostVoteView, self).dispatch(*args, **kwargs)

  def post(self, request, *args, **kwargs):
    post = Post.objects.get(id=request.POST.get('id'))
    if post.author == request.user:
      raise PermissionDenied
    value = int(request.POST.get('value'))
    if value not in [-1, 1]:
      raise PermissionDenied
    if Vote.objects.filter(post=post,user=request.user).count() > 0:
      raise PermissionDenied
    vote = Vote(post=post,
        user=request.user,
        score=value)
    vote.save()
    message = {
        'type': 'vote',
        'content': post.score,
        'id': post.id
    }
    RedisPublisher(facility='room_' + str(post.room.id), broadcast=True) \
        .publish_message(RedisMessage(json.dumps(message)))
    return HttpResponse('OK')


class RoomsView(LoginRequiredMixin, TemplateView):
  template_name = "rooms.html"

  def get_context_data(self, **kwargs):
    context = super(RoomsView, self).get_context_data(**kwargs)
    if not self.request.user.current_organisation and self.request.user.organisations.all().count() == 1:
      self.request.user.current_organisation = self.request.user.organisations.all()[0]
      self.request.user.save()
    context.update(rooms=Room.objects.filter(organisation=self.request.user.current_organisation))
    return context


class ChangeOrg(LoginRequiredMixin, View):

  def post(self, request, *args, **kwargs):
    user = request.user
    org = Organisation.objects.get(id=request.POST.get('org'))
    if org in user.organisations.all():
      user.current_organisation = org
      user.save()
    else:
      raise PermissionDenied
    return HttpResponseRedirect(reverse('rooms'))


class UserManagementView(AdminOnlyMixin, AjaxResponseMixin, CreateView):

  template_name = "user_management.html"
  model = Invitation
  fields = ['organisation', 'email']

  def get_success_url(self):
    return ''

  def get_context_data(self, **kwargs):
    context = super(UserManagementView, self).get_context_data(**kwargs)
    context.update(org=self.request.user.current_organisation)
    return context

  def form_valid(self, form):
    response = super(UserManagementView, self).form_valid(form)  # Saves form
    org = form.instance.organisation
    link = 'http://' + settings.ALLOWED_HOSTS[0] + reverse('invitation', kwargs={'token': form.instance.token})
    send_mail('Join {} on lanes'.format(org.name),
        'You have been invited to join {} on lanes, please click this link to sign up:\n\n{}'.format(org.name, link),
        'noreply@lanes.net',
    [form.instance.email], fail_silently=True)
    return response


class UserProfileView(DetailView):
  model = User
  pk_url_kwarg = 'user_id'
  template_name = 'user_profile.html'
  context_object_name = 'puser'


class RegisterView(TemplateView):
  template_name = "registration/register.html"

  def get_context_data(self, **kwargs):
    context = super(RegisterView, self).get_context_data(**kwargs)
    if 'token' in kwargs:
      logout(self.request)
      context.update(invite=Invitation.objects.get(token=kwargs.get('token')))
    return context

  def post(self, request, *args, **kwargs):
    user = User.objects.create_user(request.POST['username'], request.POST['email'],
                                    request.POST['password'])
    user.save()
    org = Organisation.objects.get(id=request.POST.get('organisation'))
    invites = Invitation.objects.filter(email=request.POST.get('email'), organisation=org)
    if invites.count() == 0:
      raise PermissionDenied
    membership = OrgMembership(user=user, organisation=org)
    membership.save()
    [i.delete() for i in invites]
    u = authenticate(username=request.POST['username'], password=request.POST['password'])
    if u is not None and u.is_active:
      login(request, u)
    return HttpResponseRedirect(reverse('rooms'))
