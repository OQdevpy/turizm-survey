from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django_recaptcha.fields import ReCaptchaField


class StaffLoginForm(AuthenticationForm):
    """Oddiy xodim loginiga reCAPTCHA majburiy emas (faqat admin uchun)."""
    username = forms.CharField(
        label="Login",
        widget=forms.TextInput(attrs={
            'class': 'field-input',
            'placeholder': "Login (foydalanuvchi nomi)",
            'autofocus': True,
        }),
    )
    password = forms.CharField(
        label="Parol",
        widget=forms.PasswordInput(attrs={
            'class': 'field-input',
            'placeholder': '••••••••',
        }),
    )

    error_messages = {
        'invalid_login': "Login yoki parol noto'g'ri.",
        'inactive': "Bu hisob faol emas.",
    }


class AdminLoginForm(AuthenticationForm):
    """Django admin login uchun reCAPTCHA bilan."""
    captcha = ReCaptchaField(label="Men robot emasman")
