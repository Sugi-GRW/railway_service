from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from urllib.parse import quote


def build_qr_data(ticket):
    """Собирает строку с данными билета для QR-кода (такой же формат, как в личном кабинете)."""
    user = ticket.doc.user if ticket.doc and ticket.doc.user else None
    fio = user.fio if user else '—'
    gender = user.gender if user else '—'
    birth_date = user.birth_date.strftime('%d.%m.%Y') if user and user.birth_date else '—'

    doc_type = ticket.doc.doc_type if ticket.doc else '—'
    doc_num = ticket.doc.doc_num if ticket.doc else '—'
    issue_date = ticket.doc.issue_date.strftime('%d.%m.%Y') if ticket.doc and ticket.doc.issue_date else '—'

    dep_time = ticket.trip.departure_time.strftime('%d.%m.%Y %H:%M') if ticket.trip and ticket.trip.departure_time else '—'
    from_station = ticket.start_station.station_name if ticket.start_station else '—'
    to_station = ticket.end_station.station_name if ticket.end_station else '—'
    wagon_class = ticket.seat_spec.type_name if ticket.seat_spec else '—'

    lines = [
        f"Билет: {ticket.trip.train_num if ticket.trip else '—'}",
        f"Маршрут: {from_station} - {to_station}",
        f"Отправление: {dep_time}",
        f"Вагон: {ticket.wagon}, Место: {ticket.seat} ({wagon_class})",
        f"Пассажир: {fio}, {gender}, {birth_date}",
        f"Документ: {doc_type} {doc_num} от {issue_date}",
        f"Статус: {ticket.status_of_ticket}",
    ]
    return "\n".join(lines)


