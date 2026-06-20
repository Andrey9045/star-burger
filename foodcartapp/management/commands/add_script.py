import json
from django.core.management.base import BaseCommand
from foodcartapp.models import Restaurant, Product

class Command(BaseCommand):
    help = 'Загружает рестораны и продукты из JSON файлов (restaurants.json, products.json)'

    def handle(self, *args, **options):
        # Загрузка ресторанов
        try:
            with open('restaurants.json', 'r', encoding='utf-8') as f:
                restaurants_data = json.load(f)
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR('Файл restaurants.json не найден в корне проекта'))
            return

        for item in restaurants_data:
            Restaurant.objects.create(
                name=item.get('title'),
                address=item.get('address'),
                contact_phone=item.get('contact_phone')
            )
        self.stdout.write(self.style.SUCCESS(f'✅ Добавлено ресторанов: {len(restaurants_data)}'))

        # Загрузка продуктов
        try:
            with open('products.json', 'r', encoding='utf-8') as f:
                products_data = json.load(f)
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR('Файл products.json не найден в корне проекта'))
            return

        for item in products_data:
            Product.objects.create(
                name=item.get('title'),
                category=item.get('type'),
                price=item.get('price'),
                image=item.get('img'),
                description=item.get('description')
            )
        self.stdout.write(self.style.SUCCESS(f'✅ Добавлено продуктов: {len(products_data)}'))
    )
