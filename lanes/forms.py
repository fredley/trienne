import logging
import re

from django import forms
from django.forms import ModelForm
from django.contrib.auth.forms import UserCreationForm
from django.forms.widgets import RadioSelect, HiddenInput
from ajax_select import make_ajax_field

from .models import Organisation, OrgMembership, Room, User, Bot

logger = logging.getLogger('django')
username_test = re.compile("^([a-z0-9]+)+$")


def validate_username(value):
  if User.objects.filter(username=value).count() > 0:
    raise forms.ValidationError('That username is already in use')
  if not username_test.match(value):
    raise forms.ValidationError('')
  return value


class OrgForm(ModelForm):

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

  class Meta:
    model = Room
    fields = ['name', 'topic', 'privacy', 'owners']
    widgets = {
        'privacy': RadioSelect(attrs={'class': 'radio-2'}),
    }

  owners = make_ajax_field(Room, 'owners', 'users', required=True, help_text="")


class BotCreateForm(ModelForm):

  username = forms.CharField(label='Name')

  class Meta:
    model = Bot
    fields = ['username', 'notify_url', 'scope']
    widgets = {
        'scope': RadioSelect(attrs={'class': 'radio-2'}),
    }
    help_texts = {
        'username': 'Enter a valid username, numbers and letters only.',
    }
    error_messages = {
        'username': {
            'invalid': "",
            'max_length': "This name is too long.",
        },
    }

  def clean_username(self):
    return validate_username(self.cleaned_data.get("username").lower())


class BotUpdateForm(ModelForm):

  class Meta:
    model = Bot
    fields = ['scope']
    widgets = {
        'scope': RadioSelect(attrs={'class': 'radio-2'}),
    }


class RegisterForm(UserCreationForm):
  secret_key = forms.CharField(label='Secret Key', widget=forms.PasswordInput())

  class Meta(UserCreationForm.Meta):
    model = User
    fields = UserCreationForm.Meta.fields + ('secret_key', 'email')
    help_texts = {
        'username': 'Enter a valid username, numbers and letters only.',
    }
    error_messages = {
        'username': {
            'invalid': "",
            'max_length': "This username is too long.",
        },
    }

  def clean_username(self):
    return validate_username(self.cleaned_data.get("username").lower())

  def clean_email(self):
    value = self.cleaned_data.get("email").lower()
    if User.objects.filter(email=value).count() > 0:
      raise forms.ValidationError('That address is already in use')
    return value

  def clean_secret_key(self):
    if self.cleaned_data.get("secret_key") != "goldfish":
      raise forms.ValidationError("Incorrect Secret Key")
    return ""

  def save(self, *args, **kwargs):
    logger.debug("Saving")
    user = super(RegisterForm, self).save(*args, **kwargs)
    domain = user.email.split('@')[1]
    orgs = Organisation.objects.filter(domain=domain)
    if orgs.count() == 1:
      OrgMembership(user=user, organisation=orgs[0]).save()
    return user
