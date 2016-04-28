from ajax_select import register, LookupChannel
from .models import User

@register('admins')
class AdminLookup(LookupChannel):

    model = User

    def get_query(self, q, request):
        return User.objects.filter(username__icontains=q)

    def get_result(self, obj):
        return obj.username

    def format_match(self, obj):
        return "%s" % (obj.username)

    def format_item_display(self, item):
        return u"<span class='user'>%s</span>" % item.username