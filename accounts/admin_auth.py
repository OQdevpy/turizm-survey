"""Admin uchun reCAPTCHA + TOTP (2FA) login oqimi.

Oqim:
  1) /admin/login/        — username + parol + reCAPTCHA   (AdminLoginForm)
  2) /admin/2fa/verify/   — TOTP kodini kiritish           (AdminOTPForm)
  3) /admin/2fa/setup/    — QR + secret + birinchi kod    (yangi yoki reset bo'lgan device)

Session kalitlari:
  - admin_2fa_pending_user_id  — login muvaffaqiyatli, lekin TOTP qolgan
  - admin_2fa_backend          — auth backend dotted path (auth_login() uchun)
"""
from __future__ import annotations

import base64
import io
import logging

import pyotp
import qrcode
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from .forms import AdminLoginForm, AdminOTPForm
from .models import AdminTOTPDevice

logger = logging.getLogger(__name__)

PENDING_USER_KEY = 'admin_2fa_pending_user_id'
PENDING_BACKEND_KEY = 'admin_2fa_backend'


def _issuer() -> str:
    return getattr(settings, 'ADMIN_2FA_ISSUER', "Turizm so'rovnoma")


def _admin_index_url() -> str:
    try:
        return reverse('admin:index')
    except Exception:
        return '/admin/'


def _get_pending_user(request) -> User | None:
    uid = request.session.get(PENDING_USER_KEY)
    if not uid:
        return None
    return User.objects.filter(pk=uid, is_active=True).first()


def _clear_pending(request) -> None:
    request.session.pop(PENDING_USER_KEY, None)
    request.session.pop(PENDING_BACKEND_KEY, None)


def _make_qr_data_url(uri: str) -> str:
    """QR code ni data:image/png;base64 URL sifatida qaytaradi (fayl saqlamasdan)."""
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode('ascii')
    return f'data:image/png;base64,{b64}'


@never_cache
@csrf_protect
@require_http_methods(['GET', 'POST'])
def admin_login_view(request):
    """1-bosqich: username + parol + reCAPTCHA."""
    # Allaqachon kirgan bo'lsa to'g'ri admin'ga
    if request.user.is_authenticated and request.user.is_staff:
        return redirect(_admin_index_url())

    if request.method == 'POST':
        form = AdminLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            if not user.is_staff:
                form.add_error(None, "Sizda admin paneliga kirish huquqi yo'q.")
            else:
                # Login qilinmagan holatda backend yo'lini saqlab qo'yamiz
                request.session[PENDING_USER_KEY] = user.pk
                request.session[PENDING_BACKEND_KEY] = getattr(user, 'backend', 'django.contrib.auth.backends.ModelBackend')
                return redirect('admin_2fa_verify')
    else:
        form = AdminLoginForm(request)

    return render(request, 'admin/login_2fa.html', {
        'form': form,
        'next': request.GET.get('next', ''),
        'site_header': "Turizm so'rovnoma — Boshqaruv paneli",
        'site_title': "Boshqaruv",
    })


@never_cache
@csrf_protect
@require_http_methods(['GET', 'POST'])
def admin_2fa_verify(request):
    """2-bosqich: TOTP kodini tekshirish. Device yo'q yoki tasdiqlanmagan → setup."""
    user = _get_pending_user(request)
    if not user:
        return redirect('admin_login')

    device = AdminTOTPDevice.objects.filter(user=user, is_active=True).first()
    if device is None or not device.is_verified:
        return redirect('admin_2fa_setup')

    if request.method == 'POST':
        form = AdminOTPForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['otp_code']
            totp = pyotp.TOTP(device.secret)
            if totp.verify(code, valid_window=1):
                backend = request.session.get(PENDING_BACKEND_KEY) or 'django.contrib.auth.backends.ModelBackend'
                _clear_pending(request)
                auth_login(request, user, backend=backend)
                device.last_used_at = timezone.now()
                device.save(update_fields=['last_used_at'])
                next_url = request.POST.get('next') or request.GET.get('next') or _admin_index_url()
                return HttpResponseRedirect(next_url)
            form.add_error('otp_code', "Kod noto'g'ri yoki muddati o'tgan. Yangi kodni kuting.")
    else:
        form = AdminOTPForm()

    return render(request, 'admin/2fa_verify.html', {
        'form': form,
        'pending_user': user,
        'next': request.GET.get('next', ''),
    })


@never_cache
@csrf_protect
@require_http_methods(['GET', 'POST'])
def admin_2fa_setup(request):
    """3-bosqich: QR + secret ko'rsatish, birinchi kodni tasdiqlash → login."""
    user = _get_pending_user(request)
    if not user:
        return redirect('admin_login')

    device, created = AdminTOTPDevice.objects.get_or_create(
        user=user,
        defaults={'secret': pyotp.random_base32(), 'is_active': True, 'is_verified': False},
    )
    # Reset variantida (is_verified=False, lekin secret eski) — admin Reset action chaqirgan bo'lsa
    if not device.is_verified and request.GET.get('regenerate') == '1':
        device.secret = pyotp.random_base32()
        device.save(update_fields=['secret'])

    totp = pyotp.TOTP(device.secret)
    provisioning_uri = totp.provisioning_uri(name=user.get_username(), issuer_name=_issuer())
    qr_data_url = _make_qr_data_url(provisioning_uri)

    form = AdminOTPForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        code = form.cleaned_data['otp_code']
        if totp.verify(code, valid_window=1):
            device.is_verified = True
            device.last_used_at = timezone.now()
            device.save(update_fields=['is_verified', 'last_used_at'])
            backend = request.session.get(PENDING_BACKEND_KEY) or 'django.contrib.auth.backends.ModelBackend'
            _clear_pending(request)
            auth_login(request, user, backend=backend)
            messages.success(request, "2FA muvaffaqiyatli sozlandi. Endi har safar kirishda kod kerak bo'ladi.")
            return redirect(_admin_index_url())
        form.add_error('otp_code', "Kod noto'g'ri. Authenticator ilovasidagi kodni qayta kiriting.")

    return render(request, 'admin/2fa_setup.html', {
        'form': form,
        'pending_user': user,
        'qr_data_url': qr_data_url,
        'secret': device.secret,
        'issuer': _issuer(),
    })


@never_cache
def admin_2fa_cancel(request):
    """Login oqimini bekor qilib login sahifasiga qaytarish."""
    _clear_pending(request)
    return redirect('admin_login')
