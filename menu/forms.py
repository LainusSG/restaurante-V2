from django import forms
from django.core.exceptions import ValidationError
from .models import Categoria, Producto, Mesa

class MesaForm(forms.ModelForm):
    nombre = forms.CharField(
        label="Nombre de la mesa",
        max_length=50,
        widget=forms.TextInput(attrs={
            "class": "form-input",
            "placeholder": "Ej: Mesa 1, Mesa A, Terraza 3",
            "required": "required",
        }),
        help_text="Nombre único para identificar la mesa"
    )
    
    class Meta:
        model = Mesa
        fields = ["nombre"]
    
    def clean_nombre(self):
        nombre = self.cleaned_data.get('nombre', '').strip()
        if not nombre:
            raise ValidationError("El nombre de la mesa no puede estar vacío")
        if len(nombre) < 2:
            raise ValidationError("El nombre debe tener al menos 2 caracteres")
        if Mesa.objects.filter(nombre__iexact=nombre).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Ya existe una mesa con este nombre")
        return nombre

class CategoriaForm(forms.ModelForm):
    nombre = forms.CharField(
        label="Nombre de la categoría",
        max_length=100,
        widget=forms.TextInput(attrs={
            "class": "form-input",
            "placeholder": "Ej: Entradas, Platos Principales, Bebidas",
            "required": "required",
        }),
        help_text="Nombre descriptivo para agrupar productos"
    )
    
    class Meta:
        model = Categoria
        fields = ["nombre"]
    
    def clean_nombre(self):
        nombre = self.cleaned_data.get('nombre', '').strip()
        if not nombre:
            raise ValidationError("El nombre de la categoría no puede estar vacío")
        if len(nombre) < 2:
            raise ValidationError("El nombre debe tener al menos 2 caracteres")
        if Categoria.objects.filter(nombre__iexact=nombre).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Ya existe una categoría con este nombre")
        return nombre

class ProductoForm(forms.ModelForm):
    categoria = forms.ModelChoiceField(
        queryset=Categoria.objects.all(),
        label="Categoría",
        widget=forms.Select(attrs={
            "class": "form-input",
            "required": "required",
        }),
        help_text="Selecciona la categoría a la que pertenece este producto"
    )
    
    nombre = forms.CharField(
        label="Nombre del producto",
        max_length=100,
        widget=forms.TextInput(attrs={
            "class": "form-input",
            "placeholder": "Ej: Filete de res, Ensalada César",
            "required": "required",
        }),
        help_text="Nombre visible en el menú"
    )
    
    descripcion = forms.CharField(
        label="Descripción",
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-input",
            "placeholder": "Describe los ingredientes o características principales...",
            "rows": 3,
        }),
        help_text="Opcional: detalles que ayuden a los clientes a elegir"
    )
    
    precio = forms.DecimalField(
        label="Precio",
        max_digits=8,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            "class": "form-input",
            "placeholder": "0.00",
            "step": "0.01",
            "min": "0",
            "required": "required",
        }),
        help_text="Precio en moneda local"
    )
    
    imagen = forms.ImageField(
        label="Imagen del producto",
        required=False,
        widget=forms.FileInput(attrs={
            "class": "form-input",
            "accept": "image/*",
        }),
        help_text="Formatos permitidos: JPG, PNG, GIF. Máximo 5MB"
    )
    
    class Meta:
        model = Producto
        fields = ["categoria", "nombre", "descripcion", "precio", "imagen"]
    
    def clean_nombre(self):
        nombre = self.cleaned_data.get('nombre', '').strip()
        if not nombre:
            raise ValidationError("El nombre del producto no puede estar vacío")
        if len(nombre) < 2:
            raise ValidationError("El nombre debe tener al menos 2 caracteres")
        return nombre
    
    def clean_precio(self):
        precio = self.cleaned_data.get('precio')
        if precio is not None and precio < 0:
            raise ValidationError("El precio no puede ser negativo")
        if precio is not None and precio > 99999.99:
            raise ValidationError("El precio es demasiado alto")
        return precio
    
    def clean_imagen(self):
        imagen = self.cleaned_data.get('imagen')
        if imagen:
            if imagen.size > 5 * 1024 * 1024:  # 5MB
                raise ValidationError("La imagen no puede pesar más de 5MB")
        return imagen