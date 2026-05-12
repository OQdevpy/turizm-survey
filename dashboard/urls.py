from django.urls import path

from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.index, name='index'),
    path('reports/', views.admin_reports, name='admin_reports'),
    path('export/', views.export_excel, name='export'),
]
