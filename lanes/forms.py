from django.forms import ModelForm
from django.forms.widgets import RadioSelect, HiddenInput
from ajax_select import make_ajax_field

from .models import Organisation, Room


class OrgForm(ModelForm):

  required_css_class = "required"

  class Meta:
    model = Organisation
    fields = ['name', 'privacy', 'visibility', 'admins', 'domain']
    widgets = {
        'privacy': RadioSelect(attrs={'class': 'radio-4'}),
        'visibility': RadioSelect(),
        'domain': HiddenInput()
    }

  admins = make_ajax_field(Organisation, 'admins', 'users', required=True, help_text="")


class OrgEditForm(ModelForm):
  class Meta:
    model = Organisation
    fields = ['admins']

  admins = make_ajax_field(Organisation, 'admins', 'users', required=True, help_text="")


class RoomForm(ModelForm):

  required_css_class = "required"

  class Meta:
    model = Room
    fields = ['name', 'topic', 'privacy', 'owners']
    widgets = {
        'privacy': RadioSelect(),
    }

  owners = make_ajax_field(Room, 'owners', 'users', required=True, help_text="")
