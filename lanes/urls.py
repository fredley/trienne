# -*- coding: utf-8 -*-
from django.conf.urls import url, include
from django.core.urlresolvers import reverse_lazy
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.views.generic import RedirectView
from django.contrib import admin
from .views import *
admin.autodiscover()


urlpatterns = [
    url(r'^orgs/select/$', ChangeOrg.as_view(), name='change_org'),
    url(r'^rooms/$', RoomsView.as_view(), name='rooms'),
    url(r'^room/add/$', RoomAddView.as_view(), name='add_room'),
    url(r'^room/(?P<room_id>\d+)/$', RoomView.as_view(), name='room'),
    url(r'^room/(?P<room_id>\d+)/post/$', RoomMessageView.as_view(), name='room_post'),
    url(r'^room/(?P<room_id>\d+)/pin/$', RoomPinView.as_view(), name='room_pin'),
    url(r'^room/(?P<room_id>\d+)/edit/$', RoomEditView.as_view(), name='room_edit'),
    url(r'^accounts/', include('django.contrib.auth.urls')),
    url(r'^accounts/register/', RegisterView.as_view(), name='register'),
    url(r'^admin/', include(admin.site.urls)),
    url(r'^$', RedirectView.as_view(url=reverse_lazy('login'))),
] + staticfiles_urlpatterns()
