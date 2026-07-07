from django.urls import path

from . import views

urlpatterns = [
    path('reports/', views.reports, name='reports'),
    path('reports/export.csv', views.export_csv, name='export_csv'),
    path('reports/export.pdf', views.export_pdf, name='export_pdf'),
]
