from django.urls import path
from . import views

urlpatterns = [
    # Pantalla inicial = seleccionar mesa
    path("", views.seleccionar_mesa, name="seleccionar_mesa"),
    path("menu", views.Menu_cliente, name="menu_cliente"),

    # Menú por mesa
    path("mesa/<int:mesa_id>/", views.menu_view, name="menu"),
    path("mesa/<int:mesa_id>/agregar/<int:producto_id>/", views.agregar_al_pedido, name="agregar_al_pedido"),
    path("mesa/<int:mesa_id>/eliminar/<int:item_id>/", views.eliminar_item_pedido, name="eliminar_item_pedido"),
    path("mesa/<int:mesa_id>/confirmar/<int:pedido_id>/", views.confirmar_pedido, name="confirmar_pedido"),
    path("mesa/<int:mesa_id>/ticket/<int:pedido_id>/", views.generar_ticket, name="generar_ticket"),

    # Cocina
    path("cocina/", views.pedidos_cocina, name="cocina"),
    path("cocina/json/", views.pedidos_cocina_json, name="pedidos_cocina_json"),
    path("item/<int:item_id>/atender/", views.atender_item, name="atender_item"),
    path("item/<int:item_id>/surtir/", views.surtir_item, name="surtir_item"),

    # Dashboard
    path("dashboard/", views.dashboard_ventas, name="dashboard"),

    # CRUD Menú
    path("administrador", views.crear_menu, name="crear_menu"),
    path("menu/crear/categoria/", views.crear_categoria, name="crear_categoria"),
    path("menu/crear/producto/", views.crear_producto, name="crear_producto"),
    path("categoria/editar/<int:categoria_id>/", views.editar_categoria, name="editar_categoria"),
    path("categoria/eliminar/<int:categoria_id>/", views.eliminar_categoria, name="eliminar_categoria"),
    path("producto/<int:producto_id>/editar/", views.editar_producto, name="editar_producto"),
    path("producto/<int:producto_id>/eliminar/", views.eliminar_producto, name="eliminar_producto"),

    # CRUD Mesas
    path("mesas/", views.listar_mesas, name="listar_mesas"),
    path("mesas/crear/", views.crear_mesa, name="crear_mesa"),
    path("mesas/<int:mesa_id>/borrar/", views.borrar_mesa, name="borrar_mesa"),
]
