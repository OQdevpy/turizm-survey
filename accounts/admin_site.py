"""Admin login uchun reCAPTCHA bilan custom site."""
from django.contrib.admin import AdminSite
from django.contrib.auth.forms import AuthenticationForm
from django_recaptcha.fields import ReCaptchaField


class CaptchaAdminAuthForm(AuthenticationForm):
    captcha = ReCaptchaField(label="Men robot emasman")


# Standart admin sayti uchun login formni almashtirish
AdminSite.login_form = CaptchaAdminAuthForm
