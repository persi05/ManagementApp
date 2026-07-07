from django.urls import path

from . import views

urlpatterns = [
    path('time-entries/', views.time_entries, name='time_entries'),
    path('time-entries/<int:entry_id>/edit/', views.edit_time_entry, name='edit_time_entry'),
    path('timer/start/', views.start_timer, name='start_timer'),
    path('timer/pause/', views.pause_timer, name='pause_timer'),
    path('timer/resume/', views.resume_timer, name='resume_timer'),
    path('timer/stop/', views.stop_timer, name='stop_timer'),
]
