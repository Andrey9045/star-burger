import os
from collections import defaultdict
from django import forms
from django.db.models import Sum, ExpressionWrapper, DecimalField, F, Prefetch
from django.shortcuts import redirect, render 
from django.views import View
from django.urls import reverse_lazy
from django.contrib.auth.decorators import user_passes_test
import requests
from geopy import distance

from django.contrib.auth import authenticate, login
from django.contrib.auth import views as auth_views


from foodcartapp.models import Product, Restaurant, Order, RestaurantMenuItem, OrderItem
from geocoder.models import Location
from dotenv import load_dotenv 

load_dotenv()

class Login(forms.Form):
    username = forms.CharField(
        label='Логин', max_length=75, required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Укажите имя пользователя'
        })
    )
    password = forms.CharField(
        label='Пароль', max_length=75, required=True,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите пароль'
        })
    )


class LoginView(View):
    def get(self, request, *args, **kwargs):
        form = Login()
        return render(request, "login.html", context={
            'form': form
        })

    def post(self, request):
        form = Login(request.POST)

        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']

            user = authenticate(request, username=username, password=password)
            if user:
                login(request, user)
                if user.is_staff:  # FIXME replace with specific permission
                    return redirect("restaurateur:RestaurantView")
                return redirect("start_page")

        return render(request, "login.html", context={
            'form': form,
            'ivalid': True,
        })


class LogoutView(auth_views.LogoutView):
    next_page = reverse_lazy('restaurateur:login')


def is_manager(user):
    return user.is_staff  # FIXME replace with specific permission


def fetch_coordinates(address):
    if not address:
        return None
    try:
        location = Location.objects.get(address=address)
        if location.lon is not None and location.lat is not None:
            return(location.lon, location.lat)
    except Location.DoesNotExist:
        pass
    try:
        base_url = "https://geocode-maps.yandex.ru/1.x"
        response = requests.get(base_url, params={
            "geocode":address,
            "apikey":os.environ['YANDEX_GEOCODER_API_KEY'],
            "format":"json"})
        response.raise_for_status()
        found_places = response.json()['response']['GeoObjectCollection']['featureMember']
        if not found_places:
            Location.objects.update_or_create(
                address=address,
                defaults={'lon' : None, 'lat' : None})
            return None

        most_relevant = found_places[0]
        lon, lat = map(float, most_relevant['GeoObject']['Point']['pos'].split(" "))

        Location.objects.update_or_create(
            address=address,
            defaults={'lon': lon, 'lat': lat})
        return (lon, lat)

    except Exception:
        return None

@user_passes_test(is_manager, login_url='restaurateur:login')
def view_products(request):
    restaurants = list(Restaurant.objects.order_by('name'))
    products = list(Product.objects.prefetch_related('menu_items'))

    products_with_restaurant_availability = []
    for product in products:
        availability = {item.restaurant_id: item.availability for item in product.menu_items.all()}
        ordered_availability = [availability.get(restaurant.id, False) for restaurant in restaurants]

        products_with_restaurant_availability.append(
            (product, ordered_availability)
        )

    return render(request, template_name="products_list.html", context={
        'products_with_restaurant_availability': products_with_restaurant_availability,
        'restaurants': restaurants,
    })


@user_passes_test(is_manager, login_url='restaurateur:login')
def view_restaurants(request):
    return render(request, template_name="restaurants_list.html", context={
        'restaurants': Restaurant.objects.all(),
    })


@user_passes_test(is_manager, login_url='restaurateur:login')
def view_orders(request):
    orders = Order.objects.exclude(status=Order.Status.COMPLETED).prefetch_related(
        Prefetch('items', queryset=OrderItem.objects.select_related('product').only(
            'id', 
            'product_id', 
            'quantity', 
            'price'
        ))).annotate(
        total_price=Sum(
            ExpressionWrapper(
                F('items__quantity')*F('items__price'), 
                output_field=DecimalField(max_digits=7, decimal_places=2)
            )
        )
    )

    all_menu_items = RestaurantMenuItem.objects.select_related('restaurant', 'product').filter(availability=True)
    product_to_restourant = defaultdict(set)

    for item in all_menu_items:
        product_to_restourant[item.product_id].add(item.restaurant_id)

    all_restaurant_ids = set()
    order_restaurant_map = {}

    for order in orders:
        product_ids=set()
        for item in order.items.all():
            product_ids.add(item.product_id)
        sets = [product_to_restourant[pid] for pid in product_ids if pid in product_to_restourant]
        if len(sets) != len(product_ids) or not sets :
            order_restaurant_map[order.id]=set()
            continue
        common_ids = set.intersection(*sets)
        order_restaurant_map[order.id]=common_ids
        all_restaurant_ids.update(common_ids)

    restaurant_cache={r.id:r for r in Restaurant.objects.filter(id__in=all_restaurant_ids)}
    
    for order in orders:
        common_ids = order_restaurant_map.get(order.id, set())
        suitable_restaurants = [restaurant_cache[rid] for rid in common_ids]
        order_coords = fetch_coordinates(order.address)
        if order_coords is None:
            order.suitable_restaurants = list(suitable_restaurants)
            for restaurant in order.suitable_restaurants:
                restaurant.distance = None 
            continue
        restaurants_with_distance = []
        for restaurant in suitable_restaurants:
            rest_coords = fetch_coordinates(restaurant.address)
            if rest_coords:
                dist = distance.distance((order_coords[1], order_coords[0]), (rest_coords[1], rest_coords[0])).km
                restaurant.distance = dist
                restaurants_with_distance.append(restaurant)
            else:
                restaurant.distance = None 
                restaurants_with_distance.append(restaurant)
        restaurants_with_distance.sort(key= lambda r: r.distance if r.distance is not None else float('inf'))
        order.suitable_restaurants = restaurants_with_distance
    return render(request, template_name='order_items.html', context={
        'order_items': orders,
    })
