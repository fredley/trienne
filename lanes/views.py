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
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.views.generic.base import TemplateView, View
from django.views.decorators.csrf import csrf_exempt
from ws4redis.redis_store import RedisMessage
from ws4redis.publisher import RedisPublisher

from .models import *

url_dot_test = re.compile(ur'.+\..+')
logger = logging.getLogger('django')
User = get_user_model()


def link_formatter(match_obj):
  link = match_obj.group(2).strip()
  url = urlparse(link)
  if url.scheme not in ['http', 'https'] or len(re.findall(url_dot_test, url.netloc)) == 0:
    return r'[{}]({})'.format(match_obj.group(1), match_obj.group(2))
  return r'<a href="{}">{}</a>'.format(link, match_obj.group(1))

md_rules = collections.OrderedDict()
md_rules[re.compile(r'\[([^\[]+)\]\(([^\)]+)\)')] = link_formatter # links
md_rules[re.compile(r'(\*\*|__)(.*?)\1')] = r'<strong>\2</strong>' # bold
md_rules[re.compile(r'(\*|_)(.*?)\1')] = r'<em>\2</em>' # emphasis
md_rules[re.compile(r'\-\-\-(.*?)\-\-\-')] = r'<del>\1</del>' # del
md_rules[re.compile(r'^&gt; (.*)')] = r'<blockquote>\1</blockquote>' # quote
md_rules[re.compile(r'`(.*?)`')] = r'<code>\1</code>' # inline code


def process_text(text):
  # Check for entire block indented by 4 spaces
  logger.debug("Hello")
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
    return "<pre>{}</pre>".format(escape(code).replace("'","&#39;"))
  text = escape(text).replace("'","&#39;").replace("\n","<br>")
  # Apply Markdown rules
  for regex, replacement in md_rules.items():
    text = re.sub(regex, replacement, text)
  return text.strip()


class RoomPostView(View):

  @csrf_exempt
  def dispatch(self, *args, **kwargs):
    return super(RoomPostView, self).dispatch(*args, **kwargs)

  def post(self, request, *args, **kwargs):
    if not request.user.is_authenticated():
      raise PermissionDenied
    self.room = Room.objects.get(id=kwargs['room_id'])
    self.publisher = RedisPublisher(facility='room_' + str(kwargs['room_id']), broadcast=True)
    return self.generate_response(request)


class RoomView(TemplateView):
  template_name = 'room.html'

  def get_context_data(self, **kwargs):
    context = super(RoomView, self).get_context_data(**kwargs)
    context.update(room=Room.objects.get(id=kwargs['room_id']))
    return context

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
    content = PostContent(
      author=request.user, 
      post=post, 
      raw=raw,
      content=process_text(raw))
    content.save()
    message = {
      'type': 'msg',
      'author': {
        'name': request.user.username,
        'id': request.user.id
      },
      'content': post.content,
      'id': post.id
    }
    self.publisher.publish_message(RedisMessage(json.dumps(message)))
    return HttpResponse('OK')


class RoomsView(TemplateView):
  template_name = "rooms.html"

  def get_context_data(self, **kwargs):
    context = super(RoomsView, self).get_context_data(**kwargs)
    context.update(rooms=Room.objects.all())
    return context


class RegisterView(TemplateView):
  template_name = "registration/register.html"

  def post(self, request, *args, **kwargs):
    user = User.objects.create_user(request.POST['username'],'',
                                    request.POST['password'])
    user.save()
    authenticate(username=request.POST['username'], password=request.POST['password'])
    return HttpResponseRedirect(reverse('rooms'))
