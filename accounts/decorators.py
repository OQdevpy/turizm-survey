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
