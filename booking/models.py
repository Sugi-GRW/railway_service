"""
Модели данных Django для взаимодействия с базой PostgreSQL.
ВАЖНО: Большинство моделей имеют `managed = False`. Это означает, что Django
не управляет созданием и изменением этих таблиц (они создаются вручную через SQL скрипты).
"""

from django.db import models


class TicketStatus:
    """Константы для статусов билетов"""
    CONFIRMED = 'Подтвержден'
    CANCELLED = 'Отменен'
    COMPLETED = 'Выполнен'


class WagonClassID:
    """Идентификаторы классов вагонов, соответствующие базе данных"""
    SITTING = 1
    ECONOMY = 2    # Плацкарт
    COMPARTMENT = 3  # Купе
    SV = 4
    FIRST = 5


class FormatTypes(models.Model):
    """Типы формата оформления услуги"""
    format_name = models.CharField(max_length=50, blank=True, null=True)
    impact_desc = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'format_types'


class SeatTypes(models.Model):
    """Категории мест (Нижнее, Верхнее, Боковое и т.д.)"""
    type_name = models.CharField(max_length=50, blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'seat_types'


class CostCoef(models.Model):
    class_name = models.CharField(max_length=50, blank=True, null=True)
    coef = models.DecimalField(max_digits=3, decimal_places=1, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'cost_coef'


class Stations(models.Model):
    station_name = models.CharField(max_length=100, blank=True, null=True)
    region = models.TextField(blank=True, null=True)  # Тип этого поля определен автоматически.

    class Meta:
        managed = False
        db_table = 'stations'


class Users(models.Model):
    login = models.CharField(unique=True, max_length=50, blank=True, null=True)
    password = models.CharField(max_length=100, blank=True, null=True)
    fio = models.CharField(max_length=150, blank=True, null=True)
    gender = models.TextField(blank=True, null=True)  # Тип этого поля определен автоматически.
    birth_date = models.DateField(blank=True, null=True)
    email = models.CharField(max_length=100, blank=True, null=True)
    phone = models.BigIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'users'


class UserDocs(models.Model):
    user = models.ForeignKey(Users, models.DO_NOTHING, blank=True, null=True)
    doc_type = models.TextField(blank=True, null=True)  # Тип этого поля определен автоматически.
    doc_num = models.CharField(max_length=50, blank=True, null=True)
    issue_date = models.DateField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'user_docs'


class Trips(models.Model):
    id = models.IntegerField(primary_key=True)
    route_id = models.IntegerField(blank=True, null=True)
    train_num = models.CharField(max_length=20, blank=True, null=True)
    departure_time = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'trips'


class RouteStops(models.Model):
    route_id = models.IntegerField(blank=True, null=True)
    station = models.ForeignKey(Stations, models.DO_NOTHING, blank=True, null=True)
    arrival_track = models.IntegerField(blank=True, null=True)
    stop_order = models.IntegerField(blank=True, null=True)
    time_from_start = models.DurationField(blank=True, null=True)
    stop_duration_min = models.IntegerField(blank=True, null=True)
    price = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'route_stops'


class TrainComp(models.Model):
    trip = models.ForeignKey(Trips, models.DO_NOTHING, blank=True, null=True)
    wagon_num = models.IntegerField(blank=True, null=True)
    class_field = models.ForeignKey(CostCoef, models.DO_NOTHING, db_column='class_id', blank=True, null=True)  # Поле переименовано, так как 'class' является зарезервированным словом в Python.

    class Meta:
        managed = False
        db_table = 'train_comp'


class SeatLayouts(models.Model):
    class_field = models.ForeignKey(CostCoef, models.DO_NOTHING, db_column='class_id', blank=True, null=True)  # Поле переименовано, так как 'class' является зарезервированным словом в Python.
    seat_num = models.IntegerField(blank=True, null=True)
    shelf_type = models.TextField(blank=True, null=True)  # Тип этого поля определен автоматически.
    seat_type = models.ForeignKey(SeatTypes, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'seat_layouts'


class ExtraServices(models.Model):
    service_name = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    format = models.ForeignKey(FormatTypes, models.DO_NOTHING, blank=True, null=True)
    price = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'extra_services'


class Tickets(models.Model):
    doc = models.ForeignKey(UserDocs, models.DO_NOTHING, blank=True, null=True)
    trip = models.ForeignKey(Trips, models.DO_NOTHING, blank=True, null=True)
    wagon = models.IntegerField(blank=True, null=True)
    seat = models.IntegerField(blank=True, null=True)
    start_station = models.ForeignKey(Stations, models.DO_NOTHING, blank=True, null=True)
    end_station = models.ForeignKey(Stations, models.DO_NOTHING, related_name='tickets_end_station_set', blank=True, null=True)
    seat_spec = models.ForeignKey(SeatTypes, models.DO_NOTHING, blank=True, null=True)
    auto_upgrade = models.BooleanField(blank=True, null=True)
    status_of_ticket = models.TextField(blank=True, null=True)  # Тип этого поля определен автоматически.
    price = models.IntegerField(blank=True, null=True)
    extra_price = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'tickets'


class BookedServices(models.Model):
    ticket = models.ForeignKey(Tickets, models.DO_NOTHING, blank=True, null=True)
    service = models.ForeignKey(ExtraServices, models.DO_NOTHING, blank=True, null=True)
    booking_time = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'booked_services'


class Notifications(models.Model):
    user = models.ForeignKey(Users, models.DO_NOTHING, blank=True, null=True)
    route_id = models.IntegerField(blank=True, null=True)
    wagon_num = models.IntegerField(blank=True, null=True)
    trip = models.ForeignKey(Trips, models.DO_NOTHING, blank=True, null=True)
    departure_point = models.ForeignKey(Stations, models.DO_NOTHING, blank=True, null=True)
    arrival_point = models.ForeignKey(Stations, models.DO_NOTHING, related_name='notifications_arrival_point_set', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'notifications'
