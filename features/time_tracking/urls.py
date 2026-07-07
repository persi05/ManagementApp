from django.urls import path

from . import views

urlpatterns = [
    path('time-entries/', views.time_entries, name='time_entries'),
    path('timer/start/', views.start_timer, name='start_timer'),
    path('timer/pause/', views.pause_timer, name='pause_timer'),
    path('timer/stop/', views.stop_timer, name='stop_timer'),
]
