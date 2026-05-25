"""
Конфигурация панели администратора Django.
Здесь регистрируются модели, чтобы ими можно было управлять через веб-интерфейс /admin/.
"""
from django.contrib import admin
from .models import (
    FormatTypes, SeatTypes, CostCoef, Stations, Users, UserDocs,
    Trips, RouteStops, TrainComp, SeatLayouts, ExtraServices,
    Tickets, BookedServices, Notifications
)
from django.urls import path
from django.shortcuts import render, redirect
from django.db.models import Max
from django.utils import timezone
import datetime

@admin.register(Users)
class UsersAdmin(admin.ModelAdmin):
    list_display = ('id', 'login', 'fio', 'gender', 'email')
    search_fields = ('login', 'fio')

@admin.register(Stations)
class StationsAdmin(admin.ModelAdmin):
    list_display = ('id', 'station_name', 'region')
    search_fields = ('station_name', 'region')

@admin.register(Trips)
class TripsAdmin(admin.ModelAdmin):
    list_display = ('id', 'train_num', 'departure_time')
    search_fields = ('train_num',)
    change_list_template = "admin/trips_changelist.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('generate-trip/', self.admin_site.admin_view(self.generate_trip_view), name='generate-trip'),
        ]
        return custom_urls + urls

    def generate_trip_view(self, request):
        if request.method == 'POST':
            train_num = request.POST.get('train_num')
            route_id = request.POST.get('route_id')
            dep_date = request.POST.get('dep_date')
            dep_time = request.POST.get('dep_time')
            wagons = request.POST.get('wagons')
            
            try:
                dep_date_str = request.POST.get('dep_date')  # DD.MM.YYYY (из JS-виджета)
                dep_time_str = request.POST.get('dep_time')  # HH:MM:SS или HH:MM
                dt_str = f"{dep_date_str} {dep_time_str}"
                # Пробуем оба формата: с секундами и без
                for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M"):
                    try:
                        departure_time = datetime.datetime.strptime(dt_str, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    raise ValueError(f"Неверный формат даты/времени: '{dt_str}'")
                
                max_id = Trips.objects.aggregate(Max('id'))['id__max'] or 0
                new_trip_id = max_id + 1
                
                trip = Trips.objects.create(
                    id=new_trip_id,
                    route_id=route_id,
                    train_num=train_num,
                    departure_time=departure_time
                )
                
                wagon_num = 1
                for char in wagons:
                    if char.isdigit():
                        class_id = int(char)
                        TrainComp.objects.create(
                            trip=trip,
                            wagon_num=wagon_num,
                            class_field_id=class_id
                        )
                        wagon_num += 1
                
                self.message_user(request, f"Рейс {train_num} успешно сгенерирован!")
                return redirect('..')
            except Exception as e:
                self.message_user(request, f"Ошибка при генерации: {e}", level='error')
        
        return render(request, 'admin/generate_trip.html', context={'opts': self.model._meta})

@admin.register(Tickets)
class TicketsAdmin(admin.ModelAdmin):
    list_display = ('id', 'trip', 'wagon', 'seat', 'status_of_ticket')

admin.site.register(FormatTypes)
admin.site.register(SeatTypes)
admin.site.register(CostCoef)
admin.site.register(UserDocs)
admin.site.register(RouteStops)
admin.site.register(TrainComp)
admin.site.register(SeatLayouts)
admin.site.register(ExtraServices)
admin.site.register(BookedServices)
admin.site.register(Notifications)
