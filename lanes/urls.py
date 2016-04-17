# -*- coding: utf-8 -*-
from django.conf.urls import url, include
from django.core.urlresolvers import reverse_lazy
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.views.generic import RedirectView
from django.contrib import admin
from .views import *
admin.autodiscover()


urlpatterns = [
    url(r'^room/(?P<room_id>\d+)/$', RoomChatView.as_view(), name='chat_room'),
    url(r'^accounts/', include('django.contrib.auth.urls')),
    url(r'^admin/', include(admin.site.urls)),
    url(r'^$', RedirectView.as_view(url=reverse_lazy('broadcast_chat'))),
] + staticfiles_urlpatterns()
