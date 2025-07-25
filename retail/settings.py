"""
Django settings for retail project.

Generated by 'django-admin startproject' using Django 5.0.7.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.0/ref/settings/
"""

import os
from pathlib import Path

import environ
import sentry_sdk
import urllib

from sentry_sdk.integrations.django import DjangoIntegration


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# environ settings
ENV_PATH = os.path.join(BASE_DIR, ".env")

if os.path.exists(ENV_PATH):
    environ.Env.read_env(env_file=ENV_PATH)

env = environ.Env()


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env.str("SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env.bool("DEBUG", default=False)

SERVICE_HOST = env.str("SERVICE_HOST", default="localhost")

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

CSRF_TRUSTED_ORIGINS = [f"https://*.{SERVICE_HOST}"]

SENTRY_DSN = env.str("SENTRY_DSN", default="")

sentry_sdk.init(
    dsn=SENTRY_DSN,
    integrations=[DjangoIntegration()],
)

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
}

# Application definition

INSTALLED_APPS = [
    "retail.admin",
    "mozilla_django_oidc",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "weni.eda.django.eda_app",
    "corsheaders",
    "retail.projects",
    "retail.features",
    "retail.integrations",
    "retail.healthcheck",
    "retail.internal",
    "rest_framework",
    "drf_yasg",
    "retail.vtex",
    "retail.templates",
    "retail.agents",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "retail.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "retail.wsgi.application"


# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases

DATABASES = dict(default=env.db(var="DATABASE_URL"))


# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

LANGUAGE_CODE = env.str("LANGUAGE_CODE", default="en-us")

TIME_ZONE = env.str("TIME_ZONE", default="America/Maceio")

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/

STATIC_URL = "static/"
STATIC_ROOT = "static"

# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Event Driven Architecture configurations

USE_EDA = env.bool("USE_EDA", default=False)

ACTION_TYPES = env.json("ACTION_TYPES", default={})

CORS_ALLOW_ALL_ORIGINS = env.str("CORS_ALLOW_ALL_ORIGINS", default=True)

if USE_EDA:
    EDA_CONSUMERS_HANDLE = "retail.event_driven.handle.handle_consumers"
    EDA_BROKER_HOST = env("EDA_BROKER_HOST", default="localhost")
    EDA_VIRTUAL_HOST = env("EDA_VIRTUAL_HOST", default="/")
    EDA_BROKER_PORT = env.int("EDA_BROKER_PORT", default=5672)
    EDA_BROKER_USER = env("EDA_BROKER_USER", default="guest")
    EDA_BROKER_PASSWORD = env("EDA_BROKER_PASSWORD", default="guest")

USE_OIDC = env.bool("USE_OIDC")

if USE_OIDC:
    REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"].append(
        "mozilla_django_oidc.contrib.drf.OIDCAuthentication"
    )

    OIDC_RP_CLIENT_ID = env.str("OIDC_RP_CLIENT_ID")
    OIDC_RP_CLIENT_SECRET = env.str("OIDC_RP_CLIENT_SECRET")
    OIDC_OP_AUTHORIZATION_ENDPOINT = env.str("OIDC_OP_AUTHORIZATION_ENDPOINT")
    OIDC_OP_TOKEN_ENDPOINT = env.str("OIDC_OP_TOKEN_ENDPOINT")
    OIDC_OP_USER_ENDPOINT = env.str("OIDC_OP_USER_ENDPOINT")
    OIDC_OP_JWKS_ENDPOINT = env.str("OIDC_OP_JWKS_ENDPOINT")
    OIDC_RP_SIGN_ALGO = env.str("OIDC_RP_SIGN_ALGO", default="RS256")
    OIDC_DRF_AUTH_BACKEND = "retail.internal.backends.WeniOIDCAuthenticationBackend"
    OIDC_RP_SCOPES = env.str("OIDC_RP_SCOPES", default="openid email")

INTEGRATIONS_REST_ENDPOINT = env.str("INTEGRATIONS_REST_ENDPOINT")

