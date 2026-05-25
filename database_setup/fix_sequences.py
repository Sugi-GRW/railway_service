import sys
import os
import django

# Добавляем корень проекта в путь
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection

tables = ['users', 'stations', 'booked_services', 'tickets', 'user_docs', 'extra_services', 'notifications', 'train_comp', 'seat_layouts']

with connection.cursor() as cursor:
    for table in tables:
        try:
            print(f"Исправление последовательности для таблицы {table}...")
            # PostgreSQL команда для синхронизации с максимальным id
            cursor.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE(MAX(id), 0) + 1, false) FROM {table};")
            new_val = cursor.fetchone()
            print(f"Новое значение последовательности для {table}: {new_val}")
        except Exception as e:
            print(f"Ошибка при исправлении {table}: {e}")
