from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from . import views

app_name = 'usuarios'

urlpatterns = [
    path('registro/', views.registro, name='registro'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('perfil/', views.perfil, name='perfil'),
    path('perfil/editar/', views.editar_perfil, name='editar_perfil'),
    path('direcciones/', views.lista_direcciones, name='direcciones'),
    path('direcciones/nueva/', views.crear_direccion, name='crear_direccion'),
    path('direcciones/<int:pk>/editar/', views.editar_direccion, name='editar_direccion'),
    path('direcciones/<int:pk>/eliminar/', views.eliminar_direccion, name='eliminar_direccion'),

    # Recuperacion de contrasena (4 vistas estandar de Django)
    path('password-reset/',
         auth_views.PasswordResetView.as_view(
             template_name='usuarios/password_reset.html',
             email_template_name='usuarios/password_reset_email.html',
             subject_template_name='usuarios/password_reset_subject.txt',
             success_url=reverse_lazy('usuarios:password_reset_done'),
         ), name='password_reset'),
    path('password-reset/enviado/',
         auth_views.PasswordResetDoneView.as_view(template_name='usuarios/password_reset_done.html'),
         name='password_reset_done'),
    path('password-reset/confirmar/<uidb64>/<token>/',
         auth_views.PasswordResetConfirmView.as_view(
             template_name='usuarios/password_reset_confirm.html',
             success_url=reverse_lazy('usuarios:password_reset_complete'),
         ), name='password_reset_confirm'),
    path('password-reset/completado/',
         auth_views.PasswordResetCompleteView.as_view(template_name='usuarios/password_reset_complete.html'),
         name='password_reset_complete'),
]
