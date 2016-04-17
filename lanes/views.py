# -*- coding: utf-8 -*-
from django.http import HttpResponse
from django.core.exceptions import PermissionDenied
from django.views.generic.base import TemplateView
from django.views.decorators.csrf import csrf_exempt
from ws4redis.redis_store import RedisMessage
from ws4redis.publisher import RedisPublisher

from .models import *


class RoomChatView(TemplateView):
    template_name = 'broadcast_chat.html'

    def get_context_data(self, **kwargs):
        context = super(RoomChatView, self).get_context_data(**kwargs)
        context.update(room=Room.objects.get(id=kwargs['room_id']))
        return context

    @csrf_exempt
    def dispatch(self, *args, **kwargs):
        return super(RoomChatView, self).dispatch(*args, **kwargs)

    def post(self, request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated():
            raise PermissionDenied
        room = Room.objects.get(id=kwargs['room_id'])
        post = Post(room=room, author=user)
        post.save()
        content = PostContent(author=user, post=post, content=request.POST.get('message'))
        content.save()
        redis_publisher = RedisPublisher(facility='room_' + str(kwargs['room_id']))
        message = RedisMessage(request.POST.get('message'))
        redis_publisher.publish_message(message)
        return HttpResponse('OK')
