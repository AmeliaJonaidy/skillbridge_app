from django.urls import path

from . import views

urlpatterns = [
    path("<int:resume_id>/", views.detail, name="resume_detail"),
    path("<int:resume_id>/set-main/", views.set_main, name="set_main_resume"),
]
