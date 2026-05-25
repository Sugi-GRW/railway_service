import threading
import time

_thread_locals = threading.local()

# Throttle: run background checks at most once per minute
_last_check = 0
_check_lock = threading.Lock()


def get_current_user():
    return getattr(_thread_locals, 'user', None)


def _get_now_msk():
    """Возвращает текущее московское время (UTC+3), соответствующее формату хранения в базе данных."""
    from datetime import datetime, timezone, timedelta
    MSK = timezone(timedelta(hours=3))
    return datetime.now(MSK).replace(tzinfo=None)


def _complete_past_tickets():
    """Отмечает билеты как 'Выполнен', если время прибытия рейса уже прошло."""
    try:
        from .models import Tickets, TicketStatus, RouteStops
        now_msk = _get_now_msk()

        confirmed = Tickets.objects.filter(
            status_of_ticket=TicketStatus.CONFIRMED
        ).select_related('trip', 'end_station')

        to_complete = []
        for ticket in confirmed:
            if not ticket.trip or not ticket.trip.departure_time or not ticket.end_station:
                continue
            dep = ticket.trip.departure_time
            if hasattr(dep, 'tzinfo') and dep.tzinfo is not None:
                dep = dep.replace(tzinfo=None)
            stop = RouteStops.objects.filter(
                route_id=ticket.trip.route_id,
                station=ticket.end_station
            ).first()
            if stop and stop.time_from_start:
                arrival_dt = dep + stop.time_from_start
                if arrival_dt < now_msk:
                    to_complete.append(ticket.pk)

        if to_complete:
            Tickets.objects.filter(pk__in=to_complete).update(
                status_of_ticket=TicketStatus.COMPLETED
            )
    except Exception:
        pass


