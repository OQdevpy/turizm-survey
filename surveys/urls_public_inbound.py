from django.urls import path

from . import views


def submit_inbound(request):
    return views.submit_public(request, 'inbound')


urlpatterns = [
    path('', views.public_inbound, name='start'),
    path('submit/', submit_inbound, name='submit'),
    path('success/', views.success_page, name='success'),
]
