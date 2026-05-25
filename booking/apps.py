"""
Конфигурация приложения booking.
Здесь могут подключаться сигналы при запуске приложения (метод ready).
"""
from django.apps import AppConfig


class BookingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'booking'

    def ready(self):
        pass

