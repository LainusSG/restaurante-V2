import calendar
import json
from decimal import Decimal
from datetime import date, timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.utils.timezone import now
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Prefetch, Sum
from django.db.models.functions import TruncDay, TruncMonth, TruncYear

from .models import (
    CajaMovimiento,
    Categoria,
    Cliente,
    IngresoMercancia,
    MenuRestaurante,
    Producto,
    ProductoAlmacen,
    Pedido,
    PedidoItem,
    Mesa,
    Proveedor,
    VentaDiaria,
    Venta,
    VentaItem,
)
from .forms import (
    AbonoClienteForm,
    CategoriaForm,
    CerrarVentaForm,
    ClienteForm,
    IngresoMercanciaForm,
    MenuRestauranteForm,
    ProductoAlmacenForm,
    ProductoForm,
    MesaForm,
    ProveedorForm,
)


def _es_admin(user):
    return user.is_authenticated and user.is_staff


admin_required = user_passes_test(_es_admin, login_url="login")


# =====================
# SelecciÃ³n de mesa
# =====================
def seleccionar_mesa(request):
    mesas = Mesa.objects.all()
    return render(request, "menu/seleccionar_mesa.html", {"mesas": mesas})


# =====================
# MenÃº y pedidos
# =====================
def menu_view(request, mesa_id):
    mesa = get_object_or_404(Mesa, id=mesa_id)
    categorias = Categoria.objects.select_related("menu").prefetch_related("productos").all()

    pedido, _ = Pedido.objects.get_or_create(
        mesa=mesa,
        entregado=False
    )

    pedido.calcular_total()

    # âœ… Revisar si todos los items ya fueron surtidos
    todos_entregados = not pedido.items.filter(surtido=False).exists()

    return render(request, "menu/menu.html", {
        "categorias": categorias,
        "pedido": pedido,
        "mesa": mesa,
        "todos_entregados": todos_entregados,
    })


def agregar_al_pedido(request, mesa_id, producto_id):
    mesa = get_object_or_404(Mesa, id=mesa_id)
    producto = get_object_or_404(Producto, id=producto_id)

    pedido, _ = Pedido.objects.get_or_create(
        mesa=mesa,
        entregado=False
    )

    observaciones = request.POST.get("observaciones", "").strip()
    if not observaciones:
        observaciones = "con todo"
    es_cortesia = request.POST.get("es_cortesia") == "on"

    # ðŸš¨ Siempre crear un nuevo item
    PedidoItem.objects.create(
        pedido=pedido,
        producto=producto,
        observaciones=observaciones,
        es_cortesia=es_cortesia,
        cantidad=1,
        confirmado=False
    )

    # ðŸš¨ Si ya estaba confirmado, volver a marcarlo como NO confirmado
    if pedido.confirmado:
        pedido.confirmado = False
        pedido.save()

    return redirect("menu", mesa_id=mesa.id)


def eliminar_item_pedido(request, mesa_id, item_id):
    item = get_object_or_404(PedidoItem, id=item_id, pedido__mesa_id=mesa_id)

    if item.confirmado:
        return redirect("menu", mesa_id=mesa_id)

    if item.cantidad > 1:
        item.cantidad -= 1
        item.save()
    else:
        item.delete()

    return redirect("menu", mesa_id=mesa_id)


def confirmar_pedido(request, mesa_id, pedido_id):
    mesa = get_object_or_404(Mesa, id=mesa_id)
    pedido = get_object_or_404(Pedido, id=pedido_id, mesa=mesa, confirmado=False)

    if request.method == "POST":
        pedido.items.filter(confirmado=False).update(confirmado=True)
        pedido.calcular_total()
        pedido.confirmado = True
        mesa.ocupada = True
        mesa.save()
        pedido.save()

    return redirect("menu", mesa_id=mesa.id)


