from django import forms
from django.core.exceptions import ValidationError
from .models import Categoria, IngresoMercancia, Producto, ProductoAlmacen, Proveedor, Mesa

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
    enlazar_inventario = forms.BooleanField(
        label="Enlazar a algun producto de almacen",
        required=False,
        widget=forms.CheckboxInput(attrs={
            "class": "inventory-link-toggle",
        }),
        help_text="Activalo si este producto debe descontar inventario al venderse"
    )

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

    producto_almacen = forms.ModelChoiceField(
        queryset=ProductoAlmacen.objects.none(),
        label="Producto de almacen",
        required=False,
        widget=forms.Select(attrs={
            "class": "form-input inventory-product-select",
            "data-searchable-inventory": "true",
        }),
        help_text="Producto que se descuenta cuando se vende este elemento"
    )

    cantidad_descontar = forms.DecimalField(
        label="Cantidad a descontar por venta",
        max_digits=10,
        decimal_places=2,
        min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={
            "class": "form-input",
            "step": "0.01",
            "min": "0",
        }),
        help_text="Ejemplo: 1 pieza, 0.25 kg o 0.50 litros"
    )
    
    class Meta:
        model = Producto
        fields = [
            "categoria",
            "nombre",
            "descripcion",
            "precio",
            "imagen",
            "enlazar_inventario",
            "producto_almacen",
            "cantidad_descontar",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["producto_almacen"].queryset = ProductoAlmacen.objects.filter(
            activo=True
        ).select_related("proveedor")
        if self.instance and self.instance.pk and self.instance.producto_almacen_id:
            self.fields["enlazar_inventario"].initial = True
    
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

    def clean(self):
        cleaned_data = super().clean()
        enlazar = cleaned_data.get("enlazar_inventario")
        producto_almacen = cleaned_data.get("producto_almacen")
        cantidad_descontar = cleaned_data.get("cantidad_descontar")

        if enlazar and not producto_almacen:
            self.add_error("producto_almacen", "Selecciona un producto de almacen")
        if enlazar and (cantidad_descontar is None or cantidad_descontar <= 0):
            self.add_error("cantidad_descontar", "Indica una cantidad mayor a 0")

        if not enlazar:
            cleaned_data["producto_almacen"] = None
            cleaned_data["cantidad_descontar"] = 1

        return cleaned_data


class ProveedorForm(forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = ["nombre", "telefono", "email", "direccion", "notas", "activo"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-input", "placeholder": "Nombre del proveedor"}),
            "telefono": forms.TextInput(attrs={"class": "form-input", "placeholder": "Telefono"}),
            "email": forms.EmailInput(attrs={"class": "form-input", "placeholder": "correo@proveedor.com"}),
            "direccion": forms.Textarea(attrs={"class": "form-input", "rows": 3}),
            "notas": forms.Textarea(attrs={"class": "form-input", "rows": 3}),
            "activo": forms.CheckboxInput(),
        }

    def clean_nombre(self):
        nombre = self.cleaned_data.get("nombre", "").strip()
        if not nombre:
            raise ValidationError("El nombre del proveedor no puede estar vacio")
        return nombre


class ProductoAlmacenForm(forms.ModelForm):
    class Meta:
        model = ProductoAlmacen
        fields = ["proveedor", "nombre", "unidad", "existencia", "minimo", "maximo", "activo"]
        widgets = {
            "proveedor": forms.Select(attrs={"class": "form-input"}),
            "nombre": forms.TextInput(attrs={"class": "form-input", "placeholder": "Ej: Tomate, Queso, Refresco"}),
            "unidad": forms.TextInput(attrs={"class": "form-input", "placeholder": "pieza, kg, litro, caja"}),
            "existencia": forms.NumberInput(attrs={"class": "form-input", "step": "0.01", "min": "0"}),
            "minimo": forms.NumberInput(attrs={"class": "form-input", "step": "0.01", "min": "0"}),
            "maximo": forms.NumberInput(attrs={"class": "form-input", "step": "0.01", "min": "0"}),
            "activo": forms.CheckboxInput(),
        }

    def clean(self):
        cleaned_data = super().clean()
        minimo = cleaned_data.get("minimo")
        maximo = cleaned_data.get("maximo")
        existencia = cleaned_data.get("existencia")

        if existencia is not None and existencia < 0:
            self.add_error("existencia", "La existencia no puede ser negativa")
        if minimo is not None and minimo < 0:
            self.add_error("minimo", "El minimo no puede ser negativo")
        if maximo is not None and maximo < 0:
            self.add_error("maximo", "El maximo no puede ser negativo")
        if minimo is not None and maximo is not None and maximo < minimo:
            self.add_error("maximo", "El maximo debe ser mayor o igual al minimo")

        return cleaned_data


class IngresoMercanciaForm(forms.ModelForm):
    class Meta:
        model = IngresoMercancia
        fields = ["proveedor", "producto_almacen", "cantidad", "costo_unitario", "referencia", "notas"]
        widgets = {
            "proveedor": forms.Select(attrs={"class": "form-input", "id": "id_proveedor_ingreso"}),
            "producto_almacen": forms.Select(attrs={"class": "form-input", "id": "id_producto_almacen_ingreso"}),
            "cantidad": forms.NumberInput(attrs={"class": "form-input", "step": "0.01", "min": "0.01"}),
            "costo_unitario": forms.NumberInput(attrs={"class": "form-input", "step": "0.01", "min": "0"}),
            "referencia": forms.TextInput(attrs={"class": "form-input", "placeholder": "Factura, nota o folio"}),
            "notas": forms.Textarea(attrs={"class": "form-input", "rows": 3}),
        }

    def clean(self):
        cleaned_data = super().clean()
        proveedor = cleaned_data.get("proveedor")
        producto_almacen = cleaned_data.get("producto_almacen")
        cantidad = cleaned_data.get("cantidad")

        if producto_almacen and proveedor and producto_almacen.proveedor_id != proveedor.id:
            self.add_error("producto_almacen", "Este producto no pertenece al proveedor seleccionado")
        if cantidad is not None and cantidad <= 0:
            self.add_error("cantidad", "La cantidad debe ser mayor a 0")

        return cleaned_data
