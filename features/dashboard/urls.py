from django.urls import path
from django.views.generic import RedirectView

from . import views

urlpatterns = [
    path('', views.landing, name='landing'),
    path('app/', RedirectView.as_view(pattern_name='dashboard', permanent=False), name='app_root'),
    path('app/dashboard/', views.dashboard, name='dashboard'),
    path('dashboard/', RedirectView.as_view(pattern_name='dashboard', permanent=False), name='dashboard_legacy'),
]
