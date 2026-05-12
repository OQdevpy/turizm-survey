from django.urls import path

from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.staff_login, name='login'),
    path('logout/', views.staff_logout, name='logout'),
]
