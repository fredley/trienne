from ajax_select import register, LookupChannel
from django.core.exceptions import PermissionDenied
from .models import User


@register('users')
class UserLookup(LookupChannel):

    model = User

    def get_query(self, q, request):
        # TODO: only return users that are relevant to request.user...
        return User.objects.filter(username__icontains=q)

    def get_result(self, obj):
        return obj.username

    def format_match(self, obj):
        return "%s" % (obj.username)

    def format_item_display(self, item):
        return u"<span class='user'>%s</span>" % item.username

    def check_auth(self, request):
      if not request.user.is_authenticated():
        raise PermissionDenied
