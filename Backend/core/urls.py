from django.urls import path
from .views import signup, login, verify_email

urlpatterns = [
    path('signup/', signup),
    path('login/', login),
    path('verify/<uuid:token>/', verify_email),
]