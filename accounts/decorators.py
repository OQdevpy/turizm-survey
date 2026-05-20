from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def staff_required(view_func):
    """Faqat is_staff yoki is_superuser kira oladi."""
    @login_required(login_url='accounts:login')
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not (request.user.is_staff or request.user.is_superuser):
            raise PermissionDenied("Sizda kirish huquqi yo'q.")
        return view_func(request, *args, **kwargs)
    return _wrapped


def superuser_required(view_func):
    """Faqat superuser kira oladi."""
    @login_required(login_url='accounts:login')
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied("Faqat superuser uchun.")
        return view_func(request, *args, **kwargs)
    return _wrapped


def has_admin_view_access(user):
    """Foydalanuvchi admin-darajadagi panellarni ko'ra oladimi.

    True qaytaradi:
      - Superuser har doim
      - StaffProfile.can_enter_surveys=False bo'lgan xodim (kuzatuvchi)
    """
    if not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser:
        return True
    if not user.is_staff:
        return False
    try:
        return not user.staff_profile.can_enter_surveys
    except Exception:
        return False


def admin_view_required(view_func):
    """Faqat superuser yoki cheklangan kuzatuvchi (can_enter_surveys=False) kira oladi."""
    @login_required(login_url='accounts:login')
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not has_admin_view_access(request.user):
            raise PermissionDenied("Sizda kuzatuv panellarini ko'rish huquqi yo'q.")
        return view_func(request, *args, **kwargs)
    return _wrapped


def survey_entry_required(view_func):
    """Faqat so'rovnoma kiritish huquqi bor xodimlar kira oladi.

    StaffProfile.can_enter_surveys False bo'lsa, PermissionDenied (403).
    Superuser doim kira oladi (admin override).
    """
    @login_required(login_url='accounts:login')
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        user = request.user
        if not (user.is_staff or user.is_superuser):
            raise PermissionDenied("Sizda kirish huquqi yo'q.")
        # Superuser doim kira oladi
        if user.is_superuser:
            return view_func(request, *args, **kwargs)
        # StaffProfile bo'lsa va can_enter_surveys=False bo'lsa, taqiqlanadi
        try:
            if not user.staff_profile.can_enter_surveys:
                raise PermissionDenied(
                    "Sizning hisobingiz uchun so'rovnoma kiritish "
                    "huquqi yopilgan. Faqat monitoringga kira olasiz."
                )
        except Exception as e:
            if isinstance(e, PermissionDenied):
                raise
            # StaffProfile yo'q bo'lsa — default ruxsat
            pass
        return view_func(request, *args, **kwargs)
    return _wrapped
