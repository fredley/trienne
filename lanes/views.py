# -*- coding: utf-8 -*-
import json

from django.http import HttpResponse
from django.core.exceptions import PermissionDenied
from django.views.generic.base import TemplateView, View
from django.views.decorators.csrf import csrf_exempt
from ws4redis.redis_store import RedisMessage
from ws4redis.publisher import RedisPublisher

from .models import *


class RoomView(TemplateView):
    template_name = 'room.html'

    def get_context_data(self, **kwargs):
        context = super(RoomView, self).get_context_data(**kwargs)
        context.update(room=Room.objects.get(id=kwargs['room_id']))
        return context


class RoomMessageView(View):
    @csrf_exempt
    def dispatch(self, *args, **kwargs):
        return super(RoomMessageView, self).dispatch(*args, **kwargs)

    def post(self, request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated():
            raise PermissionDenied
        room = Room.objects.get(id=kwargs['room_id'])
        post = Post(room=room, author=user)
        post.save()
        content = PostContent(author=user, post=post, content=request.POST.get('message'))
        content.save()
        redis_publisher = RedisPublisher(facility='room_' + str(kwargs['room_id']), broadcast=True)
        message = {
            'type': 'msg',
            'author': user.get_full_name(),
            'content': request.POST.get('message')
        }
        redis_publisher.publish_message(RedisMessage(json.dumps(message)))
        return HttpResponse('OK')
