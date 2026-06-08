from django.contrib.auth.views import LoginView, LogoutView

class CustomLoginView(LoginView):
    template_name = "login.html"

class CustomLogoutView(LogoutView):
    next_page = "/"   # A dónde redirige después de cerrar sesión