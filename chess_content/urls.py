from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("login", views.login_view, name="login"),
    path("logout", views.logout_view, name="logout"),
    path("register", views.register, name="register"),
    path("memory_rush", views.memory_rush, name="memory_rush"),
    path('record_success/', views.record_success, name='record_success'),
    path('record_fail/', views.record_fail, name='record_fail'),
    path('get_fen_list/', views.get_fen_list, name='get_fen_list')
]