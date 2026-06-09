from django.contrib import admin
from .models import CajaMovimiento, Cliente, IngresoMercancia, Pedido, ProductoAlmacen, Proveedor, Venta
# Register your models here.

admin.site.register(Pedido)
admin.site.register(Proveedor)
admin.site.register(ProductoAlmacen)
admin.site.register(IngresoMercancia)
admin.site.register(Cliente)
admin.site.register(Venta)
admin.site.register(CajaMovimiento)
