import os
from collections import defaultdict

from django import forms
from django.conf import settings
from django.contrib.auth import authenticate, login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Sum, ExpressionWrapper, DecimalField, F, Prefetch
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views import View
from geopy import distance

from foodcartapp.models import Product, Restaurant, Order, RestaurantMenuItem, OrderItem
from geocoder.models import Location
from geocoder.services import fetch_coordinates


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

def get_product_to_restaurant():
    all_menu_items = RestaurantMenuItem.objects.select_related(
        'restaurant', 'product'
    ).filter(availability=True)
    product_to_restourant = defaultdict(set)
    for item in all_menu_items:
        product_to_restourant[item.product_id].add(item.restaurant_id)
    return product_to_restourant

def get_orders_addres_coords(order_address):
    return  {
               loc.address:(loc.lon, loc.lat) 
               for loc in Location.objects.filter(address__in=order_address)
            }

def build_order_restaurant_map(orders, product_to_restourant):
    all_restaurant_ids = set()
    order_restaurant_map = {}
    for order in orders:
        common_ids = get_common_ids(order, product_to_restourant, order_restaurant_map)
        if not common_ids:
            continue
        order_restaurant_map[order.id]=common_ids
        all_restaurant_ids.update(common_ids)
    return order_restaurant_map, all_restaurant_ids

def get_common_ids(order, product_to_restourant, order_restaurant_map):
    product_ids = set()
    for item in order.items.all():
        product_ids.add(item.product_id)
    sets = [
        product_to_restourant[pid] 
        for pid in product_ids 
        if pid in product_to_restourant
    ]
    if len(sets) != len(product_ids) or not sets:
        order_restaurant_map[order.id]=set()
        return

    common_ids = set.intersection(*sets)
    return common_ids

def load_restaurants_with_coords(all_restaurant_ids):
    restaurant_cache = {
        r.id:r 
        for r in Restaurant.objects.filter(id__in=all_restaurant_ids)
    }
    restaurant_addresses = {r.address for r in restaurant_cache.values() if r.address}
    restaurant_coords = {
        loc.address:(loc.lon, loc.lat) 
        for loc in Location.objects.filter(address__in=restaurant_addresses) 
        if loc.lon is not None and loc.lat is not None
    }
    return restaurant_cache, restaurant_coords

def get_order_coords(order, all_orders_addresses):
    if order.address not in all_orders_addresses:
        address_info = fetch_coordinates(order.address)
        all_orders_addresses.update(address_info)
    order_coords = all_orders_addresses.get(order.address)
    return order_coords

def update_restaurants_with_distance(restaurants_with_distance, suitable_restaurants,restaurant_coords, order_coords):
    for restaurant in suitable_restaurants:
        if restaurant.address not in restaurant_coords:
            coords_info = fetch_coordinates(restaurant.address)
            restaurant_coords.update(coords_info)
        rest_coords = restaurant_coords.get(restaurant.address)
        if rest_coords:
            dist = distance.distance(
                (order_coords[1], order_coords[0]), 
                (rest_coords[1], rest_coords[0]) 
            ).km
            if dist > 100:
                continue
            restaurants_with_distance.append((restaurant, dist))
        else:
            dist = None
            restaurants_with_distance.append((restaurant, dist))
    restaurants_with_distance.sort(
        key=lambda r: r[1] if r[1] is not None else float('inf')
    )

def annotate_suitable_restaurants_with_restaurants_with_distance(orders, order_restaurant_map, restaurant_cache, all_orders_addresses, restaurant_coords):
    for order in orders:
        restaurants_with_distance = []
        common_ids = order_restaurant_map.get(order.id, set())
        suitable_restaurants = [restaurant_cache[rid] for rid in common_ids]
        order_coords = get_order_coords(order, all_orders_addresses)
        if order_coords is None:
            restaurants_with_distance = [(restaurant, None) for restaurant in suitable_restaurants]
            continue
        update_restaurants_with_distance(restaurants_with_distance, suitable_restaurants,restaurant_coords, order_coords)
        order.suitable_restaurants = restaurants_with_distance

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
    orders = Order.objects.exclude_completed().with_total_price()
    order_address = orders.values_list('address', flat=True).distinct()
    all_orders_addresses = get_orders_addres_coords(order_address)
    product_to_restourant = get_product_to_restaurant()
    order_restaurant_map, all_restaurant_ids = build_order_restaurant_map(orders, product_to_restourant)
    restaurant_cache, restaurant_coords = load_restaurants_with_coords(all_restaurant_ids)
    annotate_suitable_restaurants_with_restaurants_with_distance(
        orders, 
        order_restaurant_map, 
        restaurant_cache, 
        all_orders_addresses, 
        restaurant_coords
    )
    return render(request, template_name='order_items.html', context={
        'order_items': orders,
    })