def _crear_venta_desde_pedido(pedido, metodo_pago=Venta.MetodoPago.EFECTIVO, cliente=None):
    es_fiado = metodo_pago == Venta.MetodoPago.FIADO
    venta, creada = Venta.objects.get_or_create(
        pedido=pedido,
        defaults={
            "fecha": now().date(),
            "creado_en": now(),
            "ticket_numero": pedido.id,
            "mesa_nombre": pedido.mesa.nombre if pedido.mesa else "Sin mesa",
            "total": pedido.total,
            "metodo_pago": metodo_pago,
            "estado_pago": Venta.EstadoPago.PENDIENTE if es_fiado else Venta.EstadoPago.SALDADA,
            "cliente": cliente,
            "saldo_pendiente": pedido.total if es_fiado else 0,
        },
    )

    if creada:
        VentaItem.objects.bulk_create([
            VentaItem(
                venta=venta,
                producto_nombre=item.producto.nombre,
                cantidad=item.cantidad,
                observaciones=item.observaciones,
                es_cortesia=item.es_cortesia,
                precio_unitario=item.producto.precio,
                descuento_cortesia=item.descuento_cortesia(),
                subtotal=item.subtotal(),
            )
            for item in pedido.items.select_related("producto").all()
        ])

    return venta


def _registrar_entrada_caja(monto, metodo_pago, tipo, venta=None, cliente=None, descripcion=""):
    if monto <= 0:
        return None

    movimiento = CajaMovimiento.objects.create(
        tipo=tipo,
        metodo_pago=metodo_pago,
        monto=monto,
        fecha=now().date(),
        venta=venta,
        cliente=cliente,
        descripcion=descripcion,
    )
    venta_diaria, _ = VentaDiaria.objects.get_or_create(fecha=movimiento.fecha)
    venta_diaria.total += monto
    venta_diaria.save(update_fields=["total"])
    return movimiento


def _descontar_inventario_desde_pedido(pedido):
    faltantes = []
    descuentos = {}
    items = pedido.items.select_related("producto", "producto__producto_almacen")

    for item in items:
        producto_menu = item.producto
        if not producto_menu.producto_almacen_id:
            continue

        producto_almacen = ProductoAlmacen.objects.select_for_update().get(
            id=producto_menu.producto_almacen_id
        )
        cantidad_descontar = producto_menu.cantidad_descontar or Decimal("1")
        cantidad_necesaria = cantidad_descontar * item.cantidad

        if producto_almacen.id in descuentos:
            descuentos[producto_almacen.id]["cantidad"] += cantidad_necesaria
            continue

        descuentos[producto_almacen.id] = {
            "producto": producto_almacen,
            "cantidad": cantidad_necesaria,
        }

    for descuento in descuentos.values():
        producto_almacen = descuento["producto"]
        cantidad_necesaria = descuento["cantidad"]
        if producto_almacen.existencia < cantidad_necesaria:
            faltantes.append(
                f"{producto_almacen.nombre}: disponible {producto_almacen.existencia} "
                f"{producto_almacen.unidad}, requerido {cantidad_necesaria} {producto_almacen.unidad}"
            )

    if faltantes:
        return faltantes

    for descuento in descuentos.values():
        producto_almacen = descuento["producto"]
        cantidad_necesaria = descuento["cantidad"]
        producto_almacen.existencia -= cantidad_necesaria
        producto_almacen.save(update_fields=["existencia", "actualizado_en"])

    return []


