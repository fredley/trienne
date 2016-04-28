from django.contrib import admin

from ajax_select import make_ajax_form
from ajax_select.admin import AjaxSelectAdmin, AjaxSelectAdminTabularInline, AjaxSelectAdminStackedInline

from .models import *

admin.site.register(User)

class OrgAdmin(AjaxSelectAdmin):

    form = make_ajax_form(Organisation, {'admins': 'admins'})

admin.site.register(Organisation, OrgAdmin)
admin.site.register(OrgMembership)
admin.site.register(Room)
admin.site.register(RoomPrefs)
admin.site.register(Post)
admin.site.register(PostContent)
admin.site.register(Invitation)
admin.site.register(Vote)
