# -*- coding: utf-8 -*-
from django.conf.urls import url, include
from django.conf.urls.static import static
from django.contrib import admin

from ajax_select import urls as ajax_select_urls
import django_pydenticon.urls

from .views import *
admin.autodiscover()


urlpatterns = [
    url(r'^ajax/users/c/$', UserJsonView.as_view(data='org'), name='ajax_users_org'),
    url(r'^ajax/c/all/$', OrgJsonView.as_view(data='all'), name='ajax_orgs_all'),
    url(r'^ajax/c/mine/$', OrgJsonView.as_view(data='mine'), name='ajax_orgs_mine'),
    url(r'^ajax/c/followed/$', OrgJsonView.as_view(data='followed'), name='ajax_orgs_watching'),
    url(r'^ajax/c/search/$', OrgJsonView.as_view(data='search'), name='ajax_orgs_search'),
    url(r'^ajax/select/', include(ajax_select_urls)),
    url(r'^create/$', OrgCreateView.as_view(), name='create_org'),

    url(r'^c/(?P<slug>[\w-]+)/$', OrgView.as_view(), name='org'),
    url(r'^c/(?P<slug>[\w-]+)/manage/$', OrgManagementView.as_view(), name='manage_org'),
    url(r'^c/(?P<slug>[\w-]+)/manage/approval/$', OrgApprovalView.as_view()),
    url(r'^c/(?P<slug>[\w-]+)/add_room/$', RoomAddView.as_view(), name='add_room'),
    url(r'^c/(?P<slug>[\w-]+)/join/$', OrgJoinView.as_view()),
    url(r'^c/(?P<slug>[\w-]+)/apply/$', OrgApplyView.as_view()),
    url(r'^c/(?P<slug>[\w-]+)/follow/$', OrgWatchView.as_view()),
    url(r'^c/(?P<slug>[\w-]+)/status/$', OrgStatusView.as_view(), name='org_status'),
    url(r'^c/(?P<slug>[\w-]+)/invite/$', OrgInviteView.as_view(), name='org_invite'),
    url(r'^c/(?P<slug>[\w-]+)/banned/$', BannedView.as_view(), name='banned'),
    url(r'^c/(?P<slug>[\w-]+)/dm/(?P<username>[\w-]+)/$', DMView.as_view(), name='dm'),

    url(r'^c/(?P<slug>[\w-]+)/bot/create/$', BotCreateView.as_view(), name='bot_create'),
    url(r'^c/(?P<slug>[\w-]+)/bot/(?P<username>[\w-]+)/$', BotUpdateView.as_view(), name='bot'),
    url(r'^c/(?P<slug>[\w-]+)/bot/(?P<username>[\w-]+)/create_token/$', BotTokenCreateView.as_view(), name='bot_token_create'),
    url(r'^c/(?P<slug>[\w-]+)/bot/(?P<username>[\w-]+)/delete/$', BotDeleteView.as_view(), name='bot_delete'),

    url(r'^room/(?P<room_id>\d+)/$', RoomView.as_view(), name='room'),
    url(r'^room/(?P<room_id>\d+)/post/$', RoomMessageView.as_view(), name='room_post'),
    url(r'^room/(?P<room_id>\d+)/pin/$', RoomPinView.as_view(), name='room_pin'),
    url(r'^room/(?P<room_id>\d+)/edit/$', RoomEditView.as_view(), name='room_edit'),
    url(r'^room/(?P<room_id>\d+)/prefs/$', RoomPrefsView.as_view(), name='room_prefs'),
    url(r'^room/(?P<room_id>\d+)/add_member/$', RoomMemberView.as_view(), name='room_member'),
    url(r'^room/(?P<room_id>\d+)/bot/(?P<username>[\w-]+)/enable/$', BotEnableView.as_view(), name='bot_enable'),

    url(r'^post/(?P<post_id>\d+)/edit/$', PostEditView.as_view(), name='post_edit'),
    url(r'^post/(?P<post_id>\d+)/flag/$', PostFlagView.as_view(), name='post_flag'),
    url(r'^post/(?P<post_id>\d+)/vote/$', PostVoteView.as_view(), name='post_vote'),
    url(r'^post/(?P<post_id>\d+)/history/$', PostHistoryView.as_view(), name='post_history'),

    url(r'^users/(?P<user_id>\d+)/$', UserProfileView.as_view(), name='user_profile'),
    url(r'^users/(?P<user_id>\d+)/ban/$', UserBanView.as_view(), name='user_ban'),
    url(r'^users/(?P<user_id>\d+)/unban/$', UserUnbanView.as_view(), name='user_unban'),
    url(r'^users/', include('django.contrib.auth.urls')),
    url(r'^users/register/(?P<token>\w+)/', RegisterView.as_view(), name='invitation'),
    url(r'^users/register/$', RegisterView.as_view(), name='register'),
    url(r'^users/recover/$', PasswordRecoveryView.as_view(), name='forgotten_password'),
    url(r'^users/reset/(?P<token>\w+)/$', PasswordResetView.as_view(), name='reset_password'),

    url(r'^$', LandingView.as_view(), name='orgs'),
    url(r'^request_invitation/$', InvitationRequestView.as_view(), name='invitation_request'),

    url(r'^identicon/', include(django_pydenticon.urls.get_patterns())),

    url(r'^admin/', include(admin.site.urls), name='home'),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

handler400 = Error500.as_view()
handler403 = Error404.as_view()
handler404 = Error404.as_view()
handler500 = Error500.as_view()
