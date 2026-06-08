from django.contrib import admin
from .models import IngresoMercancia, Pedido, ProductoAlmacen, Proveedor
# Register your models here.

admin.site.register(Pedido)
admin.site.register(Proveedor)
admin.site.register(ProductoAlmacen)
admin.site.register(IngresoMercancia)
