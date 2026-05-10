from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from .models import PerfilUsuario, Direccion


class _BootstrapMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            existing = f.widget.attrs.get('class', '')
            f.widget.attrs['class'] = (existing + ' form-control').strip()


class RegistroForm(_BootstrapMixin, UserCreationForm):
    email = forms.EmailField(required=True, label='Email')

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')


class LoginForm(_BootstrapMixin, AuthenticationForm):
    pass


class PerfilForm(_BootstrapMixin, forms.ModelForm):
    first_name = forms.CharField(label='Nombre', required=False, max_length=60)
    last_name = forms.CharField(label='Apellido', required=False, max_length=60)
    email = forms.EmailField(label='Email')

    class Meta:
        model = PerfilUsuario
        fields = ['telefono', 'recibir_newsletter']

    def __init__(self, *args, **kwargs):
        usuario = kwargs.pop('usuario', None)
        super().__init__(*args, **kwargs)
        if usuario:
            self.fields['first_name'].initial = usuario.first_name
            self.fields['last_name'].initial = usuario.last_name
            self.fields['email'].initial = usuario.email
        # checkbox no usa form-control
        self.fields['recibir_newsletter'].widget.attrs['class'] = 'form-check-input'

    def save_full(self, usuario, commit=True):
        usuario.first_name = self.cleaned_data.get('first_name', '')
        usuario.last_name = self.cleaned_data.get('last_name', '')
        usuario.email = self.cleaned_data.get('email', '')
        perfil = super().save(commit=False)
        perfil.usuario = usuario
        if commit:
            usuario.save()
            perfil.save()
        return perfil


class DireccionForm(_BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Direccion
        fields = ['alias', 'nombre_destinatario', 'calle_numero', 'depto',
                  'comuna', 'region', 'referencia', 'telefono', 'es_predeterminada']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['es_predeterminada'].widget.attrs['class'] = 'form-check-input'
