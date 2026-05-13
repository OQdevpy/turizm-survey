import os

from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.urls import path, include
from django.views.generic import TemplateView, RedirectView


def healthcheck(request):
    """Render keep-alive / monitoring uchun. Tezkor 200 OK qaytaradi."""
    return JsonResponse({'status': 'ok', 'service': 'turizm-survey'})


admin_url = os.getenv('ADMIN_URL', 'admin/')
if not admin_url.endswith('/'):
    admin_url += '/'

urlpatterns = [
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
