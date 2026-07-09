from django.urls import path

from . import views

urlpatterns = [
    path('documents/', views.documents, name='documents'),
    path('documents/<int:item_id>/download/', views.download_document, name='download_document'),
    path('documents/<int:item_id>/open/', views.open_document, name='open_document'),
]
