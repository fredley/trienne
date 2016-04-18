# -*- coding: utf-8 -*-
import json
import re
import collections

from cgi import escape
from datetime import datetime
from urlparse import urlparse

from django.http import HttpResponse
from django.core.exceptions import PermissionDenied
from django.views.generic.base import TemplateView, View
from django.views.decorators.csrf import csrf_exempt
from ws4redis.redis_store import RedisMessage
from ws4redis.publisher import RedisPublisher

from .models import *

url_dot_test = re.compile(ur'.+\..+')


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


def markdown(text):
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
        raw = request.POST.get('message').strip()
        content = PostContent(
            author=request.user, 
            post=post, 
            raw=raw,
            content=markdown(escape(raw).replace("'","&#39;").replace("\n","<br>")))
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
