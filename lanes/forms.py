from django.forms import ModelForm

from ajax_select import make_ajax_field

from .models import Organisation

class OrgForm(ModelForm):

  required_css_class = "required"

  class Meta:
    model = Organisation
    fields = ['name', 'visibility', 'privacy', 'admins']

  admins = make_ajax_field(Organisation, 'admins', 'admins', required=True, help_text="Select one or more users to be admins.")