def generar_ticket(request, mesa_id, pedido_id):
    mesa = get_object_or_404(Mesa, id=mesa_id)
    pedido = get_object_or_404(Pedido, id=pedido_id, mesa=mesa, confirmado=True, entregado=False)

    if pedido.items.filter(surtido=False).exists():
        return redirect("menu", mesa_id=mesa.id)

    pedido.calcular_total()
    form = CerrarVentaForm(request.POST or None)
    if request.method != "POST":
        return render(request, "menu/cerrar_venta.html", {
            "form": form,
            "pedido": pedido,
            "mesa": mesa,
        })

    if not form.is_valid():
        return render(request, "menu/cerrar_venta.html", {
            "form": form,
            "pedido": pedido,
            "mesa": mesa,
        })

    with transaction.atomic():
        pedido.calcular_total()
        faltantes = _descontar_inventario_desde_pedido(pedido)
        if faltantes:
            messages.error(request, "Inventario insuficiente: " + "; ".join(faltantes))
            return redirect("menu", mesa_id=mesa.id)

        metodo_pago = form.cleaned_data["metodo_pago"]
        cliente = form.cleaned_data["cliente"]
        venta = _crear_venta_desde_pedido(pedido, metodo_pago=metodo_pago, cliente=cliente)
        if metodo_pago != Venta.MetodoPago.FIADO:
            _registrar_entrada_caja(
                venta.total,
                metodo_pago,
                CajaMovimiento.Tipo.VENTA,
                venta=venta,
                descripcion=f"Venta ticket #{venta.ticket_numero or venta.id}",
            )

        pedido.entregado = True
        pedido.save()

        mesa.ocupada = False
        mesa.save()

    return render(request, "menu/ticket.html", {"pedido": pedido, "venta": venta})

def detalle_venta(request, venta_id):
    venta = get_object_or_404(Venta.objects.prefetch_related("items"), id=venta_id)
    return render(request, "menu/detalle_venta.html", {"venta": venta})


def reimprimir_ticket(request, venta_id):
    venta = get_object_or_404(Venta.objects.prefetch_related("items"), id=venta_id)
    return render(request, "menu/ticket.html", {"venta": venta, "reimpresion": True})


def listar_clientes(request):
    busqueda = request.GET.get("q", "").strip()
    clientes = Cliente.objects.all()
    if busqueda:
        clientes = clientes.filter(nombre__icontains=busqueda)

    for cliente in clientes:
        cliente.deuda_actual = cliente.deuda_total

    return render(request, "menu/clientes.html", {
        "clientes": clientes,
        "busqueda": busqueda,
    })


def crear_cliente(request):
    if request.method == "POST":
        form = ClienteForm(request.POST)
        if form.is_valid():
            cliente = form.save()
            messages.success(request, "Cliente creado correctamente")
            return redirect("detalle_cliente", cliente_id=cliente.id)
    else:
        form = ClienteForm()
    return render(request, "menu/cliente_form.html", {"form": form, "titulo": "Crear cliente"})


