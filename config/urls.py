import os

from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.urls import path, include
from django.views.generic import TemplateView, RedirectView

from accounts import admin_auth


def healthcheck(request):
    """Render keep-alive / monitoring uchun. Tezkor 200 OK qaytaradi."""
    return JsonResponse({'status': 'ok', 'service': 'turizm-survey'})


admin_url = os.getenv('ADMIN_URL', 'admin/')
if not admin_url.endswith('/'):
    admin_url += '/'

# Admin login + 2FA — admin.site.urls dan OLDIN aniqlanadi.
# Django admin dispatcher /admin/login/ ga ham javob beradi, lekin biz buni
# custom view bilan ushlab olamiz.
urlpatterns = [
    path(admin_url + 'login/', admin_auth.admin_login_view, name='admin_login'),
    path(admin_url + '2fa/verify/', admin_auth.admin_2fa_verify, name='admin_2fa_verify'),
    path(admin_url + '2fa/setup/', admin_auth.admin_2fa_setup, name='admin_2fa_setup'),
    path(admin_url + '2fa/cancel/', admin_auth.admin_2fa_cancel, name='admin_2fa_cancel'),

    path(admin_url, admin.site.urls),

    # Serve favicon from static files to avoid 404 noise
    path('favicon.ico', RedirectView.as_view(url='/static/favicon.ico', permanent=False), name='favicon'),

    # Keep-alive endpoint (UptimeRobot uchun)
    path('healthz/', healthcheck, name='healthcheck'),

    # Landing
    path('', TemplateView.as_view(template_name='home.html'), name='home'),

    # Public surveys (turistlar uchun, login YO'Q)
    path('inbound/', include(('surveys.urls_public_inbound', 'public_inbound'), namespace='public_inbound')),
    path('outbound/', include(('surveys.urls_public_outbound', 'public_outbound'), namespace='public_outbound')),

    # Staff (xodimlar uchun, login KERAK)
    path('staff/', include('accounts.urls')),
    path('staff/', include('dashboard.urls')),
    path('staff/survey/', include('surveys.urls_staff')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
