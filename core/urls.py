from django.contrib.auth import views as auth_views
from django.urls import include, path

from . import views

accounts_patterns = ([
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('register/', views.register, name='register'),
    path('settings/', views.account_settings, name='settings'),
], 'accounts')

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('accounts/', include(accounts_patterns)),
    path('app/projects/', views.projects, name='projects'),
    path('app/projects/<int:project_id>/', views.project_detail, name='project_detail'),
    path('app/project-assignments/<int:assignment_id>/remove/', views.remove_project_assignment, name='remove_project_assignment'),
    path('app/employees/', views.employees, name='employees'),
    path('app/employees/<int:user_id>/', views.employee_detail, name='employee_detail'),
    path('app/boards/', views.kanban, name='kanban'),
    path('app/boards/<int:project_id>/', views.kanban, name='kanban_project'),
    path('app/tasks/<int:task_id>/move/', views.move_task, name='move_task'),
    path('app/time-entries/', views.time_entries, name='time_entries'),
    path('app/timer/start/', views.start_timer, name='start_timer'),
    path('app/timer/pause/', views.pause_timer, name='pause_timer'),
    path('app/timer/stop/', views.stop_timer, name='stop_timer'),
    path('app/worklogs/', views.worklogs, name='worklogs'),
    path('app/worklogs/<int:worklog_id>/visibility/', views.toggle_worklog_visibility, name='toggle_worklog_visibility'),
    path('app/reports/', views.reports, name='reports'),
    path('app/reports/export.csv', views.export_csv, name='export_csv'),
    path('app/reports/export.pdf', views.export_pdf, name='export_pdf'),
]
