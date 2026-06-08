from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("menu", "0026_venta_ventaitem"),
    ]

    operations = [
        migrations.AddField(
            model_name="pedidoitem",
            name="es_cortesia",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="ventaitem",
            name="descuento_cortesia",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name="ventaitem",
            name="es_cortesia",
            field=models.BooleanField(default=False),
        ),
    ]
