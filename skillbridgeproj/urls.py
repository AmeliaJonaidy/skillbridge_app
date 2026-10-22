"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from accounts import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', views.logout_view, name='logout'),
    path('inbox/', views.inbox, name='inbox'),
    path('onboarding/', views.onboarding, name='onboarding'),
    path('plans/', views.plans, name='plans'),
    path('plans/checkout/confirm/', views.pro_checkout_confirm, name='pro_checkout_confirm'),
    path('plans/checkout/', views.start_pro_checkout, name='start_pro_checkout'),
    path('plans/cancel/confirm/', views.cancel_pro_confirm, name='cancel_pro_confirm'),
    path('plans/cancel/', views.cancel_pro, name='cancel_pro'),
    path('plans/success/', views.pro_payment_success, name='pro_payment_success'),
    path('payments/stripe/webhook/', views.stripe_webhook, name='stripe_webhook'),
    path('', include('candidates.urls')),
    path('recruiter/', include('employers.urls')),
    path('jobs/', include('jobs.urls')),
    path('resumes/', include('resumes.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
