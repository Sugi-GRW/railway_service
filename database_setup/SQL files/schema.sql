-- 1. УДАЛЕНИЕ СУЩЕСТВУЮЩИХ ТАБЛИЦ И ТИПОВ
DROP TABLE IF EXISTS format_types CASCADE;
DROP TABLE IF EXISTS seat_types CASCADE;
DROP TABLE IF EXISTS cost_coef CASCADE;
DROP TABLE IF EXISTS stations CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS user_docs CASCADE;
DROP TABLE IF EXISTS trips CASCADE;
DROP TABLE IF EXISTS route_stops CASCADE;
DROP TABLE IF EXISTS train_comp CASCADE;
DROP TABLE IF EXISTS seat_layouts CASCADE;
DROP TABLE IF EXISTS extra_services CASCADE;
DROP TABLE IF EXISTS tickets CASCADE;
DROP TABLE IF EXISTS booked_services CASCADE;
DROP TABLE IF EXISTS notifications CASCADE;

DROP TYPE IF EXISTS region_enum CASCADE;
DROP TYPE IF EXISTS shelf_enum CASCADE;
DROP TYPE IF EXISTS gender_enum CASCADE;
DROP TYPE IF EXISTS doc_type_enum CASCADE;
DROP TYPE IF EXISTS ticket_status_enum CASCADE;

-- 2. СОЗДАНИЕ ТИПОВ ENUM
CREATE TYPE region_enum AS ENUM (
    'Москва', 
    'Тверская область', 
    'Санкт-Петербург', 
    'Рязанская область', 
    'Республика Татарстан'
);

CREATE TYPE shelf_enum AS ENUM ('Сидячие', 'Верхнее', 'Нижнее', 'Боковое верхнее', 'Боковое нижнее');
CREATE TYPE gender_enum AS ENUM ('Мужской', 'Женский');
CREATE TYPE doc_type_enum AS ENUM ('Паспорт РФ', 'Свидетельство о рождении', 'Заграничный паспорт', 'Иностранный документ');
CREATE TYPE ticket_status_enum AS ENUM ('Забронирован', 'Подтвержден', 'Выполнен', 'Отменен');

-- 3. СОЗДАНИЕ ТАБЛИЦ

CREATE TABLE format_types (
    id SERIAL PRIMARY KEY,
    format_name VARCHAR(50),
    impact_desc TEXT
);

CREATE TABLE seat_types (
    id SERIAL PRIMARY KEY,
    type_name VARCHAR(50),
    description TEXT
);

CREATE TABLE cost_coef (
    id SERIAL PRIMARY KEY,
    class_name VARCHAR(50),
    coef DECIMAL(3,1)
);

CREATE TABLE stations (
    id SERIAL PRIMARY KEY,
    station_name VARCHAR(100),
    region region_enum
);

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    login VARCHAR(50) UNIQUE,
    password VARCHAR(100),
    fio VARCHAR(150),
    gender gender_enum,
    birth_date DATE,
    email VARCHAR(100),
    phone BIGINT
);

CREATE TABLE user_docs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    doc_type doc_type_enum,
    doc_num VARCHAR(50),
    issue_date DATE
);

CREATE TABLE trips (
    id SERIAL PRIMARY KEY,
    route_id INTEGER,
    train_num VARCHAR(20),
    departure_time TIMESTAMP
);

CREATE TABLE route_stops (
    id SERIAL PRIMARY KEY,
    route_id INTEGER,
    station_id INTEGER REFERENCES stations(id),
    arrival_track INTEGER,
    stop_order INTEGER,
    time_from_start INTERVAL,
    stop_duration_min INTEGER,
    price INTEGER
);

CREATE TABLE train_comp (
    id SERIAL PRIMARY KEY,
    trip_id INTEGER REFERENCES trips(id),
    wagon_num INTEGER,
    class_id INTEGER REFERENCES cost_coef(id)
);

CREATE TABLE seat_layouts (
    id SERIAL PRIMARY KEY,
    class_id INTEGER REFERENCES cost_coef(id),
    seat_num INTEGER,
    shelf_type shelf_enum,
    seat_type_id INTEGER REFERENCES seat_types(id)
);

CREATE TABLE extra_services (
    id SERIAL PRIMARY KEY,
    service_name VARCHAR(100),
    description TEXT,
    format_id INTEGER REFERENCES format_types(id),
    price INTEGER
);

CREATE TABLE tickets (
    id SERIAL PRIMARY KEY,
    doc_id INTEGER REFERENCES user_docs(id),
    trip_id INTEGER REFERENCES trips(id),
    wagon INTEGER,
    seat INTEGER,
    start_station_id INTEGER REFERENCES stations(id),
    end_station_id INTEGER REFERENCES stations(id),
    seat_spec_id INTEGER REFERENCES seat_types(id),
    auto_upgrade BOOLEAN,
    status_of_ticket ticket_status_enum,
    price INTEGER,
    extra_price INTEGER
);

CREATE TABLE booked_services (
    id SERIAL PRIMARY KEY,
    ticket_id INTEGER REFERENCES tickets(id),
    service_id INTEGER REFERENCES extra_services(id),
    booking_time TIMESTAMP
);

CREATE TABLE notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    route_id INTEGER,
    trip_id INTEGER REFERENCES trips(id),
    wagon_num INTEGER,
    departure_point_id INT REFERENCES stations(id),
    arrival_point_id INT REFERENCES stations(id)
);


INSERT INTO cost_coef (id, class_name, coef) VALUES
(1, 'Сидячий', 0.7),
(2, 'Плацкарт', 1.0),
(3, 'Купе', 1.5),
(4, 'СВ', 5.0),
(5, 'Первый', 10.0);



INSERT INTO format_types (id, format_name, impact_desc) VALUES
(1, 'Динамическое добавление', 'Привязывается к заказу без изменения бланка'),
(2, 'Строгое оформление', 'Требует аннулирования и перевыпуска бланка');

INSERT INTO seat_types (id, type_name, description) VALUES
(1, 'Стандартное', 'Обычное место без ограничений'),
(2, 'Женское купе', 'Только для пассажиров женского пола'),
(3, 'Мужское купе', 'Только для пассажиров мужского пола'),
(4, 'С животными', 'Разрешен провоз питомцев');

INSERT INTO extra_services (id, service_name, description, format_id, price) VALUES
(1, 'Комплект белья', 'Стандартный комплект постельного белья', 1, 190),
(2, 'Легкий завтрак', 'Комплексное питание из 2-х блюд', 1, 300),
(3, 'Сытный обед', 'Комплексное питание из 3-х блюд', 1, 500),
(4, 'Горячий ужин', 'Комплексное питание из 3-х блюд', 1, 500),
(5, 'Провоз багажа', 'Сверхнормативный багаж до 30 кг', 2, 1200),
(6, 'Страхование НС', 'Страховка от несчастных случаев', 2, 150),
(7, 'Доступ в бизнес-зал', 'Ожидание поезда', 1, 2500);

INSERT INTO users (id, login, password, fio, gender, birth_date, email, phone) VALUES 
(1, 'ivanov_a', '2b12$eIm1', 'Иванов Андрей Ильич', 'Мужской', '1985-04-12', 'ivan@mail.ru', 79001112233);

INSERT INTO user_docs (id, user_id, doc_type, doc_num, issue_date) VALUES 
(1, 1, 'Паспорт РФ', '4510123456', '2025-04-13');
