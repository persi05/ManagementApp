from django.urls import path

from . import views

urlpatterns = [
    path('employees/', views.employees, name='employees'),
    path('employees/<int:user_id>/', views.employee_detail, name='employee_detail'),
]
