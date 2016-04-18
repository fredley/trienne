from django import template
from django.utils.html import conditional_escape

register = template.Library()

@register.filter
def multiline(text):
  return text.replace("\n","\\n")