from django.urls import path

from . import views

urlpatterns = [path("<int:job_id>/", views.detail, name="job_detail")]
