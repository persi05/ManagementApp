from django.urls import path

from . import views

urlpatterns = [
    path('projects/', views.projects, name='projects'),
    path('projects/<int:project_id>/', views.project_detail, name='project_detail'),
    path('projects/<int:project_id>/default-tasks/', views.set_default_tasks_project, name='set_default_tasks_project'),
    path('project-assignments/<int:assignment_id>/remove/', views.remove_project_assignment, name='remove_project_assignment'),
    path('project-label-rates/<int:rate_id>/remove/', views.remove_project_label_rate, name='remove_project_label_rate'),
]
