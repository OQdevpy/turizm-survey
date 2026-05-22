from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django_recaptcha.fields import ReCaptchaField


class StaffLoginForm(AuthenticationForm):
    """Xodim login formasi — reCAPTCHA bilan himoyalangan."""
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
    captcha = ReCaptchaField(label="Men robot emasman")

    error_messages = {
        'invalid_login': "Login yoki parol noto'g'ri.",
        'inactive': "Bu hisob faol emas.",
    }


class AdminLoginForm(AuthenticationForm):
    """Django admin login uchun reCAPTCHA bilan (1-bosqich — keyin TOTP)."""
    captcha = ReCaptchaField(label="Men robot emasman")


class AdminOTPForm(forms.Form):
    """Admin 2FA TOTP kodini tekshirish (6 raqam)."""
    otp_code = forms.CharField(
        label="Tasdiqlash kodi",
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={
            'class': 'field-input',
            'placeholder': '123456',
            'autofocus': True,
            'autocomplete': 'one-time-code',
            'inputmode': 'numeric',
            'pattern': '[0-9]{6}',
            'maxlength': '6',
        }),
        error_messages={
            'required': "Kodni kiriting.",
            'min_length': "Kod 6 raqamdan iborat bo'lishi kerak.",
            'max_length': "Kod 6 raqamdan iborat bo'lishi kerak.",
        },
    )

    def clean_otp_code(self):
        code = (self.cleaned_data.get('otp_code') or '').strip()
        if not code.isdigit():
            raise forms.ValidationError("Kod faqat raqamlardan iborat bo'lishi kerak.")
        return code
