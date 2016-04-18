# -*- coding: utf-8 -*-
import json

from django.http import HttpResponse
from django.core.exceptions import PermissionDenied
from django.views.generic.base import TemplateView, View
from django.views.decorators.csrf import csrf_exempt
from ws4redis.redis_store import RedisMessage
from ws4redis.publisher import RedisPublisher

from .models import *


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
        content = PostContent(author=request.user, post=post, content=request.POST.get('message'))
        content.save()
        message = {
            'type': 'msg',
            'author': {
                'name': request.user.username,
                'id': request.user.id
            },
            'content': request.POST.get('message'),
            'id': post.id
        }
        self.publisher.publish_message(RedisMessage(json.dumps(message)))
        return HttpResponse('OK')
