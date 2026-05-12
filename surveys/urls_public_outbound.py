from django.urls import path

from . import views


def submit_outbound(request):
    return views.submit_public(request, 'outbound')


urlpatterns = [
    path('', views.public_outbound, name='start'),
    path('submit/', submit_outbound, name='submit'),
    path('success/', views.success_page, name='success'),
]