FLOWS_REST_ENDPOINT = env.str("FLOWS_REST_ENDPOINT")

EMAILS_CAN_TESTING = env.str("EMAILS_CAN_TESTING", "").split(",")

# Redis
REDIS_URL = env.str("REDIS_URL", default="redis://localhost:6379")


# Celery
CELERY_BROKER_URL = env.str("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = None
CELERY_TASK_IGNORE_RESULT = True
CELERY_ACCEPT_CONTENT = ["application/json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE


# Cache
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
}

OIDC_CACHE_TOKEN = env.bool(
    "OIDC_CACHE_TOKEN", default=False
)  # Enable/disable user token caching (default: False).
OIDC_CACHE_TTL = env.int(
    "OIDC_CACHE_TTL", default=600
)  # Time-to-live for cached user tokens (default: 600 seconds).

VTEX_IO_OIDC_RP_CLIENT_SECRET = env.str("VTEX_IO_OIDC_RP_CLIENT_SECRET", "")
VTEX_IO_OIDC_RP_CLIENT_ID = env.str("VTEX_IO_OIDC_RP_CLIENT_ID", "")

# Abandoned Cart timeout in minutes
ABANDONED_CART_COUNTDOWN = env.int("ABANDONED_CART_COUNTDOWN", default=25)

# Endpoint for Nexus service
NEXUS_REST_ENDPOINT = env.str("NEXUS_REST_ENDPOINT", default="")

# Endpoint for code actions service
CODE_ACTIONS_REST_ENDPOINT = env.str("CODE_ACTIONS_REST_ENDPOINT", "")

# VTEX IO workspace configuration
VTEX_IO_WORKSPACE = env.str("VTEX_IO_WORKSPACE", default="")

# Lambda no token validation
LAMBDA_ALLOWED_ROLES = env.list("LAMBDA_ALLOWED_ROLES", default=[])

USE_LAMBDA = env.bool("USE_LAMBDA", default=False)
USE_S3 = env.bool("USE_S3", default=False)

DOMAIN = env.str("DOMAIN", default="http://localhost:8000")

if USE_LAMBDA:
    LAMBDA_ROLE_ARN = env.str("LAMBDA_ROLE_ARN")
    LAMBDA_RUNTIME = env.str("LAMBDA_RUNTIME")
    LAMBDA_HANDLER = env.str("LAMBDA_HANDLER")
    LAMBDA_REGION = env.str("LAMBDA_REGION")
    LAMBDA_TIMEOUT = env.int("LAMBDA_TIMEOUT", default=60)
    LAMBDA_CODE_GENERATOR = env.str("LAMBDA_CODE_GENERATOR")
    LAMBDA_CODE_GENERATOR_REGION = env.str("LAMBDA_CODE_GENERATOR_REGION")
    LAMBDA_LOG_GROUP = env.str("LAMBDA_LOG_GROUP")

if USE_S3:
    AWS_STORAGE_BUCKET_NAME = env.str("AWS_STORAGE_BUCKET_NAME")

USE_META = env.bool("USE_LAMBDA", default=False)

if USE_META:
    META_SYSTEM_USER_ACCESS_TOKEN = env.str("META_SYSTEM_USER_ACCESS_TOKEN")
    META_VERSION = env.str("META_VERSION", default="v20.0")
    META_API_URL = urllib.parse.urljoin(
        env.str("WHATSAPP_API_URL", default="https://graph.facebook.com/"), META_VERSION
    )

ORDER_STATUS_AGENT_UUID = env.str("ORDER_STATUS_AGENT_UUID", default="")

# Path to the JWT public key
JWT_PUBLIC_KEY_PATH = BASE_DIR / "retail" / "jwt_keys" / "public_key.pem"

# The public key is loaded a single time at application startup.
try:
    with open(JWT_PUBLIC_KEY_PATH, "rb") as f:
        JWT_PUBLIC_KEY = f.read()
except FileNotFoundError:
    JWT_PUBLIC_KEY = None
