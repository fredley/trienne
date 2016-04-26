# -*- coding: utf-8 -*-
import os

from .socket import get_allowed_channels

BASE_DIR = os.path.dirname(os.path.dirname(__file__))

DEBUG = True

ALLOWED_HOSTS = []

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}

ALLOWED_HOSTS = ["localhost"]

AUTH_USER_MODEL = 'lanes.User'

ROOT_URLCONF = 'lanes.urls'
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'rooms'

SECRET_KEY = 'key'

STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "static"),
]

STATIC_URL = '/static/'

SESSION_ENGINE = 'redis_sessions.session'

SESSION_REDIS_PREFIX = 'session'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': ['templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'ws4redis.context_processors.default',
            ],
        },
    },
]

EMAIL_USE_TLS = True
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_HOST_USER = os.environ.get('GMAIL_USER','')
EMAIL_HOST_PASSWORD = os.environ.get('GMAIL_PASSWORD','')
EMAIL_PORT = 587
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

LANGUAGE_CODE = 'en-gb'

TIME_ZONE = 'Europe/London'

USE_I18N = True
USE_L10N = True
USE_TZ = True

INSTALLED_APPS = (
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_gravatar',
    'bootstrapform',
    'ws4redis',
    'lanes',
)

MIDDLEWARE_CLASSES = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
)

WSGI_APPLICATION = 'ws4redis.django_runserver.application'

WEBSOCKET_URL = '/ws/'
WS4REDIS_EXPIRE = 3600
WS4REDIS_HEARTBEAT = '--ah-ah-ah-ah-stayin-alive--'
WS4REDIS_PREFIX = 'lanes'
WS4REDIS_ALLOWED_CHANNELS = get_allowed_channels

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '[%(asctime)s %(module)s] %(levelname)s: %(message)s'
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'null': {
            'level': 'DEBUG',
            'class': 'logging.NullHandler',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
        'django': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
        'django.db.backends': {
            'handlers': ['null'],  # Quiet by default!
            'propagate': False,
            'level': 'DEBUG',
        },
    },
}
