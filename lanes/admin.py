from django.contrib import admin
from .models import *

admin.site.register(User)
admin.site.register(Organisation)
admin.site.register(OrgMembership)
admin.site.register(Room)
admin.site.register(RoomPrefs)
admin.site.register(Post)
admin.site.register(PostContent)
