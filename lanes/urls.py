# -*- coding: utf-8 -*-
from django.conf.urls import url, include
from django.conf.urls.static import static
from django.core.urlresolvers import reverse_lazy
from django.views.generic import RedirectView
from django.contrib import admin

from ajax_select import urls as ajax_select_urls

from .views import *
admin.autodiscover()


urlpatterns = [
    url(r'^ajax/orgs/all/$', OrgJsonView.as_view(data='all'), name='ajax_orgs_all'),
    url(r'^ajax/orgs/mine/$', OrgJsonView.as_view(data='mine'), name='ajax_orgs_mine'),
    url(r'^ajax/orgs/watched/$', OrgJsonView.as_view(data='watched'), name='ajax_orgs_watching'),
    url(r'^ajax/orgs/search/$', OrgJsonView.as_view(data='search'), name='ajax_orgs_search'),
    url(r'^ajax/select/', include(ajax_select_urls)),
    url(r'^orgs/$', OrgsView.as_view(), name='orgs'),
    url(r'^orgs/new/$', OrgCreateView.as_view(), name='create_org'),

    url(r'^org/(?P<slug>[\w-]+)/$', OrgView.as_view(), name='org'),
    url(r'^org/(?P<slug>[\w-]+)/manage/$', OrgManagementView.as_view(), name='manage_org'),
    url(r'^org/(?P<slug>[\w-]+)/add_room/$', RoomAddView.as_view(), name='add_room'),
    url(r'^org/(?P<slug>[\w-]+)/join/$', OrgJoinView.as_view()),
    url(r'^org/(?P<slug>[\w-]+)/apply/$', OrgApplyView.as_view()),
    url(r'^org/(?P<slug>[\w-]+)/follow/$', OrgWatchView.as_view()),

    url(r'^room/(?P<room_id>\d+)/$', RoomView.as_view(), name='room'),
    url(r'^room/(?P<room_id>\d+)/post/$', RoomMessageView.as_view(), name='room_post'),
    url(r'^room/(?P<room_id>\d+)/pin/$', RoomPinView.as_view(), name='room_pin'),
    url(r'^room/(?P<room_id>\d+)/edit/$', RoomEditView.as_view(), name='room_edit'),
    url(r'^room/(?P<room_id>\d+)/prefs/$', RoomPrefsView.as_view(), name='room_prefs'),

    url(r'^post/(?P<post_id>\d+)/edit/$', PostEditView.as_view(), name='post_edit'),
    url(r'^post/(?P<post_id>\d+)/vote/$', PostVoteView.as_view(), name='post_vote'),
    url(r'^post/(?P<post_id>\d+)/history/$', PostHistoryView.as_view()),

    url(r'^users/(?P<user_id>\d+)/$', UserProfileView.as_view(), name='user_profile'),
    url(r'^users/', include('django.contrib.auth.urls')),
    url(r'^users/register/(?P<token>\w+)/', RegisterView.as_view(), name='invitation'),
    url(r'^users/register/', RegisterView.as_view(), name='register'),
    url(r'^users/manage/', UserManagementView.as_view(), name='manage_users'),
    url(r'^admin/', include(admin.site.urls)),
    url(r'^$', RedirectView.as_view(url=reverse_lazy('orgs'))),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
