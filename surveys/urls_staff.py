from django.urls import path

from . import views


def staff_submit_inbound(request):
    return views.submit_staff(request, 'inbound')


def staff_submit_outbound(request):
    return views.submit_staff(request, 'outbound')


app_name = 'staff_surveys'

urlpatterns = [
    path('inbound/', views.staff_inbound, name='inbound'),
    path('inbound/submit/', staff_submit_inbound, name='inbound_submit'),
    path('outbound/', views.staff_outbound, name='outbound'),
    path('outbound/submit/', staff_submit_outbound, name='outbound_submit'),
]
