from django.db import models


class Location(models.Model):
    address = models.CharField(max_length=200, verbose_name="Адрес", unique=True, db_index=True)
    lon = models.FloatField(verbose_name="Долгота", null=True, blank=True)
    lat = models.FloatField(verbose_name="Широта", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")


    class Meta:
        verbose_name = "Координаты адреса"
        verbose_name_plural = "Координаты адресов"

    def __str__(self):
        return f"{self.address}:({self.lon}, {self.lat})" if self.lon else self.address

