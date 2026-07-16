from django.urls import path

from . import views

urlpatterns = [
    path('boards/', views.kanban, name='kanban'),
    path('boards/<int:project_id>/', views.kanban, name='kanban_project'),
    path('tasks/<int:task_id>/move/', views.move_task, name='move_task'),
    path('tasks/<int:task_id>/card/', views.update_task_card, name='update_task_card'),
    path('tasks/<int:task_id>/notes/', views.add_task_note, name='add_task_note'),
    path('tasks/<int:task_id>/attachments/', views.add_task_attachment, name='add_task_attachment'),
    path('tasks/<int:task_id>/documents/', views.link_task_document, name='link_task_document'),
    path('columns/<int:column_id>/edit/', views.update_column, name='update_column'),
    path('columns/<int:column_id>/delete/', views.delete_column, name='delete_column'),
    path('tasks/<int:task_id>/edit/', views.edit_task, name='edit_task'),
    path('tasks/<int:task_id>/delete/', views.delete_task, name='delete_task'),
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/<int:notification_id>/read/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/read-all/', views.mark_all_notifications_read, name='mark_all_notifications_read'),
    path('worklogs/', views.worklogs, name='worklogs'),
    path('worklogs/<int:worklog_id>/edit/', views.edit_worklog, name='edit_worklog'),
    path('worklogs/<int:worklog_id>/visibility/', views.toggle_worklog_visibility, name='toggle_worklog_visibility'),
]