def _process_auto_upgrades():
    """
    Для подтвержденных билетов с auto_upgrade=True: повышает класс обслуживания
    на один уровень вверх ровно за 1 час до отправления поезда.

    - Если следующий по иерархии класс отсутствует в поезде, ищет следующий доступный
      (но выполняется только ОДИН апгрейд на билет).
    - Обрабатывает билеты в порядке убывания класса (СВ первыми), чтобы пассажиры
      с более высоким классом имели приоритет на свободные места.
    """
    try:
        from .models import (
            Tickets, TicketStatus, TrainComp, SeatLayouts, SeatTypes, WagonClassID
        )
        now_msk = _get_now_msk()

        # Полная иерархия классов (от низшего к высшему)
        CLASS_HIERARCHY = [
            WagonClassID.SITTING,      # 1 - Сидячий
            WagonClassID.ECONOMY,      # 2 - Плацкарт
            WagonClassID.COMPARTMENT,  # 3 - Купе
            WagonClassID.SV,           # 4 - СВ
            WagonClassID.FIRST,        # 5 - Первый
        ]

        # Получаем всех кандидатов на апгрейд за один запрос
        candidates = list(Tickets.objects.filter(
            status_of_ticket=TicketStatus.CONFIRMED,
            auto_upgrade=True,
        ).select_related('trip', 'start_station', 'end_station', 'doc__user', 'seat_spec'))

        # Сортировка по текущему классу по убыванию (высший класс имеет приоритет)
        # Нам нужен класс вагона — кэшируем его
        ticket_class_cache = {}
        for ticket in candidates:
            if not ticket.trip:
                ticket_class_cache[ticket.pk] = None
                continue
            try:
                tc = TrainComp.objects.get(trip=ticket.trip, wagon_num=ticket.wagon)
                ticket_class_cache[ticket.pk] = tc.class_field_id
            except TrainComp.DoesNotExist:
                ticket_class_cache[ticket.pk] = None

        # Сортируем: сначала высокие классы, чтобы они получили приоритет
        def class_sort_key(t):
            cid = ticket_class_cache.get(t.pk)
            try:
                return -CLASS_HIERARCHY.index(cid)
            except (ValueError, TypeError):
                return 0

        candidates.sort(key=class_sort_key)

        from collections import defaultdict
        groups = defaultdict(list)
        
        for ticket in candidates:
            if not ticket.trip or not ticket.trip.departure_time:
                continue

            dep = ticket.trip.departure_time
            if hasattr(dep, 'tzinfo') and dep.tzinfo is not None:
                dep = dep.replace(tzinfo=None)

            # Временное окно для апгрейда: за 55–65 минут до отправления (в среднем за 1 час)
            minutes_to_dep = (dep - now_msk).total_seconds() / 60
            if not (55 <= minutes_to_dep <= 65):
                continue

            current_class_id = ticket_class_cache.get(ticket.pk)
            if current_class_id is None:
                continue
                
            groups[(ticket.trip_id, current_class_id)].append(ticket)

        # Кэшируем доступные классы для каждого рейса
        trip_available_classes = {}

        for (trip_id, current_class_id), group_tickets in groups.items():
            if trip_id not in trip_available_classes:
                trip_available_classes[trip_id] = set(
                    TrainComp.objects.filter(trip_id=trip_id)
                    .values_list('class_field_id', flat=True)
                )
            available = trip_available_classes[trip_id]

            # Ищем следующий класс, который реально есть в данном поезде
            try:
                current_idx = CLASS_HIERARCHY.index(current_class_id)
            except ValueError:
                continue

            next_class_id = None
            for cls in CLASS_HIERARCHY[current_idx + 1:]:
                if cls in available:
                    next_class_id = cls
                    break

            if next_class_id is None:
                continue

            # Считаем свободные места в next_class_id для этого рейса
            next_wagons = list(TrainComp.objects.filter(
                trip_id=trip_id,
                class_field_id=next_class_id
            ).order_by('wagon_num'))

            free_seats_pool = []
            
            for wagon in next_wagons:
                all_seats = list(SeatLayouts.objects.filter(
                    class_field_id=next_class_id
                ).values_list('seat_num', 'seat_type_id'))

                occupied = set(
                    Tickets.objects.filter(
                        trip_id=trip_id,
                        wagon=wagon.wagon_num,
                    ).exclude(
                        status_of_ticket=TicketStatus.CANCELLED
                    ).values_list('seat', flat=True)
                )

                for seat_num, seat_type_id in all_seats:
                    if seat_num not in occupied:
                        free_seats_pool.append({
                            'wagon': wagon,
                            'seat_num': seat_num,
                            'seat_type_id': seat_type_id
                        })

            if len(group_tickets) > len(free_seats_pool):
                # Если претендентов больше, чем свободных мест, никого не переводим
                continue

            # Выполняем апгрейд
            freed_old_seats = []  # (old_wagon, old_seat) до изменения
            for i, ticket in enumerate(group_tickets):
                # Запоминаем старое место до апгрейда для уведомлений
                freed_old_seats.append((ticket.wagon, ticket.seat, ticket))

                free_seat_info = free_seats_pool[i]
                ticket.wagon = free_seat_info['wagon'].wagon_num
                ticket.seat = free_seat_info['seat_num']

                try:
                    new_seat_spec = SeatTypes.objects.get(id=free_seat_info['seat_type_id'])
                except Exception:
                    new_seat_spec = ticket.seat_spec

                ticket.seat_spec = new_seat_spec
                ticket.auto_upgrade = False  # Только один апгрейд за раз
                ticket.save()

                ticket_class_cache[ticket.pk] = next_class_id
                try:
                    from .email_utils import send_upgrade_email
                    send_upgrade_email(ticket)
                except Exception as e:
                    print(f"[AutoUpgrade] Email error: {e}")

            # Уведомляем подписчиков об освободившихся местах —
            # одно письмо на вагон (группируем освободившиеся старые места по вагону)
            from collections import defaultdict as _dd
            by_wagon = _dd(list)
            for old_wagon, old_seat, ticket in freed_old_seats:
                by_wagon[old_wagon].append((old_seat, ticket))

            try:
                from .email_utils import send_seat_available_email
                for old_wagon_num, seat_ticket_pairs in by_wagon.items():
                    # Берём любой билет из группы для получения данных рейса
                    representative_ticket = seat_ticket_pairs[0][1]
                    # Временно подменяем wagon/seat на старое значение для формирования письма
                    import copy
                    fake_ticket = copy.copy(representative_ticket)
                    fake_ticket.wagon = old_wagon_num
                    fake_ticket.seat = seat_ticket_pairs[0][0]
                    send_seat_available_email(fake_ticket)
            except Exception as e:
                print(f"[AutoUpgrade] Seat notification error: {e}")

    except Exception as e:
        print(f"[AutoUpgrade] Error: {e}")




class CurrentUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        global _last_check

        _thread_locals.user = getattr(request, 'user', None)

        # Запускаем фоновые проверки не чаще чем раз в 60 секунд
        now_ts = time.time()
        if now_ts - _last_check > 60:
            with _check_lock:
                if now_ts - _last_check > 60:
                    _last_check = now_ts
                    _complete_past_tickets()
                    _process_auto_upgrades()

        response = self.get_response(request)
        _thread_locals.user = None
        return response
