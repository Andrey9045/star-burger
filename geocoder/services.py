import requests
from requests.exceptions import RequestException
from django.conf import settings
from .models import Location


def fetch_coordinates(address):
    if not address:
        return None
    location = Location.objects.filter(address=address).first()
    if location and location.lon is not None and location.lat is not None:
        return {address: (location.lon, location.lat)}  # не обновляем!
    try:
        base_url = "https://geocode-maps.yandex.ru/1.x"
        response = requests.get(base_url, params={
            "geocode":address,
            "apikey":settings.YANDEX_GEOCODER_API_KEY,
            "format":"json"})
        response.raise_for_status()
    except RequestException:
        return {address:None}
    try:
        found_places = response.json()['response']['GeoObjectCollection']['featureMember']
    except (KeyError, ValueError) as e:
        print(f"Ошибка парсинга ответа для адреса {address}: {e}")
        return {address: None}
    if not found_places:
        Location.objects.update_or_create(
            address=address,
            defaults={'lon' : None, 'lat' : None})
        return {address : None}
    try:
        most_relevant = found_places[0]
        lon, lat = map(float, most_relevant['GeoObject']['Point']['pos'].split(" "))
    except (IndexError, KeyError, ValueError) as e:
        print(f"Ошибка извлечения координат для адреса {address}: {e}")
        return {address: None}
    Location.objects.update_or_create(
        address=address,
        defaults={'lon': lon, 'lat': lat}
    )
    address_info = {address: (lon, lat)}
    return address_info
