from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include

# Account pages. Only the ones that work without email: the app can't send email, so the
# "forgot password" pages are left out (they would say an email was sent when none was).
# A forgotten password is reset by the household's admin in /admin/ (see the README).
account_urls = [
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("password_change/", auth_views.PasswordChangeView.as_view(), name="password_change"),
    path("password_change/done/", auth_views.PasswordChangeDoneView.as_view(), name="password_change_done"),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include(account_urls)),
    path("", include("tracker.urls")),
]
