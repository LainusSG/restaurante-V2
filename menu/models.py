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
    producto_almacen = models.ForeignKey(
        "ProductoAlmacen",
        on_delete=models.SET_NULL,
        related_name="productos_menu",
        blank=True,
        null=True,
    )
    cantidad_descontar = models.DecimalField(max_digits=10, decimal_places=2, default=1)

    def __str__(self):
        return self.nombre


class Proveedor(models.Model):
    nombre = models.CharField(max_length=150, unique=True)
    telefono = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    direccion = models.TextField(blank=True)
    notas = models.TextField(blank=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class ProductoAlmacen(models.Model):
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT, related_name="productos")
    nombre = models.CharField(max_length=150)
    unidad = models.CharField(max_length=30, default="pieza")
    existencia = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    minimo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    maximo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    activo = models.BooleanField(default=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nombre"]
        unique_together = ["proveedor", "nombre"]

    @property
    def faltante_para_maximo(self):
        faltante = self.maximo - self.existencia
        return faltante if faltante > 0 else 0

    @property
    def bajo_minimo(self):
        return self.existencia <= self.minimo

    def __str__(self):
        return f"{self.nombre} ({self.proveedor.nombre})"


class IngresoMercancia(models.Model):
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT, related_name="ingresos")
    producto_almacen = models.ForeignKey(ProductoAlmacen, on_delete=models.PROTECT, related_name="ingresos")
    cantidad = models.DecimalField(max_digits=12, decimal_places=2)
    referencia = models.CharField(max_length=120, blank=True)
    notas = models.TextField(blank=True)
    creado_en = models.DateTimeField(default=now)

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self):
        return f"{self.producto_almacen.nombre} +{self.cantidad}"


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


class Cliente(models.Model):
    nombre = models.CharField(max_length=150)
    telefono = models.CharField(max_length=30, blank=True)
    direccion = models.TextField(blank=True)
    notas = models.TextField(blank=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    @property
    def deuda_total(self):
        return self.ventas.filter(estado_pago=Venta.EstadoPago.PENDIENTE).aggregate(
            total=Sum("saldo_pendiente")
        )["total"] or 0


class Venta(models.Model):
    class MetodoPago(models.TextChoices):
        EFECTIVO = "efectivo", "Efectivo"
        TRANSFERENCIA = "transferencia", "Deposito o transferencia"
        FIADO = "fiado", "Deuda o fiado"

    class EstadoPago(models.TextChoices):
        SALDADA = "saldada", "Saldada"
        PENDIENTE = "pendiente", "Pendiente"

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
    metodo_pago = models.CharField(
        max_length=20,
        choices=MetodoPago.choices,
        default=MetodoPago.EFECTIVO,
    )
    estado_pago = models.CharField(
        max_length=20,
        choices=EstadoPago.choices,
        default=EstadoPago.SALDADA,
    )
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="ventas",
        null=True,
        blank=True,
    )
    saldo_pendiente = models.DecimalField(max_digits=10, decimal_places=2, default=0)

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


class CajaMovimiento(models.Model):
    class Tipo(models.TextChoices):
        VENTA = "venta", "Venta"
        ABONO = "abono", "Abono de deuda"

    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    metodo_pago = models.CharField(max_length=20, choices=Venta.MetodoPago.choices)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    fecha = models.DateField(default=now)
    creado_en = models.DateTimeField(default=now)
    venta = models.ForeignKey(
        Venta,
        on_delete=models.SET_NULL,
        related_name="movimientos_caja",
        null=True,
        blank=True,
    )
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.SET_NULL,
        related_name="movimientos_caja",
        null=True,
        blank=True,
    )
    descripcion = models.CharField(max_length=180, blank=True)

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.fecha}: {self.monto}"


