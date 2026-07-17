from django.urls import path

from . import views

urlpatterns = [
    path('employees/', views.employees, name='employees'),
    path('employees/<int:user_id>/', views.employee_detail, name='employee_detail'),
    path('charges/', views.charges, name='charges'),
    path('charges/<int:charge_id>/delete/', views.delete_charge, name='delete_charge'),
]
