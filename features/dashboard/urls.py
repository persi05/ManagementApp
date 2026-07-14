from django.urls import path

from . import views

urlpatterns = [
    path('', views.landing, name='landing'),
    path('app/dashboard/', views.dashboard, name='dashboard'),
]
