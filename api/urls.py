from django.contrib.auth import views as auth_views
from django.urls import path
from . import views

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(template_name="api/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("users", views.users, name="users"),
    path("api/query/", views.query, name="api-query"),
    path("api/confirm/", views.confirm, name="api-confirm"),
]
