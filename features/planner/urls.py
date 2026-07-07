from django.urls import path

from . import views

urlpatterns = [
    path('calendar/', views.calendar_view, name='calendar'),
    path('calendar/leave/<int:leave_id>/status/', views.update_leave_status, name='update_leave_status'),
    path('calendar/leave/<int:leave_id>/read/', views.mark_leave_as_read, name='mark_leave_as_read'),
]