def editar_cliente(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    if request.method == "POST":
        form = ClienteForm(request.POST, instance=cliente)
        if form.is_valid():
            form.save()
            messages.success(request, "Cliente actualizado correctamente")
            return redirect("detalle_cliente", cliente_id=cliente.id)
    else:
        form = ClienteForm(instance=cliente)
    return render(request, "menu/cliente_form.html", {
        "form": form,
        "cliente": cliente,
        "titulo": "Editar cliente",
    })


def detalle_cliente(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    ventas_pendientes = cliente.ventas.filter(
        estado_pago=Venta.EstadoPago.PENDIENTE
    ).prefetch_related("items").order_by("creado_en")
    ventas_saldadas = cliente.ventas.filter(
        estado_pago=Venta.EstadoPago.SALDADA
    ).prefetch_related("items").order_by("-creado_en")
    deuda_total = ventas_pendientes.aggregate(total=Sum("saldo_pendiente"))["total"] or 0

    if request.method == "POST":
        form = AbonoClienteForm(request.POST)
        if form.is_valid():
            monto = form.cleaned_data["monto"]
            metodo_pago = form.cleaned_data["metodo_pago"]

            if monto > deuda_total:
                form.add_error("monto", "El abono no puede ser mayor a la deuda total")
            else:
                restante = monto
                with transaction.atomic():
                    ventas_para_abono = cliente.ventas.select_for_update().filter(
                        estado_pago=Venta.EstadoPago.PENDIENTE
                    ).order_by("creado_en")
                    for venta in ventas_para_abono:
                        if restante <= 0:
                            break
                        aplicado = min(restante, venta.saldo_pendiente)
                        venta.saldo_pendiente -= aplicado
                        if venta.saldo_pendiente <= 0:
                            venta.saldo_pendiente = 0
                            venta.estado_pago = Venta.EstadoPago.SALDADA
                        venta.save(update_fields=["saldo_pendiente", "estado_pago"])
                        _registrar_entrada_caja(
                            aplicado,
                            metodo_pago,
                            CajaMovimiento.Tipo.ABONO,
                            venta=venta,
                            cliente=cliente,
                            descripcion=f"Abono cliente {cliente.nombre}",
                        )
                        restante -= aplicado

                messages.success(request, "Abono registrado correctamente")
                return redirect("detalle_cliente", cliente_id=cliente.id)
    else:
        form = AbonoClienteForm()

    movimientos = cliente.movimientos_caja.select_related("venta")[:30]
    return render(request, "menu/cliente_detalle.html", {
        "cliente": cliente,
        "ventas_pendientes": ventas_pendientes,
        "ventas_saldadas": ventas_saldadas,
        "deuda_total": deuda_total,
        "form": form,
        "movimientos": movimientos,
    })


@require_http_methods(["POST"])
def eliminar_cliente(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    if cliente.ventas.exists():
        cliente.activo = False
        cliente.save(update_fields=["activo"])
        messages.success(request, "Cliente desactivado porque tiene ventas registradas")
    else:
        cliente.delete()
        messages.success(request, "Cliente eliminado correctamente")
    return redirect("listar_clientes")




# =====================
# Cocina
# =====================
def pedidos_cocina(request):
    pedidos = (
        Pedido.objects.filter(confirmado=True, entregado=False)
        .select_related("mesa")
        .prefetch_related("items__producto")
    )
    return render(request, "menu/cocina.html", {"pedidos": pedidos})


def pedidos_cocina_json(request):
    pedidos = (
        Pedido.objects.filter(confirmado=True, entregado=False)
        .select_related("mesa")
        .prefetch_related("items__producto")
    )
    html = render_to_string("menu/pedidos_list.html", {"pedidos": pedidos})
    return JsonResponse({"html": html})


def atender_item(request, item_id):
    item = get_object_or_404(PedidoItem, id=item_id, confirmado=True, atendido=False)
    item.atendido = True
    item.save()
    return redirect("cocina")


def surtir_item(request, item_id):
    item = get_object_or_404(PedidoItem, id=item_id, confirmado=True, atendido=True, surtido=False)
    item.surtido = True
    item.save()
    return redirect("cocina")


# =====================
# Dashboard de ventas
# =====================
def _fecha_corta(fecha):
    return fecha.strftime("%d/%m/%Y")


def _periodo_label(periodo, filtro):
    inicio = periodo["inicio"] if isinstance(periodo, dict) else periodo
    inicio = inicio.date() if hasattr(inicio, "date") else inicio

    if filtro == "semana":
        fin = periodo["fin"] if isinstance(periodo, dict) else inicio + timedelta(days=6)
        numero_semana = periodo["numero"] if isinstance(periodo, dict) else inicio.isocalendar()[1]
        return f"Semana {numero_semana}: {_fecha_corta(inicio)} - {_fecha_corta(fin)}"

    if filtro == "mes":
        ultimo_dia = calendar.monthrange(inicio.year, inicio.month)[1]
        fin = date(inicio.year, inicio.month, ultimo_dia)
        return f"{_fecha_corta(inicio)} - {_fecha_corta(fin)}"

    if filtro in ("aÃ±o", "aÃƒÂ±o"):
        fin = date(inicio.year, 12, 31)
        return f"{_fecha_corta(inicio)} - {_fecha_corta(fin)}"

    return _fecha_corta(inicio)


def _ventas_por_semana_desde_enero(ventas):
    semanas = {}

    for venta in ventas:
        # ISO 8601: Semana comienza lunes (1) y termina domingo (7)
        ano_iso, numero_semana, _ = venta.fecha.isocalendar()
        
        # Calcular el lunes de la semana ISO
        inicio = date.fromisocalendar(ano_iso, numero_semana, 1)  # 1 = lunes
        fin = date.fromisocalendar(ano_iso, numero_semana, 7)     # 7 = domingo
        
        clave = (ano_iso, numero_semana)

        if clave not in semanas:
            semanas[clave] = {
                "periodo": {"inicio": inicio, "fin": fin, "numero": numero_semana},
                "total": 0,
            }

        semanas[clave]["total"] += venta.total

    return [semanas[clave] for clave in sorted(semanas)]


def _sumar_ventas(ventas):
    return ventas.aggregate(total=Sum("total"))["total"] or 0


def _sumar_movimientos(movimientos):
    return movimientos.aggregate(total=Sum("monto"))["total"] or 0


def _consulta_caja_fisica(request):
    hoy = now().date()
    tipo = request.GET.get("total_tipo", "dia")
    valor = request.GET.get("total_valor", "")
    movimientos = CajaMovimiento.objects.filter(metodo_pago=Venta.MetodoPago.EFECTIVO)

    try:
        if valor and tipo == "mes":
            ano, mes = [int(parte) for parte in valor.split("-", 1)]
            total = _sumar_movimientos(movimientos.filter(fecha__year=ano, fecha__month=mes))
        elif valor and tipo in ("aÃ±o", "ano"):
            ano = int(valor)
            total = _sumar_movimientos(movimientos.filter(fecha__year=ano))
        elif valor:
            total = _sumar_movimientos(movimientos.filter(fecha=date.fromisoformat(valor)))
        else:
            total = _sumar_movimientos(movimientos.filter(fecha=hoy))
    except (TypeError, ValueError):
        total = _sumar_movimientos(movimientos.filter(fecha=hoy))

    return total


def _consulta_total_ventas(request, ventas):
    hoy = now().date()
    tipo = request.GET.get("total_tipo", "dia")
    valor = request.GET.get("total_valor", "")
    consulta_activa = bool(valor)

    if not consulta_activa:
        total = _sumar_ventas(ventas.filter(fecha=hoy))
        return {
            "tipo": "dia",
            "valor": hoy.isoformat(),
            "label": f"Hoy, {_fecha_corta(hoy)}",
            "total": total,
            "datos": None,
        }

    try:
        if tipo == "mes":
            ano, mes = [int(parte) for parte in valor.split("-", 1)]
            inicio = date(ano, mes, 1)
            total = _sumar_ventas(ventas.filter(fecha__year=ano, fecha__month=mes))
            return {
                "tipo": "mes",
                "valor": valor,
                "label": _periodo_label(inicio, "mes"),
                "total": total,
                "datos": [{"periodo": inicio, "total": total}],
            }

        if tipo in ("aÃ±o", "ano"):
            ano = int(valor)
            inicio = date(ano, 1, 1)
            total = _sumar_ventas(ventas.filter(fecha__year=ano))
            return {
                "tipo": "aÃ±o",
                "valor": valor,
                "label": _periodo_label(inicio, "aÃ±o"),
                "total": total,
                "datos": [{"periodo": inicio, "total": total}],
            }

        dia = date.fromisoformat(valor)
        total = _sumar_ventas(ventas.filter(fecha=dia))
        return {
            "tipo": "dia",
            "valor": valor,
            "label": _fecha_corta(dia),
            "total": total,
            "datos": [{"periodo": dia, "total": total}],
        }
    except (TypeError, ValueError):
        total = _sumar_ventas(ventas.filter(fecha=hoy))
        return {
            "tipo": "dia",
            "valor": hoy.isoformat(),
            "label": f"Hoy, {_fecha_corta(hoy)}",
            "total": total,
            "datos": None,
        }


def dashboard_ventas(request):
    filtro = request.GET.get("filtro", "dia")

    ventas = VentaDiaria.objects.all().order_by("fecha")
    movimientos_caja = CajaMovimiento.objects.select_related("venta", "cliente").order_by("-creado_en")
    consulta_total = _consulta_total_ventas(request, ventas)
    caja_fisica_total = _consulta_caja_fisica(request)

    if consulta_total["datos"] is not None and consulta_total["tipo"] == "dia":
        filtro = "dia"
        datos = movimientos_caja.filter(fecha=date.fromisoformat(consulta_total["valor"]))
    elif consulta_total["datos"] is not None:
        filtro = consulta_total["tipo"]
        datos = consulta_total["datos"]
    elif filtro == "dia":
        datos = movimientos_caja
    elif filtro == "semana":
        datos = _ventas_por_semana_desde_enero(ventas)
    elif filtro == "mes":
        datos = ventas.annotate(periodo=TruncMonth("fecha")).values("periodo").annotate(total=Sum("total")).order_by("periodo")
    elif filtro == "aÃ±o":
        datos = ventas.annotate(periodo=TruncYear("fecha")).values("periodo").annotate(total=Sum("total")).order_by("periodo")
    else:
        filtro = "dia"
        datos = ventas_individuales

    datos = list(datos)
    for dato in datos:
        if isinstance(dato, CajaMovimiento):
            origen = "Abono" if dato.tipo == CajaMovimiento.Tipo.ABONO else "Venta"
            mesa = f" - Mesa {dato.venta.mesa_nombre}" if dato.venta else ""
            cliente = f" - {dato.cliente.nombre}" if dato.cliente else ""
            dato.periodo_label = f"{origen} {_fecha_corta(dato.fecha)} {dato.creado_en.strftime('%H:%M')}{mesa}{cliente}"
        else:
            dato["periodo_label"] = _periodo_label(dato["periodo"], filtro)

    labels = [d.periodo_label if isinstance(d, CajaMovimiento) else d["periodo_label"] for d in datos]
    valores = [float(d.monto if isinstance(d, CajaMovimiento) else d["total"]) for d in datos]
    total_general_label = f"${consulta_total['total']:,.2f}"
    caja_fisica_label = f"${caja_fisica_total:,.2f}"
    paginator = Paginator(datos, 15)
    page_obj = paginator.get_page(request.GET.get("page"))
    pagination_params = request.GET.copy()
    pagination_params.pop("page", None)
    pagination_query = pagination_params.urlencode()

    return render(request, "menu/dashboard.html", {
        "filtro": filtro,
        "labels": json.dumps(labels),
        "valores": json.dumps(valores),
        "total_general_label": total_general_label,
        "caja_fisica_label": caja_fisica_label,
        "consulta_total": consulta_total,
        "datos": page_obj,
        "page_obj": page_obj,
        "pagination_query": pagination_query,
    })


# =====================
# CRUD CategorÃ­as y Productos
# =====================
@admin_required
def crear_categoria(request):
    if request.method == "POST":
        form = CategoriaForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("crear_menu")
    else:
        form = CategoriaForm()
    return render(request, "menu/crear_categoria.html", {"form": form})


@admin_required
def crear_producto(request):
    if request.method == "POST":
        form = ProductoForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect("crear_menu")
    else:
        form = ProductoForm()
    return render(request, "menu/crear_producto.html", {"form": form})


@admin_required
def obtener_categorias_por_menu(request, menu_id):
    """
    Devuelve las categorías de un menú específico en formato JSON.
    Se utiliza para filtrar dinámicamente el campo de categoría en el formulario de crear producto.
    """
    try:
        menu = MenuRestaurante.objects.get(id=menu_id, activo=True)
        categorias = Categoria.objects.filter(menu=menu).values("id", "nombre")
        return JsonResponse({
            "success": True,
            "categorias": list(categorias)
        })
    except MenuRestaurante.DoesNotExist:
        return JsonResponse({
            "success": False,
            "error": "Menú no encontrado"
        }, status=404)


@admin_required
def crear_menu_restaurante(request):
    if request.method == "POST":
        form = MenuRestauranteForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Menu creado correctamente")
            return redirect("crear_menu")
    else:
        form = MenuRestauranteForm()
    return render(request, "menu/menu_restaurante_form.html", {
        "form": form,
        "titulo": "Crear menu",
    })


@admin_required
def editar_menu_restaurante(request, menu_id):
    menu = get_object_or_404(MenuRestaurante, id=menu_id)
    if request.method == "POST":
        form = MenuRestauranteForm(request.POST, instance=menu)
        if form.is_valid():
            form.save()
            messages.success(request, "Menu actualizado correctamente")
            return redirect("crear_menu")
    else:
        form = MenuRestauranteForm(instance=menu)
    return render(request, "menu/menu_restaurante_form.html", {
        "form": form,
        "titulo": "Editar menu",
        "menu": menu,
    })


@admin_required
@require_http_methods(["POST"])
def eliminar_menu_restaurante(request, menu_id):
    menu = get_object_or_404(MenuRestaurante, id=menu_id)
    
    # Verificar si el menú tiene categorías
    if menu.categorias.exists():
        messages.error(request, f"No se puede eliminar el menu '{menu.nombre}' porque tiene categorías asociadas. Elimina primero todas sus categorías.")
        return redirect("crear_menu")
    
    # Verificar si el menú tiene productos
    if menu.productos.exists():
        messages.error(request, f"No se puede eliminar el menu '{menu.nombre}' porque tiene productos asociados. Elimina primero todos sus productos.")
        return redirect("crear_menu")
    
    nombre_menu = menu.nombre
    menu.delete()
    messages.success(request, f"Menu '{nombre_menu}' eliminado correctamente")
    return redirect("crear_menu")


@admin_required
def crear_menu(request):
    productos = Producto.objects.select_related("categoria").order_by("nombre")
    categorias = Categoria.objects.prefetch_related(
        Prefetch("productos", queryset=productos)
    )
    menus = MenuRestaurante.objects.prefetch_related(
        Prefetch("categorias", queryset=categorias),
        "productos",
    )
    return render(request, "menu/crear_menu.html", {
        "menus": menus,
    })


@admin_required
def inventario(request):
    proveedor_id = request.GET.get("proveedor", "")
    busqueda = request.GET.get("q", "").strip()

    productos = ProductoAlmacen.objects.select_related("proveedor").filter(activo=True)
    if proveedor_id:
        productos = productos.filter(proveedor_id=proveedor_id)
    if busqueda:
        productos = productos.filter(nombre__icontains=busqueda)

    context = {
        "productos": productos,
        "proveedores": Proveedor.objects.filter(activo=True),
        "proveedor_id": proveedor_id,
        "busqueda": busqueda,
    }
    return render(request, "menu/inventario.html", context)


@admin_required
def crear_proveedor(request):
    if request.method == "POST":
        form = ProveedorForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Proveedor creado correctamente")
            return redirect("inventario")
    else:
        form = ProveedorForm()
    return render(request, "menu/crear_proveedor.html", {"form": form})


@admin_required
def crear_producto_almacen(request):
    if request.method == "POST":
        form = ProductoAlmacenForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Producto de almacen creado correctamente")
            return redirect("inventario")
    else:
        form = ProductoAlmacenForm()
    return render(request, "menu/crear_producto_almacen.html", {"form": form})


@admin_required
def ingresar_mercancia(request):
    productos = ProductoAlmacen.objects.filter(activo=True).select_related("proveedor")
    productos_por_proveedor = [
        {
            "id": producto.id,
            "proveedor_id": producto.proveedor_id,
            "nombre": producto.nombre,
            "unidad": producto.unidad,
        }
        for producto in productos
    ]

    if request.method == "POST":
        form = IngresoMercanciaForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                ingreso = form.save()
                producto = ProductoAlmacen.objects.select_for_update().get(id=ingreso.producto_almacen_id)
                producto.existencia += ingreso.cantidad
                producto.save(update_fields=["existencia", "actualizado_en"])
            messages.success(request, "Mercancia ingresada correctamente")
            return redirect("inventario")
    else:
        proveedor_inicial = request.GET.get("proveedor")
        initial = {"proveedor": proveedor_inicial} if proveedor_inicial else None
        form = IngresoMercanciaForm(initial=initial)

    return render(request, "menu/ingresar_mercancia.html", {
        "form": form,
        "productos_por_proveedor": productos_por_proveedor,
    })


@admin_required
def editar_categoria(request, categoria_id):
    categoria = get_object_or_404(Categoria, id=categoria_id)
    if request.method == "POST":
        form = CategoriaForm(request.POST, instance=categoria)
        if form.is_valid():
            form.save()
            return redirect("crear_menu")
    else:
        form = CategoriaForm(instance=categoria)
    return render(request, "menu/editar_categoria.html", {"form": form, "categoria": categoria})


@admin_required
@require_http_methods(["POST"])
def eliminar_categoria(request, categoria_id):
    categoria = get_object_or_404(Categoria, id=categoria_id)
    categoria.delete()
    return redirect("crear_menu")


@admin_required
def editar_producto(request, producto_id):
    producto = get_object_or_404(Producto, id=producto_id)
    if request.method == "POST":
        form = ProductoForm(request.POST, request.FILES, instance=producto)
        if form.is_valid():
            form.save()
            return redirect("crear_menu")
    else:
        form = ProductoForm(instance=producto)
    return render(request, "menu/editar_producto.html", {"form": form, "producto": producto})


@admin_required
@require_http_methods(["POST"])
def eliminar_producto(request, producto_id):
    producto = get_object_or_404(Producto, id=producto_id)
    producto.delete()
    return redirect("crear_menu")


# =====================
# CRUD Mesas
# =====================
def crear_mesa(request):
    if request.method == "POST":
        form = MesaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Mesa creada correctamente âœ…")
            return redirect("listar_mesas")
    else:
        form = MesaForm()
    return render(request, "menu/crear_mesa.html", {"form": form})


def listar_mesas(request):
    mesas = Mesa.objects.all()
    return render(request, "menu/listar_mesas.html", {"mesas": mesas})


def borrar_mesa(request, mesa_id):
    mesa = get_object_or_404(Mesa, id=mesa_id)
    if request.method == "POST":
        mesa.delete()
        return redirect("listar_mesas")
    return render(request, "menu/confirmar_borrar.html", {"mesa": mesa})



def Menu_cliente(request):
    menus = MenuRestaurante.objects.filter(activo=True).order_by("orden", "nombre")
    if menus.count() == 1:
        return redirect("menu_cliente_detalle", menu_id=menus.first().id)
    return render(request, "menu/seleccionar_menu_cliente.html", {"menus": menus})


def menu_cliente_detalle(request, menu_id):
    menu_restaurante = get_object_or_404(MenuRestaurante, id=menu_id, activo=True)
    productos = Producto.objects.filter(menu=menu_restaurante).order_by("nombre")
    categorias = (
        Categoria.objects.filter(menu=menu_restaurante)
        .prefetch_related(Prefetch("productos", queryset=productos))
    )
    return render(request, "menu/menu_cliente.html", {
        "categorias": categorias,
        "menu_restaurante": menu_restaurante,
    })