def send_ticket_action_email(ticket, action='Покупка', added_services=None):
    """Отправляет красивое HTML-письмо с билетом пользователю (о покупке или возврате)."""
    try:
        from django.template.loader import render_to_string
        from datetime import timedelta

        user = ticket.doc.user if ticket.doc and ticket.doc.user else None
        if not user or not user.email:
            return

        email_address = user.email
        train_num = ticket.trip.train_num if ticket.trip else '—'
        from_station = ticket.start_station.station_name if ticket.start_station else '—'
        to_station = ticket.end_station.station_name if ticket.end_station else '—'
        
        dep_dt = None
        arr_dt = None
        dep_track = 1
        arr_track = 1
        if ticket.trip and ticket.trip.departure_time:
            from .models import RouteStops
            # Время отправления с учетом конкретной станции
            start_stop = RouteStops.objects.filter(route_id=ticket.trip.route_id, station=ticket.start_station).first()
            if start_stop:
                dep_dt = ticket.trip.departure_time + (start_stop.time_from_start or timedelta())
                dep_track = start_stop.arrival_track or 1
                # Добавляем время стоянки, если это не начальная станция маршрута
                if start_stop.stop_duration_min:
                    dep_dt += timedelta(minutes=start_stop.stop_duration_min)
            else:
                dep_dt = ticket.trip.departure_time

            # Время прибытия на конкретную станцию
            end_stop = RouteStops.objects.filter(route_id=ticket.trip.route_id, station=ticket.end_station).first()
            if end_stop:
                arr_dt = ticket.trip.departure_time + (end_stop.time_from_start or timedelta())
                arr_track = end_stop.arrival_track or 1
            else:
                arr_dt = dep_dt + timedelta(hours=4, minutes=10) # Запасной вариант
                
        from_station_display = f"{from_station} ({dep_track} путь)"
        to_station_display = f"{to_station} ({arr_track} путь)"

        dep_date = dep_dt.strftime('%d.%m.%Y') if dep_dt else '—'
        dep_time = dep_dt.strftime('%H:%M') if dep_dt else '—'
        
        arr_date = arr_dt.strftime('%d.%m.%Y') if arr_dt else '—'
        arr_time = arr_dt.strftime('%H:%M') if arr_dt else '—'
        
        duration = ""
        if dep_dt and arr_dt:
            diff = arr_dt - dep_dt
            total_seconds = int(diff.total_seconds())
            days, remainder = divmod(total_seconds, 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, _ = divmod(remainder, 60)
            
            parts = []
            if days > 0: parts.append(f"{days} дн")
            if hours > 0: parts.append(f"{hours} ч")
            if minutes > 0: parts.append(f"{minutes} мин")
            duration = " ".join(parts) if parts else "0 мин"
                
        train_route = f"{from_station} - {to_station}"
        
        wagon_class = 'Неизвестно'
        wagon_class_id = None
        try:
            from .models import TrainComp, WagonClassID, SeatLayouts
            tc = TrainComp.objects.select_related('class_field').get(trip=ticket.trip, wagon_num=ticket.wagon)
            if tc.class_field:
                wagon_class = tc.class_field.class_name
                wagon_class_id = tc.class_field_id
        except Exception:
            pass
            
        seat_type = ticket.seat_spec.type_name if ticket.seat_spec else "Стандартное"
        seat_location = "Стандартное"
        
        if wagon_class_id and ticket.seat:
            from .models import SeatLayouts
            layout = SeatLayouts.objects.filter(class_field_id=wagon_class_id, seat_num=ticket.seat).first()
            if layout and layout.shelf_type:
                seat_location = layout.shelf_type
        
        action_title = "Покупка" if action == 'Покупка' else "Возврат"
        if action == 'ДопУслуги':
            action_title = "Оформление новых доп. услуг"
            
        services_title = ""
        services_list = []
        
        if action == 'Покупка':
            s_list = [bs.service.service_name for bs in ticket.bookedservices_set.all()]
            if s_list:
                services_title = "Оформленные доп. услуги"
                services_list = s_list
        elif action == 'ДопУслуги' and added_services:
            s_list = [s.service_name for s in added_services]
            if s_list:
                services_title = "Добавленные доп. услуги"
                services_list = s_list
        elif action == 'Возврат' and added_services:
            s_list = [s.service_name for s in added_services]
            if s_list:
                services_title = "Отмененные доп. услуги"
                services_list = s_list

        subject = f'{action_title} — Поезд {train_num}, {from_station} → {to_station}'

        site_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')
        profile_url = f"{site_url}/profile/#tickets"

        context = {
            'action_title': action_title,
            'services_title': services_title,
            'services_list': services_list,
            'train_num': train_num,
            'train_route': train_route,
            'wagon_num': ticket.wagon,
            'seat_num': ticket.seat if ticket.seat else '—',
            'wagon_class': wagon_class,
            'seat_location': seat_location,
            'seat_type': seat_type,
            'duration': duration,
            'dep_date': dep_date,
            'dep_time': dep_time,
            'from_station': from_station_display,
            'arr_date': arr_date,
            'arr_time': arr_time,
            'to_station': to_station_display,
            'profile_url': profile_url,
        }

        html_body = render_to_string('emails/ticket_notification.html', context)

        plain_body = (
            f"{action_title} билета\n\n"
            f"Поезд №{train_num}, вагон №{ticket.wagon}, место(а) {ticket.seat}\n"
            f"Маршрут: {from_station} - {to_station}\n"
            f"Отправление: {dep_date} в {dep_time}\n"
        )

        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[email_address],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=True)

    except Exception as e:
        print(f"[Email Error] Не удалось отправить письмо с билетом: {e}")


