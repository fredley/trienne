from django.forms import ModelForm

from ajax_select import make_ajax_field

from .models import Organisation, Room


class OrgForm(ModelForm):

  required_css_class = "required"

  class Meta:
    model = Organisation
    fields = ['name', 'visibility', 'privacy', 'admins']

  admins = make_ajax_field(Organisation, 'admins', 'users', required=True, help_text="Select one or more users to be admins.")


class RoomForm(ModelForm):

  required_css_class = "required"

  class Meta:
    model = Room
    fields = ['name', 'topic', 'privacy', 'owners']

  owners = make_ajax_field(Room, 'owners', 'users', required=True, help_text="Select owners of this room.")
