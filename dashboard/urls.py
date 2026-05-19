from django.urls import path

from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.index, name='index'),
    path('reports/', views.admin_reports, name='admin_reports'),
    path('monitoring/', views.monitoring, name='monitoring'),
    path('monitoring/staff/<int:staff_id>/', views.monitoring_staff_detail, name='monitoring_staff'),
    path('export/', views.export_excel, name='export'),
]