def send_seat_available_email(ticket):
    """
    Отправляет HTML-письмо всем пользователям, подписанным на уведомления
    о свободных местах в данном вагоне/маршруте, когда билет отменяется.
    """
    try:
        from .models import Notifications, Users, TrainComp, WagonClassID
        from django.template.loader import render_to_string

        if not ticket.trip:
            return

        route_id = ticket.trip.route_id
        wagon_num = ticket.wagon

        # Ищем все подписки на этот маршрут и номер вагона
        subscribers = Notifications.objects.filter(
            route_id=route_id,
            wagon_num=wagon_num,
        ).select_related('user', 'departure_point', 'arrival_point')

        if not subscribers.exists():
            return

        train_num = ticket.trip.train_num or '—'
        from_station = ticket.start_station.station_name if ticket.start_station else '—'
        to_station = ticket.end_station.station_name if ticket.end_station else '—'
        seat_num = ticket.seat or '—'

        # Вычисляем точные времена и пути из RouteStops (как в send_ticket_action_email)
        from datetime import timedelta
        dep_dt = arr_dt = None
        dep_track = arr_track = 1
        if ticket.trip and ticket.trip.departure_time:
            from .models import RouteStops
            start_stop = RouteStops.objects.filter(route_id=ticket.trip.route_id, station=ticket.start_station).first()
            if start_stop:
                dep_dt = ticket.trip.departure_time + (start_stop.time_from_start or timedelta())
                dep_track = start_stop.arrival_track or 1
                if start_stop.stop_duration_min:
                    dep_dt += timedelta(minutes=start_stop.stop_duration_min)
            else:
                dep_dt = ticket.trip.departure_time

            end_stop = RouteStops.objects.filter(route_id=ticket.trip.route_id, station=ticket.end_station).first()
            if end_stop:
                arr_dt = ticket.trip.departure_time + (end_stop.time_from_start or timedelta())
                arr_track = end_stop.arrival_track or 1
            else:
                arr_dt = dep_dt + timedelta(hours=4, minutes=10) if dep_dt else None

        dep_date = dep_dt.strftime('%d.%m.%Y') if dep_dt else '—'
        dep_time_str = dep_dt.strftime('%H:%M') if dep_dt else '—'
        arr_date = arr_dt.strftime('%d.%m.%Y') if arr_dt else '—'
        arr_time_str = arr_dt.strftime('%H:%M') if arr_dt else '—'

        duration = ''
        if dep_dt and arr_dt:
            diff = arr_dt - dep_dt
            total_seconds = int(diff.total_seconds())
            days, remainder = divmod(total_seconds, 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, _ = divmod(remainder, 60)
            parts = []
            if days > 0: parts.append(f'{days} дн')
            if hours > 0: parts.append(f'{hours} ч')
            if minutes > 0: parts.append(f'{minutes} мин')
            duration = ' '.join(parts) if parts else '0 мин'

        from_station_display = f'{from_station} ({dep_track} путь)'
        to_station_display = f'{to_station} ({arr_track} путь)'

        # Определяем параметры места
        wagon_class = 'Неизвестно'
        wagon_class_id = None
        try:
            from .models import TrainComp, WagonClassID, SeatLayouts
            tc = TrainComp.objects.select_related('class_field').get(trip=ticket.trip, wagon_num=ticket.wagon)
            if tc.class_field:
                wagon_class = tc.class_field.class_name
                wagon_class_id = tc.class_field_id
        except Exception:
            pass

        seat_type = ticket.seat_spec.type_name if ticket.seat_spec else 'Стандартное'
        seat_location = 'Стандартное'

        if wagon_class_id and ticket.seat:
            from .models import SeatLayouts
            layout = SeatLayouts.objects.filter(class_field_id=wagon_class_id, seat_num=ticket.seat).first()
            if layout and layout.shelf_type:
                seat_location = layout.shelf_type

        # Ссылка на выбор места
        site_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')
        buy_url = f'{site_url}/seats/{ticket.trip.id}/?wagon={wagon_num}&seat={seat_num}'

        canceler_user_id = ticket.doc.user.id if ticket.doc and ticket.doc.user else None

        for notif in subscribers:
            user = notif.user
            if not user or not user.email:
                continue

            # Не отправляем уведомление тому, кто сам же и вернул этот билет
            if canceler_user_id and user.id == canceler_user_id:
                continue

            # Проверка пола
            user_gender = (user.gender or '').lower()
            if 'жен' in seat_type.lower() and 'муж' in user_gender:
                continue
            if 'муж' in seat_type.lower() and 'жен' in user_gender:
                continue

            fio = user.fio or 'Пассажир'
            subject = f'Освободилось место — Поезд {train_num}, вагон {wagon_num}'
            unsubscribe_url = f'{site_url}/profile/notification/{notif.id}/delete/'

            context = {
                'fio': fio,
                'train_num': train_num,
                'wagon_num': wagon_num,
                'seat_num': seat_num,
                'wagon_class': wagon_class,
                'seat_location': seat_location,
                'seat_type': seat_type,
                'duration': duration,
                'dep_date': dep_date,
                'dep_time': dep_time_str,
                'from_station': from_station_display,
                'arr_date': arr_date,
                'arr_time': arr_time_str,
                'to_station': to_station_display,
                'buy_url': buy_url,
                'unsubscribe_url': unsubscribe_url,
            }

            html_body = render_to_string('emails/seat_available.html', context)

            plain_body = (
                f'Здравствуйте, {fio}!\n\n'
                f'Освободилось место в поезде {train_num}:\n'
                f'Маршрут: {from_station} → {to_station}\n'
                f'Отправление: {dep_date} в {dep_time_str}\n'
                f'Прибытие: {arr_date} в {arr_time_str}\n'
                f'Вагон: №{wagon_num} ({wagon_class})\n'
                f'Место: №{seat_num} ({seat_location}, {seat_type})\n\n'
                f'Перейти к выбору места: {buy_url}\n\n'
                f'Отписаться от уведомлений: {unsubscribe_url}\n'
            )


            try:
                msg = EmailMultiAlternatives(
                    subject=subject,
                    body=plain_body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[user.email],
                )
                msg.attach_alternative(html_body, "text/html")
                msg.send(fail_silently=True)
                print(f"[Email] Уведомление о свободном месте отправлено: {user.email}")
            except Exception as e:
                print(f"[Email Error] Не удалось отправить уведомление пользователю {user.email}: {e}")

    except Exception as e:
        print(f"[Email Error] Ошибка в send_seat_available_email: {e}")


def send_upgrade_email(ticket):
    """Отправляет HTML-письмо о повышении класса билета (автоапгрейд)."""
    try:
        from django.template.loader import render_to_string
        from datetime import timedelta

        user = ticket.doc.user if ticket.doc and ticket.doc.user else None
        if not user or not user.email:
            return

        train_num = ticket.trip.train_num if ticket.trip else '—'
        from_station = ticket.start_station.station_name if ticket.start_station else '—'
        to_station = ticket.end_station.station_name if ticket.end_station else '—'

        dep_dt = None
        arr_dt = None
        if ticket.trip and ticket.trip.departure_time:
            from .models import RouteStops
            start_stop = RouteStops.objects.filter(route_id=ticket.trip.route_id, station=ticket.start_station).first()
            if start_stop:
                dep_dt = ticket.trip.departure_time + (start_stop.time_from_start or timedelta())
                if start_stop.stop_duration_min:
                    dep_dt += timedelta(minutes=start_stop.stop_duration_min)
            else:
                dep_dt = ticket.trip.departure_time

            end_stop = RouteStops.objects.filter(route_id=ticket.trip.route_id, station=ticket.end_station).first()
            if end_stop:
                arr_dt = ticket.trip.departure_time + (end_stop.time_from_start or timedelta())
            else:
                arr_dt = dep_dt + timedelta(hours=4, minutes=10)

        dep_date = dep_dt.strftime('%d.%m.%Y') if dep_dt else '—'
        dep_time = dep_dt.strftime('%H:%M') if dep_dt else '—'

        arr_date = arr_dt.strftime('%d.%m.%Y') if arr_dt else '—'
        arr_time = arr_dt.strftime('%H:%M') if arr_dt else '—'

        wagon_class = 'Неизвестно'
        wagon_class_id = None
        try:
            from .models import TrainComp, SeatLayouts
            tc = TrainComp.objects.select_related('class_field').get(trip=ticket.trip, wagon_num=ticket.wagon)
            if tc.class_field:
                wagon_class = tc.class_field.class_name
                wagon_class_id = tc.class_field_id
        except Exception:
            pass

        seat_type = ticket.seat_spec.type_name if ticket.seat_spec else 'Стандартное'
        seat_location = 'Стандартное'
        if wagon_class_id and ticket.seat:
            from .models import SeatLayouts
            layout = SeatLayouts.objects.filter(class_field_id=wagon_class_id, seat_num=ticket.seat).first()
            if layout and layout.shelf_type:
                seat_location = layout.shelf_type

        subject = f'Повышение класса билета — Поезд {train_num}, {from_station} → {to_station}'
        site_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')
        profile_url = f"{site_url}/profile/#tickets"

        context = {
            'action_title': 'Повышение класса',
            'train_num': train_num,
            'train_route': f"{from_station} - {to_station}",
            'wagon_num': ticket.wagon,
            'seat_num': ticket.seat if ticket.seat else '—',
            'wagon_class': wagon_class,
            'seat_location': seat_location,
            'seat_type': seat_type,
            'duration': '',
            'dep_date': dep_date,
            'dep_time': dep_time,
            'from_station': from_station,
            'arr_date': arr_date,
            'arr_time': arr_time,
            'to_station': to_station,
            'profile_url': profile_url,
        }

        html_body = render_to_string('emails/ticket_notification.html', context)
        plain_body = (
            f"Повышение класса билета\n\n"
            f"Поезд №{train_num}, вагон №{ticket.wagon}, место(а) {ticket.seat}\n"
            f"Класс: {wagon_class}\n"
            f"Маршрут: {from_station} - {to_station}\n"
            f"Отправление: {dep_date} в {dep_time}\n"
        )

        from django.core.mail import EmailMultiAlternatives
        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=True)
        print(f"[Email] Уведомление об апгрейде отправлено: {user.email}")

    except Exception as e:
        print(f"[Email Error] Не удалось отправить письмо об апгрейде: {e}")
