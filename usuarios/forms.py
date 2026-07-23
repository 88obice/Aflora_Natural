from django import forms
from django.core.validators import RegexValidator
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from .models import PerfilUsuario, Direccion


# Solo letras (incluye tildes y ñ) y espacios entre palabras. Sin numeros ni simbolos.
solo_letras = RegexValidator(
    regex=r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+(?:[ '\-][A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+)*$",
    message='El nombre solo puede contener letras y espacios.',
)


class _BootstrapMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            existing = f.widget.attrs.get('class', '')
            f.widget.attrs['class'] = (existing + ' form-control').strip()


class RegistroForm(_BootstrapMixin, UserCreationForm):
    """Registro tipo ecommerce: nombre + correo + contraseña.

    El username no se pide al cliente; se setea igual al correo por detras.
    """
    nombre = forms.CharField(
        label='Nombre',
        max_length=60,
        validators=[solo_letras],
        widget=forms.TextInput(attrs={'placeholder': 'Tu nombre'}),
    )
    email = forms.EmailField(required=True, label='Correo electrónico')

    class Meta:
        model = User
        fields = ('nombre', 'email', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # UserCreationForm agrega 'username' como campo obligatorio; lo quitamos
        # porque el cliente no lo ingresa (se setea = correo en save()).
        self.fields.pop('username', None)

    def clean_nombre(self):
        return self.cleaned_data['nombre'].strip()

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Ya existe una cuenta con este correo.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        # username = correo (invisible para el cliente; login es por correo).
        user.username = self.cleaned_data['email']
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['nombre']
        if commit:
            user.save()
        return user


class LoginForm(_BootstrapMixin, AuthenticationForm):
    """Login por correo. El campo sigue llamandose 'username' internamente
    (lo exige AuthenticationForm), pero se muestra y valida como correo.
    El EmailBackend resuelve el correo -> usuario."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Correo electrónico'
        self.fields['username'].widget.attrs.update({
            'type': 'email',
            'placeholder': 'tucorreo@ejemplo.com',
            'autofocus': True,
            'autocomplete': 'email',
        })


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
        # Telefono: prefijo chileno fijo para que el cliente no lo tipee.
        self.fields['telefono'].widget.attrs['placeholder'] = '+56 9 1234 5678'
        if not (self.instance and self.instance.telefono):
            self.fields['telefono'].initial = '+56 9 '
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
        # Telefono: prefijo chileno fijo.
        self.fields['telefono'].widget.attrs['placeholder'] = '+56 9 1234 5678'
        if not (self.instance and self.instance.pk and self.instance.telefono):
            self.fields['telefono'].initial = '+56 9 '
