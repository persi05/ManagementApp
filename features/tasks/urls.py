from django.urls import path

from . import views

urlpatterns = [
    path('boards/', views.kanban, name='kanban'),
    path('boards/<int:project_id>/', views.kanban, name='kanban_project'),
    path('tasks/<int:task_id>/move/', views.move_task, name='move_task'),
    path('columns/<int:column_id>/delete/', views.delete_column, name='delete_column'),
    path('tasks/<int:task_id>/edit/', views.edit_task, name='edit_task'),
    path('tasks/<int:task_id>/delete/', views.delete_task, name='delete_task'),
    path('worklogs/', views.worklogs, name='worklogs'),
    path('worklogs/<int:worklog_id>/visibility/', views.toggle_worklog_visibility, name='toggle_worklog_visibility'),
]
