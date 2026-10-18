from django.urls import path

from . import views

urlpatterns = [
    path("<int:resume_id>/", views.detail, name="resume_detail"),
]
