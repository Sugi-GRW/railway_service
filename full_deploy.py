import subprocess
import os
import sys

# Конфигурация
DB_NAME = "railway_db"
DB_USER = "postgres"
PSQL_PATH = r'C:\Program Files\PostgreSQL\18\bin\psql.exe'

# Загрузка пароля из .env
def load_password():
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                if line.startswith("DB_PASSWORD="):
                    return line.split("=")[1].strip()
    return os.getenv("PGPASSWORD")

os.environ['PGPASSWORD'] = load_password() or ""

if not os.environ['PGPASSWORD']:
    print("!!! ОШИБКА: Пароль БД не найден в .env и в PGPASSWORD. Импорт невозможен.")
    sys.exit(1)

def run_sql(file_path):
    print(f"\n>>> [SQL] Выполняю {file_path}...")
    try:
        subprocess.run([PSQL_PATH, "-U", DB_USER, "-d", DB_NAME, "-f", file_path], check=True)
        print(f"--- OK: {file_path}")
    except subprocess.CalledProcessError as e:
        print(f"!!! ОШИБКА в {file_path}: {e}")
        sys.exit(1)

def run_python(script_path):
    print(f"\n>>> [PY] Запускаю {script_path}...")
    try:
        python_exe = os.path.join("venv", "Scripts", "python.exe")
        subprocess.run([python_exe, script_path], check=True)
        print(f"--- OK: {script_path}")
    except subprocess.CalledProcessError as e:
        print(f"!!! ОШИБКА в {script_path}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("="*60)
    print("ПОЛНОЕ РАЗВЕРТЫВАНИЕ БАЗЫ ДАННЫХ (СХЕМА + МАРШРУТЫ + МЕСТА)")
    print("="*60)

    # 1. Структура и базовые настройки (с коэффициентами и пользователем)
    run_sql(os.path.join("database_setup", "SQL files", "schema.sql"))

    # 2. Загрузка основной базы маршрутов (80к строк)
    run_sql(os.path.join("database_setup", "SQL files", "parsed_data.sql"))

    # 3. Загрузка мест (seat_layouts)
    run_sql(os.path.join("database_setup", "SQL files", "insert_layouts.sql"))

    # 4. Добавление тестового рейса Москва - Санкт-Петербург
    run_sql(os.path.join("database_setup", "SQL files", "add_moscow_spb_trip.sql"))

    # 5. Финальная синхронизация ID
    run_python(os.path.join("database_setup", "fix_sequences.py"))

    print("\n" + "="*60)
    print("ВСЁ ГОТОВО! БАЗА ПОЛНОСТЬЮ ЗАПОЛНЕНА.")
    print("="*60)
