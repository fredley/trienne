# -*- coding: utf-8 -*-
import json
import re
import collections
import logging

from cgi import escape
from datetime import datetime
from urlparse import urlparse

from django.contrib.auth import get_user_model, authenticate
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.views.generic.base import TemplateView, View
from django.views.generic.edit import CreateView, UpdateView
from django.views.decorators.csrf import csrf_exempt
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
    logger.debug("line")
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
    room = Room.objects.get(id=kwargs['room_id'], organisation=self.request.user.current_organisation)
    if room.organisation not in self.request.user.organisations.all():
      raise PermissionDenied
    context.update(room=room,
                   prefs=RoomPrefs.objects.get_or_create(room=room, user=self.request.user)[0])
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
    post.pinned_at = datetime.now()
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
        'id': request.user.id
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


class RoomEditView(LoginRequiredMixin, UpdateView):
  template_name = "room_edit.html"
  fields = ['name', 'topic']
  model = Room
  pk_url_kwarg = 'room_id'

  def get_object(self):
    room = super(RoomEditView, self).get_object()
    if room.organisation not in request.user.organisations.all():
      raise PermissionDenied

  def get_success_url(self):
    return reverse("room", kwargs={"room_id": self.object.id})


class PostEditView(LoginRequiredMixin, View):

  @csrf_exempt
  def dispatch(self, *args, **kwargs):
    return super(PostEditView, self).dispatch(*args, **kwargs)

  def post(self, request, *args, **kwargs):
    post = Post.objects.get(id=request.POST.get('id'))
    if post.author != request.user:
      # TODO allow admins to edit posts
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

class RoomsView(LoginRequiredMixin, TemplateView):
  template_name = "rooms.html"

  def get_context_data(self, **kwargs):
    context = super(RoomsView, self).get_context_data(**kwargs)
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


class RegisterView(TemplateView):
  template_name = "registration/register.html"

  def post(self, request, *args, **kwargs):
    user = User.objects.create_user(request.POST['username'], '',
                                    request.POST['password'])
    user.save()
    authenticate(username=request.POST['username'], password=request.POST['password'])
    return HttpResponseRedirect(reverse('rooms'))
