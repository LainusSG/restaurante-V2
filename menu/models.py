from django.db import models
from django.db.models import Sum
from django.utils.timezone import now


class Categoria(models.Model):
    nombre = models.CharField(max_length=100)

    def __str__(self):
        return self.nombre

class Producto(models.Model):
    categoria = models.ForeignKey(Categoria, on_delete=models.CASCADE, related_name="productos")
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    precio = models.DecimalField(max_digits=8, decimal_places=2)
    imagen = models.ImageField(upload_to="productos/", blank=True, null=True)

    def __str__(self):
        return self.nombre


class Mesa(models.Model):
    nombre = models.CharField(max_length=50, unique=True)
    ocupada = models.BooleanField(default=False)

    def __str__(self):
        return self.nombre

class Pedido(models.Model):
    mesa = models.ForeignKey(
        Mesa, on_delete=models.SET_NULL, null=True, blank=True, related_name="pedidos"
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    entregado = models.BooleanField(default=False)
    confirmado = models.BooleanField(default=False)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    atendido = models.BooleanField(default=False)

    def calcular_total(self):
        total = sum(item.subtotal() for item in self.items.select_related("producto").all())
        self.total = total
        self.save()
        return total

    def __str__(self):
        return f"Pedido #{self.id} - {self.mesa.nombre if self.mesa else 'Sin mesa'}"

class PedidoItem(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="items")
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    cantidad = models.PositiveIntegerField(default=1)
    observaciones = models.CharField(max_length=255, default="con todo")
    es_cortesia = models.BooleanField(default=False)
    confirmado = models.BooleanField(default=False)  # ya lo tenemos
    atendido = models.BooleanField(default=False)   # nuevo
    surtido = models.BooleanField(default=False)    # nuevo

    def importe_bruto(self):
        return self.cantidad * self.producto.precio

    def descuento_cortesia(self):
        return self.importe_bruto() if self.es_cortesia else 0

    def subtotal(self):
        return 0 if self.es_cortesia else self.importe_bruto()

    def __str__(self):
        return f"{self.producto.nombre} x{self.cantidad} ({self.observaciones})"

class VentaDiaria(models.Model):
    fecha = models.DateField(default=now)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f"Ventas {self.fecha}: {self.total}"


class Venta(models.Model):
    pedido = models.OneToOneField(
        Pedido,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="venta",
    )
    fecha = models.DateField(default=now)
    creado_en = models.DateTimeField(default=now)
    ticket_numero = models.PositiveIntegerField(null=True, blank=True)
    mesa_nombre = models.CharField(max_length=50, default="Sin mesa")
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self):
        return f"Venta #{self.id} - {self.fecha}: {self.total}"


class VentaItem(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name="items")
    producto_nombre = models.CharField(max_length=100)
    cantidad = models.PositiveIntegerField(default=1)
    observaciones = models.CharField(max_length=255, default="con todo")
    es_cortesia = models.BooleanField(default=False)
    precio_unitario = models.DecimalField(max_digits=8, decimal_places=2)
    descuento_cortesia = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.producto_nombre} x{self.cantidad}"


