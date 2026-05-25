from django.shortcuts import render, redirect
from django.contrib import messages
from .models import Users, Stations, Trips, RouteStops, TrainComp, Tickets, UserDocs, SeatLayouts, Notifications, ExtraServices, BookedServices, TicketStatus, WagonClassID
from datetime import datetime, timedelta

def search_view(request):
    """
    Представление для поиска рейсов (билетов).
    Принимает параметры 'from' (откуда), 'to' (куда) и 'date' (дата).
    Ищет станции, проверяет наличие маршрута между ними и рассчитывает актуальное время
    отправления, прибытия и базовую стоимость проезда.
    """
    from_query = request.GET.get('from', '')
    to_query = request.GET.get('to', '')
    date_query = request.GET.get('date', '')
    
    results = []
    
    if from_query and to_query and date_query:
        from django.db.models import Q
        start_stations = Stations.objects.filter(Q(station_name__icontains=from_query) | Q(region__icontains=from_query))
        end_stations = Stations.objects.filter(Q(station_name__icontains=to_query) | Q(region__icontains=to_query))
        
        start_ids = list(start_stations.values_list('id', flat=True))
        end_ids = list(end_stations.values_list('id', flat=True))
        
        rs_starts = RouteStops.objects.filter(station_id__in=start_ids)
        rs_ends = RouteStops.objects.filter(station_id__in=end_ids)
        
        valid_routes = []
        for rs_start in rs_starts:
            for rs_end in rs_ends:
                # Маршрут валиден, если станция прибытия находится позже станции отправления
                if rs_start.route_id == rs_end.route_id and rs_start.stop_order < rs_end.stop_order:
                    valid_routes.append({
                        'route_id': rs_start.route_id,
                        'start_stop': rs_start,
                        'end_stop': rs_end
                    })
                    
        try:
            # Ожидаем дату в формате YYYY-MM-DD
            search_date = datetime.strptime(date_query, '%Y-%m-%d').date()
            
            for r in valid_routes:
                trips = Trips.objects.filter(route_id=r['route_id'])
                for trip in trips:
                    start_stop = r['start_stop']
                    end_stop = r['end_stop']
                    
                    # Задержка отправления: время от старта маршрута + время стоянки
                    depart_delay = start_stop.time_from_start or timedelta()
                    if start_stop.stop_duration_min:
                        depart_delay += timedelta(minutes=start_stop.stop_duration_min)
                        
                    actual_depart_time = trip.departure_time + depart_delay
                    actual_arrive_time = trip.departure_time + (end_stop.time_from_start or timedelta())
                    
                    if actual_depart_time.date() == search_date:
                        # Суммируем цены участков маршрута от станции отправления до станции прибытия
                        # Цена на каждой остановке = стоимость участка ОТ ПРЕДЫДУЩЕЙ остановки ДО текущей
                        # Поэтому берем остановки с порядком > start_stop и <= end_stop
                        segment_stops = RouteStops.objects.filter(
                            route_id=r['route_id'],
                            stop_order__gt=start_stop.stop_order,
                            stop_order__lte=end_stop.stop_order
                        )
                        base_price = sum(s.price or 0 for s in segment_stops)
                        
                        wagons = TrainComp.objects.filter(trip_id=trip.id).select_related('class_field')
                        min_coef = None
                        classes = set()
                        for w in wagons:
                            if w.class_field:
                                coef = w.class_field.coef
                                classes.add(w.class_field.class_name)
                                if min_coef is None or coef < min_coef:
                                    min_coef = coef
                                    
                        min_price = int(float(base_price) * float(min_coef)) if min_coef else base_price
                        
                        # Продолжительность пути: разница между временем в пути до конечной и начальной остановок
                        start_time = start_stop.time_from_start or timedelta()
                        end_time = end_stop.time_from_start or timedelta()
                        duration = end_time - start_time
                        
                        total_seconds = int(duration.total_seconds())
                        hours, remainder = divmod(total_seconds, 3600)
                        minutes, _ = divmod(remainder, 60)
                        duration_str = f"{hours} Ч {minutes} МИН"
                        
                        results.append({
                            'trip_id': trip.id,
                            'train_num': trip.train_num,
                            'depart_time': actual_depart_time,
                            'arrive_time': actual_arrive_time,
                            'duration': duration,
                            'duration_str': duration_str,
                            'min_price': min_price,
                            'base_price': base_price,
                            'classes': list(classes),
                            'start_station': start_stop.station.station_name,
                            'end_station': end_stop.station.station_name,
                            'start_station_id': start_stop.station_id,
                            'end_station_id': end_stop.station_id,
                            'is_past': actual_depart_time < datetime.now(),
                            'is_multi_day': actual_depart_time.date() != actual_arrive_time.date(),
                        })
        except ValueError:
            pass
            
    sort_param = request.GET.get('sort', 'time')
            
    if results and sort_param:
        if sort_param == 'price':
            results.sort(key=lambda x: x['min_price'])
        elif sort_param == 'time':
            results.sort(key=lambda x: x['duration'].total_seconds())

    if results:
        min_price_res = min(results, key=lambda x: x['min_price'])
        min_time_res = min(results, key=lambda x: x['duration'].total_seconds())
        for res in results:
            if res['min_price'] == min_price_res['min_price']:
                res['is_cheapest'] = True
            if res['duration'].total_seconds() == min_time_res['duration'].total_seconds():
                res['is_fastest'] = True

    context = {
        'results': results,
        'from_query': from_query,
        'to_query': to_query,
        'date_query': date_query,
        'sort_param': sort_param,
    }
    return render(request, 'search.html', context)


def seat_selection_view(request, trip_id):
    """
    Представление для выбора вагона и места на конкретный рейс.
    Загружает доступные вагоны, занятые места (с учетом перекрытия маршрутов)
    и дополнительные услуги для оформления билета.
    """
    try:
        trip = Trips.objects.get(id=trip_id)
    except Trips.DoesNotExist:
        return redirect('search')
        
    # Динамически определяем базовую цену сегмента на стороне сервера
    from_station_id = request.GET.get('from_station')
    to_station_id   = request.GET.get('to_station')
    
    base_price = None
    if from_station_id and to_station_id:
        try:
            start_stop = RouteStops.objects.filter(route_id=trip.route_id, station_id=int(from_station_id)).first()
            end_stop = RouteStops.objects.filter(route_id=trip.route_id, station_id=int(to_station_id)).first()
            if start_stop and end_stop and start_stop.stop_order < end_stop.stop_order:
                segment_stops = RouteStops.objects.filter(
                    route_id=trip.route_id,
                    stop_order__gt=start_stop.stop_order,
                    stop_order__lte=end_stop.stop_order
                )
                base_price = sum(s.price or 0 for s in segment_stops)
        except (ValueError, Exception):
            pass

    if base_price is None:
        all_stops = RouteStops.objects.filter(route_id=trip.route_id)
        base_price = sum(s.price or 0 for s in all_stops)

    passenger_start_order = None
    passenger_end_order   = None
    if from_station_id and to_station_id:
        try:
            ps = RouteStops.objects.filter(route_id=trip.route_id, station_id=int(from_station_id)).first()
            pe = RouteStops.objects.filter(route_id=trip.route_id, station_id=int(to_station_id)).first()
            if ps and pe:
                passenger_start_order = ps.stop_order
                passenger_end_order   = pe.stop_order
        except (ValueError, Exception):
            pass

    wagons = TrainComp.objects.filter(trip_id=trip_id).select_related('class_field').order_by('wagon_num')

    # Получаем все активные (не отмененные) билеты на этот рейс
    all_tickets = Tickets.objects.filter(trip_id=trip_id).exclude(status_of_ticket=TicketStatus.CANCELLED)

    # Создаем словарь порядковых номеров остановок для этого маршрута
    route_stops_qs = RouteStops.objects.filter(route_id=trip.route_id)
    station_to_order = {rs.station_id: rs.stop_order for rs in route_stops_qs}

    booked_seats_by_wagon = {}
    wagon_prices = {}
    for w in wagons:
        wagon_tickets = all_tickets.filter(wagon=w.wagon_num)
        if passenger_start_order is not None and passenger_end_order is not None:
            # Считаем место занятым только если его забронированный маршрут пересекается с маршрутом текущего пассажира
            # Пересечение: начало билета < конец пассажира И начало пассажира < конец билета

            booked = []
            for t in wagon_tickets:
                t_start = station_to_order.get(t.start_station_id)
                t_end   = station_to_order.get(t.end_station_id)
                if t_start is not None and t_end is not None:
                    if t_start < passenger_end_order and passenger_start_order < t_end:
                        booked.append(t.seat)
        else:
            booked = list(wagon_tickets.values_list('seat', flat=True))
        booked_seats_by_wagon[w.wagon_num] = booked
        coef = float(w.class_field.coef) if (w.class_field and w.class_field.coef) else 1.0
        wagon_prices[w.wagon_num] = int(base_price * coef)
        
    extra_services = ExtraServices.objects.all()
    
    user_id = request.session.get('user_id')
    user_gender = ""
    tracked_wagons = []
    if user_id:
        try:
            user = Users.objects.get(id=user_id)
            user_gender = user.gender if user.gender else ""
            tracked_wagons = list(Notifications.objects.filter(user=user, route_id=trip.route_id).values_list('wagon_num', flat=True))
        except Users.DoesNotExist:
            pass

    import json
    # Build wagon -> class_id mapping for frontend
    wagon_class_ids = {w.wagon_num: w.class_field_id for w in wagons if w.class_field_id}
    CLASS_HIERARCHY = [1, 2, 3, 4, 5]  # SITTING, ECONOMY, COMPARTMENT, SV, FIRST
    max_class_id = max((c for c in wagon_class_ids.values() if c), key=lambda c: CLASS_HIERARCHY.index(c) if c in CLASS_HIERARCHY else -1, default=None)

    can_auto_upgrade = True
    if trip.departure_time:
        dep = trip.departure_time
        if hasattr(dep, 'tzinfo') and dep.tzinfo is not None:
            dep = dep.replace(tzinfo=None)
        from datetime import timezone, timedelta
        MSK = timezone(timedelta(hours=3))
        now_msk = datetime.now(MSK).replace(tzinfo=None)
        minutes_to_dep = (dep - now_msk).total_seconds() / 60
        if minutes_to_dep < 70:
            can_auto_upgrade = False

    context = {
        'trip': trip,
        'wagons': wagons,
        'booked_seats_json': json.dumps(booked_seats_by_wagon),
        'wagon_prices_json': json.dumps(wagon_prices),
        'wagon_class_ids_json': json.dumps(wagon_class_ids),
        'max_class_id': max_class_id,
        'can_auto_upgrade': can_auto_upgrade,
        'extra_services': extra_services,
        'user_gender': user_gender,
        'tracked_wagons_json': json.dumps(tracked_wagons),
        'from_station_id': from_station_id or '',
        'to_station_id': to_station_id or '',
    }
    return render(request, 'seat_selection.html', context)

def login_view(request):
    """
    Представление для входа в систему.
    Проверяет логин и пароль в базе данных и сохраняет ID пользователя в сессии.
    """
    next_url = request.GET.get('next') or request.POST.get('next') or 'profile'
    if request.method == 'POST':
        u = request.POST.get('username')
        p = request.POST.get('password')
        try:
            user = Users.objects.get(login=u, password=p)
            request.session['user_id'] = user.id
            return redirect(next_url)
        except Users.DoesNotExist:
            return render(request, 'login.html', {'error': 'Неверный логин или пароль', 'next': next_url})
    return render(request, 'login.html', {'next': next_url})

def register_view(request):
    """
    Представление для регистрации нового пользователя.
    Выполняет валидацию данных (совпадение паролей, уникальность логина, формат имени)
    и создает новую запись в таблице пользователей.
    """
    if request.method == 'POST':
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        middle_name = request.POST.get('middle_name')
        email = request.POST.get('email')
        username = request.POST.get('username')
        password = request.POST.get('password')
        password_confirm = request.POST.get('password_confirm')
        phone = request.POST.get('phone')
        gender = request.POST.get('gender')
        birth_date = request.POST.get('birth_date')
        
        if Users.objects.filter(login=username).exists():
            return render(request, 'login.html', {'error': 'Невозможно зарегистрироваться', 'active_tab': 'reg', 'reg_data': request.POST})
            
        parsed_birth_date = None
        if birth_date:
            try:
                parsed_birth_date = datetime.strptime(birth_date, '%d.%m.%Y').date()
            except ValueError:
                parsed_birth_date = birth_date
                
        parsed_phone = None
        if phone:
            parsed_phone = int(''.join(filter(str.isdigit, phone)))
            
        if Users.objects.filter(email=email).exists():
            return render(request, 'login.html', {'error': 'Невозможно зарегистрироваться под данным email', 'active_tab': 'reg', 'reg_data': request.POST})
            
        if parsed_phone and Users.objects.filter(phone=parsed_phone).exists():
            return render(request, 'login.html', {'error': 'Невозможно зарегистрироваться под данным номером телефона', 'active_tab': 'reg', 'reg_data': request.POST})
            
        fio_parts = [last_name, first_name]
        if middle_name:
            fio_parts.append(middle_name)
        fio = " ".join([p.strip() for p in fio_parts if p and p.strip()])
        user = Users.objects.create(
            login=username,
            email=email,
            password=password,
            fio=fio,
            phone=parsed_phone,
            gender=gender,
            birth_date=parsed_birth_date
        )
        request.session['user_id'] = user.id
        next_url = request.POST.get('next') or 'profile'
        return redirect(next_url)
    return redirect('login')

def logout_view(request):
    """
    Представление для выхода из системы.
    Удаляет ID пользователя из сессии и перенаправляет на указанную страницу или на главную.
    """
    if 'user_id' in request.session:
        del request.session['user_id']
    next_url = request.GET.get('next') or 'search'
    return redirect(next_url)

def profile_view(request):
    """
    Представление для отображения личного кабинета пользователя.
    Загружает профиль, документы, историю билетов и подписки на уведомления.
    Также обогащает объекты дополнительными данными (расчетное время прибытия, класс вагона).
    """
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('login')
    
    try:
        from datetime import timedelta
        user = Users.objects.get(id=user_id)
        docs = UserDocs.objects.filter(user=user)
        tickets = Tickets.objects.filter(doc__user=user).select_related('trip', 'start_station', 'end_station', 'doc').order_by('-id')
        notifications = Notifications.objects.filter(user=user).select_related('departure_point', 'arrival_point', 'trip')
        
        # Обогащаем объекты уведомлений реальными данными из БД
        for notif in notifications:
            # Если конкретный рейс не привязан, ищем ближайший по маршруту
            if not notif.trip and notif.route_id:
                notif.trip = Trips.objects.filter(route_id=notif.route_id).order_by('departure_time').first()

            if notif.trip and notif.trip.departure_time and notif.arrival_point:
                end_stop = RouteStops.objects.filter(route_id=notif.trip.route_id, station=notif.arrival_point).first()
                start_stop = RouteStops.objects.filter(route_id=notif.trip.route_id, station=notif.departure_point).first()
                
                if end_stop and end_stop.time_from_start:
                    notif.arrival_time = notif.trip.departure_time + end_stop.time_from_start
                else:
                    notif.arrival_time = None
                    
                notif.arrival_track = end_stop.arrival_track if end_stop else 1
                notif.departure_track = start_stop.arrival_track if start_stop else 1
            else:
                notif.arrival_time = None
                notif.arrival_track = 1
                notif.departure_track = 1

        
        # Обогащаем объекты билетов реальными данными для интерфейса
        for ticket in tickets:
            if ticket.trip and ticket.trip.departure_time and ticket.end_station:
                end_stop = RouteStops.objects.filter(route_id=ticket.trip.route_id, station=ticket.end_station).first()
                start_stop = RouteStops.objects.filter(route_id=ticket.trip.route_id, station=ticket.start_station).first()
                
                if end_stop and end_stop.time_from_start:
                    ticket.arrival_time = ticket.trip.departure_time + end_stop.time_from_start
                else:
                    ticket.arrival_time = None
                    
                ticket.arrival_track = end_stop.arrival_track if end_stop else 1
                ticket.departure_track = start_stop.arrival_track if start_stop else 1
            else:
                ticket.arrival_time = None
                ticket.arrival_track = 1
                ticket.departure_track = 1
            
            # Получаем класс вагона
            try:
                tc = TrainComp.objects.select_related('class_field').get(trip=ticket.trip, wagon_num=ticket.wagon)
                ticket.wagon_class = tc.class_field.class_name if tc.class_field else 'Неизвестно'
                ticket.wagon_class_id = tc.class_field_id if tc.class_field else None
            except Exception:
                ticket.wagon_class = 'Неизвестно'
                ticket.wagon_class_id = None
                
            # Парсим расположение и тип места из БД
            ticket.seat_type = ticket.seat_spec.type_name if ticket.seat_spec else "Стандартное"
            ticket.seat_location = "Стандартное"
            
            if ticket.wagon_class_id and ticket.seat:
                from .models import SeatLayouts
                layout = SeatLayouts.objects.filter(class_field_id=ticket.wagon_class_id, seat_num=ticket.seat).first()
                if layout and layout.shelf_type:
                    ticket.seat_location = layout.shelf_type
                
        dynamic_services = ExtraServices.objects.filter(format_id=1)

        return render(request, 'profile.html', {
            'user': user,
            'docs': docs,
            'tickets': tickets,
            'notifications': notifications,
            'dynamic_services': dynamic_services
        })
    except Users.DoesNotExist:
        return redirect('login')

def profile_update_user_view(request):
    """
    Представление для обновления личных данных пользователя в профиле.
    """
    user_id = request.session.get('user_id')
    if not user_id or request.method != 'POST':
        return redirect('profile')
    
    try:
        user = Users.objects.get(id=user_id)
        
        new_email = request.POST.get('email', user.email)
        phone = request.POST.get('phone')
        parsed_phone = None
        if phone:
            parsed_phone = int(''.join(filter(str.isdigit, phone)))
            
        if new_email and new_email != user.email and Users.objects.filter(email=new_email).exclude(id=user.id).exists():
            messages.error(request, 'Этот email уже используется другим аккаунтом.')
            return redirect('/profile/#profile')
            
        if parsed_phone and parsed_phone != user.phone and Users.objects.filter(phone=parsed_phone).exclude(id=user.id).exists():
            messages.error(request, 'Этот номер телефона уже используется другим аккаунтом.')
            return redirect('/profile/#profile')

        user.fio = request.POST.get('fio', user.fio)
        user.email = new_email
        user.gender = request.POST.get('gender', user.gender)
        
        if parsed_phone:
            user.phone = parsed_phone
            
        birth_date = request.POST.get('birth_date')
        if birth_date:
            try:
                user.birth_date = datetime.strptime(birth_date, '%d.%m.%Y').date()
            except ValueError:
                user.birth_date = birth_date
            
        user.save()
        messages.success(request, 'Личные данные успешно обновлены.')
    except Exception as e:
        messages.error(request, f'Ошибка при обновлении данных: {e}')
        
    return redirect('/profile/#profile')

def profile_add_doc_view(request):
    """
    Представление для добавления нового документа пассажира в профиль.
    Выполняет строгую проверку форматов (Паспорт РФ, Загранпаспорт, Свидетельство о рождении).
    """
    user_id = request.session.get('user_id')
    if not user_id or request.method != 'POST':
        return redirect('/profile/#docs')
        
    try:
        user = Users.objects.get(id=user_id)
        doc_type = request.POST.get('doc_type')
        doc_num = request.POST.get('doc_num')
        issue_date = request.POST.get('issue_date')
        
        if doc_type and doc_num:
            import re
            
            if doc_type == 'Паспорт РФ':
                digits = re.sub(r'\D', '', doc_num)
                if len(digits) != 10:
                    messages.error(request, 'Неверный формат Паспорта РФ. Ожидается 10 цифр.')
                    return redirect('/profile/#docs')
                doc_num = f"{digits[:4]} {digits[4:]}"
                
            elif doc_type == 'Загранпаспорт':
                digits = re.sub(r'\D', '', doc_num)
                if len(digits) != 9:
                    messages.error(request, 'Неверный формат Загранпаспорта. Ожидается 9 цифр.')
                    return redirect('/profile/#docs')
                doc_num = f"{digits[:2]} {digits[2:]}"
                
            elif doc_type == 'Свидетельство о рождении':
                # Удаляем пробелы и дефисы, переводим все символы в верхний регистр
                cleaned = re.sub(r'[\s-]', '', doc_num).upper()
                # Регулярка ожидает: римские цифры + две русские буквы + 6 цифр
                match = re.match(r'^([IVXLCDM]+)([А-ЯЁ]{2})(\d{6})$', cleaned)
                if not match:
                    # Попытка исправить, если пользователь ввел английские буквы вместо русских
                    eng_to_cyr = str.maketrans('ABCEHKMOPTX', 'АВСЕНКМОРТХ')
                    match2 = re.match(r'^([IVXLCDM]+)([A-ZА-ЯЁ]{2})(\d{6})$', cleaned)
                    if match2:
                        letters = match2.group(2).translate(eng_to_cyr)
                        if not re.match(r'^[А-ЯЁ]{2}$', letters):
                            messages.error(request, 'Неверный формат Свидетельства о рождении. Пример: I-ЕА 720345')
                            return redirect('/profile/#docs')
                        doc_num = f"{match2.group(1)}-{letters} {match2.group(3)}"
                    else:
                        messages.error(request, 'Неверный формат Свидетельства о рождении. Пример: I-ЕА 720345')
                        return redirect('/profile/#docs')
                else:
                    doc_num = f"{match.group(1)}-{match.group(2)} {match.group(3)}"

            if UserDocs.objects.filter(doc_type=doc_type, doc_num=doc_num).exists():
                doc_name_lower = doc_type.lower()
                if 'паспорт рф' in doc_name_lower:
                    msg = 'Невозможно создать паспорт'
                elif 'загранпаспорт' in doc_name_lower:
                    msg = 'Невозможно создать загранпаспорт'
                elif 'свидетельство' in doc_name_lower:
                    msg = 'Невозможно создать свидетельство о рождении'
                else:
                    msg = 'Невозможно создать документ'
                messages.error(request, msg)
                return redirect('/profile/#docs')
                
            parsed_issue_date = None
            if issue_date:
                try:
                    parsed_issue_date = datetime.strptime(issue_date, '%d.%m.%Y').date()
                except ValueError:
                    parsed_issue_date = issue_date

            UserDocs.objects.create(
                user=user,
                doc_type=doc_type,
                doc_num=doc_num,
                issue_date=parsed_issue_date
            )
            messages.success(request, 'Документ успешно добавлен.')
        else:
            messages.error(request, 'Тип и номер документа обязательны.')
    except Exception as e:
        messages.error(request, f'Ошибка при добавлении документа: {e}')
        
    return redirect('/profile/#docs')

def profile_edit_doc_view(request, doc_id):
    """
    Представление для изменения существующего документа пассажира.
    Также проводит перепроверку форматов.
    """
    user_id = request.session.get('user_id')
    if not user_id or request.method != 'POST':
        return redirect('/profile/#docs')
        
    try:
        user = Users.objects.get(id=user_id)
        doc = UserDocs.objects.get(id=doc_id, user=user)
        
        doc_type = request.POST.get('doc_type')
        doc_num = request.POST.get('doc_num')
        issue_date = request.POST.get('issue_date')
        
        if doc_type and doc_num:
            import re
            
            if doc_type == 'Паспорт РФ':
                digits = re.sub(r'\D', '', doc_num)
                if len(digits) != 10:
                    messages.error(request, 'Неверный формат Паспорта РФ. Ожидается 10 цифр.')
                    return redirect('/profile/#docs')
                doc_num = f"{digits[:4]} {digits[4:]}"
                
            elif doc_type == 'Загранпаспорт':
                digits = re.sub(r'\D', '', doc_num)
                if len(digits) != 9:
                    messages.error(request, 'Неверный формат Загранпаспорта. Ожидается 9 цифр.')
                    return redirect('/profile/#docs')
                doc_num = f"{digits[:2]} {digits[2:]}"
                
            elif doc_type == 'Свидетельство о рождении':
                cleaned = re.sub(r'[\s-]', '', doc_num).upper()
                match = re.match(r'^([IVXLCDM]+)([А-ЯЁ]{2})(\d{6})$', cleaned)
                if not match:
                    eng_to_cyr = str.maketrans('ABCEHKMOPTX', 'АВСЕНКМОРТХ')
                    match2 = re.match(r'^([IVXLCDM]+)([A-ZА-ЯЁ]{2})(\d{6})$', cleaned)
                    if match2:
                        letters = match2.group(2).translate(eng_to_cyr)
                        if not re.match(r'^[А-ЯЁ]{2}$', letters):
                            messages.error(request, 'Неверный формат Свидетельства о рождении.')
                            return redirect('/profile/#docs')
                        doc_num = f"{match2.group(1)}-{letters} {match2.group(3)}"
                    else:
                        messages.error(request, 'Неверный формат Свидетельства о рождении.')
                        return redirect('/profile/#docs')
                else:
                    doc_num = f"{match.group(1)}-{match.group(2)} {match.group(3)}"

            # Проверяем, не пытаемся ли мы изменить на документ, который уже существует (кроме текущего)
            if doc.doc_type != doc_type or doc.doc_num != doc_num:
                if UserDocs.objects.filter(doc_type=doc_type, doc_num=doc_num).exclude(id=doc.id).exists():
                    doc_name_lower = doc_type.lower()
                    if 'паспорт рф' in doc_name_lower:
                        msg = 'Невозможно создать паспорт'
                    elif 'загранпаспорт' in doc_name_lower:
                        msg = 'Невозможно создать загранпаспорт'
                    elif 'свидетельство' in doc_name_lower:
                        msg = 'Невозможно создать свидетельство о рождении'
                    else:
                        msg = 'Невозможно создать документ'
                    messages.error(request, msg)
                    return redirect('/profile/#docs')
            
            parsed_issue_date = None
            if issue_date:
                try:
                    parsed_issue_date = datetime.strptime(issue_date, '%d.%m.%Y').date()
                except ValueError:
                    parsed_issue_date = issue_date

            doc.doc_type = doc_type
            doc.doc_num = doc_num
            doc.issue_date = parsed_issue_date
            doc.save()
            messages.success(request, 'Документ успешно изменен.')
        else:
            messages.error(request, 'Тип и номер документа обязательны.')
            
    except UserDocs.DoesNotExist:
        messages.error(request, 'Документ не найден.')
    except Exception as e:
        messages.error(request, f'Ошибка при изменении документа: {e}')
        
    return redirect('/profile/#docs')

def profile_delete_doc_view(request, doc_id):
    """
    Представление для удаления документа из профиля.
    Запрещает удаление, если на этот документ оформлен активный билет (IntegrityError).
    """
    user_id = request.session.get('user_id')
    if not user_id or request.method != 'POST':
        return redirect('/profile/#docs')
        
    try:
        from django.db import IntegrityError
        doc = UserDocs.objects.get(id=doc_id, user_id=user_id)
        doc.delete()
        messages.success(request, 'Документ успешно удален.')
    except UserDocs.DoesNotExist:
        messages.error(request, 'Документ не найден.')
    except IntegrityError:
        messages.error(request, 'Нельзя удалить документ, по которому оформлен билет.')
        
    return redirect('/profile/#docs')

def delete_account_view(request):
    """
    Представление для удаления аккаунта.
    Поддерживает как "мягкое" скрытие, так и полное удаление с отменой всех активных билетов.
    """
    user_id = request.session.get('user_id')
    if not user_id or request.method != 'POST':
        return redirect('profile')

    mode = request.POST.get('mode', 'simple')

    try:
        user = Users.objects.get(id=user_id)

        if mode == 'full_delete':
            # Отменяем активные билеты и рассылаем уведомления об освободившихся местах
            active_tickets = list(Tickets.objects.filter(
                doc__user=user
            ).exclude(status_of_ticket=TicketStatus.CANCELLED).select_related('trip', 'start_station', 'end_station', 'doc__user', 'seat_spec'))
            
            by_wagon = {} # (trip_id, wagon) -> ticket
            for ticket in active_tickets:
                ticket.status_of_ticket = TicketStatus.CANCELLED
                ticket.save()
                try:
                    from .email_utils import send_ticket_action_email
                    send_ticket_action_email(ticket, action='Возврат')
                except Exception:
                    pass

                # Группируем по уникальному сочетанию (рейс, вагон)
                if ticket.trip_id and ticket.wagon:
                    key = (ticket.trip_id, ticket.wagon)
                    if key not in by_wagon:
                        by_wagon[key] = ticket

            # Рассылаем по одному уведомлению на вагон
            try:
                from .email_utils import send_seat_available_email
                for ticket in by_wagon.values():
                    send_seat_available_email(ticket)
            except Exception:
                pass

            # Удаляем все данные пользователя в правильном порядке (связанные таблицы)
            from .models import Notifications, UserDocs, Tickets as TicketsModel
            Notifications.objects.filter(user=user).delete()
            # Сначала удаляем дополнительные услуги, затем билеты, потом документы
            all_docs = UserDocs.objects.filter(user=user)
            user_tickets = Tickets.objects.filter(doc__in=all_docs)
            BookedServices.objects.filter(ticket__in=user_tickets).delete()
            user_tickets.delete()
            all_docs.delete()
            user.delete()

        else:
            # Простой режим: деактивируем только логин и пароль (без удаления истории)
            user.login = None
            user.password = None
            user.save()

        # Logout
        if 'user_id' in request.session:
            del request.session['user_id']

    except Users.DoesNotExist:
        pass

    return redirect('search')


def profile_cancel_ticket_view(request, ticket_id):
    """
    Представление для отмены билета пользователем.
    Меняет статус билета на 'Отменен', отправляет уведомления о возврате
    и оповещает других пользователей об освободившемся месте.
    """
    user_id = request.session.get('user_id')
    if not user_id or request.method != 'POST':
        return redirect('/profile/#tickets')

    try:
        ticket = Tickets.objects.select_related(
            'trip', 'start_station', 'end_station', 'seat_spec', 'doc__user'
        ).get(id=ticket_id, doc__user_id=user_id)
        from .models import BookedServices
        # Находим и удаляем сопутствующие доп. услуги
        booked_services = list(BookedServices.objects.filter(ticket=ticket).select_related('service'))
        cancelled_services_list = [bs.service for bs in booked_services if bs.service]
        BookedServices.objects.filter(ticket=ticket).delete()

        ticket.status_of_ticket = TicketStatus.CANCELLED
        ticket.extra_price = 0
        ticket.save()

        # Уведомляем подписчиков об освободившемся месте
        from .email_utils import send_seat_available_email, send_ticket_action_email
        send_seat_available_email(ticket)
        
        # Отправляем письмо пассажиру о возврате
        send_ticket_action_email(ticket, action='Возврат', added_services=cancelled_services_list)

        messages.success(request, 'Билет успешно отменен.')
    except Tickets.DoesNotExist:
        messages.error(request, 'Билет не найден.')

    return redirect('/profile/#tickets')

def profile_add_services_view(request, ticket_id):
    user_id = request.session.get('user_id')
    if not user_id or request.method != 'POST':
        return redirect('/profile/#tickets')
        
    try:
        from .models import Tickets, ExtraServices, BookedServices
        ticket = Tickets.objects.get(id=ticket_id, doc__user_id=user_id)
        services_param = request.POST.get('dynamic_services', '')
        
        if services_param:
            service_ids = [s for s in services_param.split(',') if s]
            services = ExtraServices.objects.filter(id__in=service_ids)
            total_price = 0
            from django.utils import timezone
            for s in services:
                BookedServices.objects.create(ticket=ticket, service=s, booking_time=timezone.now())
                total_price += (s.price or 0)
                
            if ticket.extra_price is None:
                ticket.extra_price = 0
            ticket.extra_price += total_price
            ticket.save()
            
            from .email_utils import send_ticket_action_email
            send_ticket_action_email(ticket, action='ДопУслуги', added_services=services)
            
            from django.contrib import messages
            messages.success(request, 'Дополнительные услуги успешно оплачены и добавлены к билету.')
    except Tickets.DoesNotExist:
        from django.contrib import messages
        messages.error(request, 'Билет не найден.')
    except Exception as e:
        from django.contrib import messages
        messages.error(request, f'Ошибка при добавлении услуг: {e}')
        
    return redirect('/profile/#tickets')

def profile_delete_notification_view(request, notif_id):
    """
    Представление для удаления подписки на уведомление из профиля.
    """
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect(f'/login/?next=/profile/notification/{notif_id}/delete/')
        
    try:
        notif = Notifications.objects.get(id=notif_id, user_id=user_id)
        notif.delete()
        messages.success(request, 'Уведомление удалено.')
    except Notifications.DoesNotExist:
        messages.error(request, 'Уведомление не найдено.')
        
    return redirect('/profile/#notifications')

def profile_add_notification_view(request, trip_id):
    """
    Представление для добавления подписки на уведомления о местах в конкретном рейсе.
    Используется, когда мест нет, и пользователь хочет получить письмо при их освобождении.
    """
    user_id = request.session.get('user_id')
    if not user_id or request.method != 'POST':
        return redirect('login')
        
    try:
        trip = Trips.objects.get(id=trip_id)
        wagon_num = request.POST.get('wagon_num')
        from .models import RouteStops
        stops = RouteStops.objects.filter(route_id=trip.route_id).order_by('stop_order')
        start_station = stops.first().station if stops.exists() else None
        end_station = stops.last().station if stops.exists() else None
        
        if not Notifications.objects.filter(user_id=user_id, trip=trip, wagon_num=wagon_num).exists():
            Notifications.objects.create(
                user_id=user_id,
                route_id=trip.route_id,
                trip=trip,
                wagon_num=wagon_num,
                departure_point=start_station,
                arrival_point=end_station
            )
            messages.success(request, f'Вы успешно подписались на уведомления (Вагон {wagon_num if wagon_num else "Любой"})!')
        else:
            messages.info(request, 'Вы уже подписаны на этот рейс с указанными параметрами.')
            
    except Trips.DoesNotExist:
        messages.error(request, 'Рейс не найден.')
    
    return redirect(f'/seats/{trip_id}/')

def success_view(request):
    """
    Представление для отображения страницы успешного завершения операции (например, оплаты билета).
    """
    return render(request, 'success.html')

def checkout_view(request, trip_id):
    """
    Представление для оформления билета (оплаты).
    Проверяет корректность выбранного места, пол,
    формирует билет и дополнительные услуги, а также отправляет email-подтверждение.
    """
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('login')

    try:
        trip = Trips.objects.get(id=trip_id)
        user = Users.objects.get(id=user_id)
        user_doc = UserDocs.objects.filter(user=user).order_by('-issue_date').first()
    except (Trips.DoesNotExist, Users.DoesNotExist):
        return redirect('search')

    if not user_doc:
        messages.warning(request, 'Для оформления билета необходимо добавить хотя бы один документ в профиле.')
        return redirect('/profile/#docs')

    if request.method == 'POST':
        wagon = request.POST.get('wagon')
        seat = request.POST.get('seat')
        price = request.POST.get('price', 0)
        extra_services_param = request.POST.get('extra_services', '')
        from_station_id = request.POST.get('from_station')
        to_station_id   = request.POST.get('to_station')
        auto_upgrade_val = request.POST.get('auto_upgrade', 'false') == 'true'

        # Определяем фактические станции отправления и прибытия для данного пассажира
        pax_start_station = None
        pax_end_station   = None
        if from_station_id and to_station_id:
            try:
                pax_start_station = Stations.objects.get(id=int(from_station_id))
                pax_end_station   = Stations.objects.get(id=int(to_station_id))
            except (Stations.DoesNotExist, ValueError):
                pass
        # Если не переданы, берем первую и последнюю остановку маршрута
        if not pax_start_station or not pax_end_station:
            _stops = RouteStops.objects.filter(route_id=trip.route_id).select_related('station').order_by('stop_order')
            if not pax_start_station and _stops.first():
                pax_start_station = _stops.first().station
            if not pax_end_station and _stops.last():
                pax_end_station = _stops.last().station

        # Проверяем, что поезд еще не отправился
        if pax_start_station:
            start_stop = RouteStops.objects.filter(route_id=trip.route_id, station=pax_start_station).first()
            if start_stop:
                depart_delay = start_stop.time_from_start or timedelta()
                if start_stop.stop_duration_min:
                    depart_delay += timedelta(minutes=start_stop.stop_duration_min)
                actual_depart_time = trip.departure_time + depart_delay
                if actual_depart_time < datetime.now():
                    messages.error(request, 'Поезд уже отправился.')
                    return redirect('search')

        # Проверяем, существует ли указанное место в вагоне
        seat_spec_obj = None
        try:
            wagon_num = int(wagon)
            seat_num = int(seat)
            w_obj = TrainComp.objects.select_related('class_field').get(trip=trip, wagon_num=wagon_num)
            sl = SeatLayouts.objects.select_related('seat_type').get(class_field=w_obj.class_field, seat_num=seat_num)
            seat_spec_obj = sl.seat_type
            wagon_class = w_obj.class_field.class_name if w_obj.class_field else ""
        except (ValueError, TrainComp.DoesNotExist, SeatLayouts.DoesNotExist):
            messages.error(request, 'Указанное место или вагон не существует для этого поезда.')
            return redirect('search')

        # Безопасно рассчитываем цену на стороне сервера для предотвращения подмены стоимости со стороны клиента
        base_price_val = None
        if from_station_id and to_station_id:
            try:
                start_stop = RouteStops.objects.filter(route_id=trip.route_id, station_id=int(from_station_id)).first()
                end_stop = RouteStops.objects.filter(route_id=trip.route_id, station_id=int(to_station_id)).first()
                if start_stop and end_stop and start_stop.stop_order < end_stop.stop_order:
                    segment_stops = RouteStops.objects.filter(
                        route_id=trip.route_id,
                        stop_order__gt=start_stop.stop_order,
                        stop_order__lte=end_stop.stop_order
                    )
                    base_price_val = sum(s.price or 0 for s in segment_stops)
            except (ValueError, Exception):
                pass
        
        if base_price_val is None:
            all_stops = RouteStops.objects.filter(route_id=trip.route_id)
            base_price_val = sum(s.price or 0 for s in all_stops)
            
        coef_val = float(w_obj.class_field.coef) if (w_obj.class_field and w_obj.class_field.coef) else 1.0
        price = int(base_price_val * coef_val)

        # Отключаем опцию автоапгрейда, если выбранный класс является максимальным в этом поезде
        CLASS_HIERARCHY = [
            WagonClassID.SITTING, WagonClassID.ECONOMY, WagonClassID.COMPARTMENT,
            WagonClassID.SV, WagonClassID.FIRST,
        ]
        train_class_ids = set(
            TrainComp.objects.filter(trip=trip).values_list('class_field_id', flat=True)
        )
        # Ищем максимальный класс среди вагонов текущего поезда
        max_class_in_train = None
        for cls in reversed(CLASS_HIERARCHY):
            if cls in train_class_ids:
                max_class_in_train = cls
                break
        if w_obj.class_field_id == max_class_in_train:
            auto_upgrade_val = False

        if auto_upgrade_val:
            price = int(price * 1.1)

        # Проверяем  половые ограничения места (2: Женское, 3: Мужское)
        if sl.seat_type_id == 2:
            if not user.gender or not user.gender.strip().upper().startswith('Ж'):
                messages.error(request, 'Вы не можете оформить билет в женское купе.')
                return redirect('search')
        elif sl.seat_type_id == 3:
            if not user.gender or not user.gender.strip().upper().startswith('М'):
                messages.error(request, 'Вы не можете оформить билет в мужское купе.')
                return redirect('search')

        # Проверка пересечения (чтобы не было активного билета на то же место и участок пути)
        route_stops_qs = RouteStops.objects.filter(route_id=trip.route_id)
        station_to_order = {rs.station_id: rs.stop_order for rs in route_stops_qs}
        
        p_start_order = station_to_order.get(pax_start_station.id) if pax_start_station else None
        p_end_order = station_to_order.get(pax_end_station.id) if pax_end_station else None
        
        active_tickets = Tickets.objects.filter(trip=trip, wagon=wagon_num, seat=seat_num).exclude(status_of_ticket=TicketStatus.CANCELLED)
        
        overlap = False
        if active_tickets.exists() and p_start_order is not None and p_end_order is not None:
            for t in active_tickets:
                t_start = station_to_order.get(t.start_station_id)
                t_end = station_to_order.get(t.end_station_id)
                if t_start is not None and t_end is not None:
                    if t_start < p_end_order and p_start_order < t_end:
                        overlap = True
                        break
        elif active_tickets.exists():
            overlap = True
            
        if overlap:
            messages.error(request, 'Извините, это место уже куплено или занято на выбранном участке маршрута.')
            return redirect('search')

        # Рассчитываем сумму дополнительных услуг (extra_price)
        extra_price_total = 0
        booked_service_objects = []
        if extra_services_param:
            service_ids = [s for s in extra_services_param.split(',') if s]
            service_objs = ExtraServices.objects.filter(id__in=service_ids)
            for s in service_objs:
                extra_price_total += s.price or 0
            booked_service_objects = list(service_objs)

        ticket = Tickets.objects.create(
            doc=user_doc,
            trip=trip,
            wagon=wagon,
            seat=seat,
            price=price,
            extra_price=extra_price_total if extra_price_total else None,
            start_station=pax_start_station,
            end_station=pax_end_station,
            seat_spec=seat_spec_obj,
            auto_upgrade=auto_upgrade_val,
            status_of_ticket=TicketStatus.CONFIRMED
        )

        if booked_service_objects:
            from django.utils import timezone
            for s in booked_service_objects:
                BookedServices.objects.create(ticket=ticket, service=s, booking_time=timezone.now())
                
        # Отправляем письмо о покупке
        from .email_utils import send_ticket_action_email
        send_ticket_action_email(ticket, action='Покупка')
                
        return redirect('success')

    wagon = request.GET.get('wagon')
    seat = request.GET.get('seat')
    extra_services_param = request.GET.get('extra_services', '')
    from_station_id = request.GET.get('from_station')
    to_station_id   = request.GET.get('to_station')
    auto_upgrade_param = request.GET.get('auto_upgrade', 'false')

    if not wagon or not seat:
        return redirect('seat_selection', trip_id=trip_id)

    # Безопасно рассчитываем цену на стороне сервера для предотвращения подмены стоимости со стороны клиента
    base_price_val = None
    if from_station_id and to_station_id:
        try:
            start_stop = RouteStops.objects.filter(route_id=trip.route_id, station_id=int(from_station_id)).first()
            end_stop = RouteStops.objects.filter(route_id=trip.route_id, station_id=int(to_station_id)).first()
            if start_stop and end_stop and start_stop.stop_order < end_stop.stop_order:
                segment_stops = RouteStops.objects.filter(
                    route_id=trip.route_id,
                    stop_order__gt=start_stop.stop_order,
                    stop_order__lte=end_stop.stop_order
                )
                base_price_val = sum(s.price or 0 for s in segment_stops)
        except (ValueError, Exception):
            pass

    if base_price_val is None:
        all_stops = RouteStops.objects.filter(route_id=trip.route_id)
        base_price_val = sum(s.price or 0 for s in all_stops)

    # Умножаем стоимость на коэффициент выбранного класса вагона
    try:
        w_obj_get = TrainComp.objects.select_related('class_field').get(trip=trip, wagon_num=int(wagon))
        coef_val_get = float(w_obj_get.class_field.coef) if (w_obj_get.class_field and w_obj_get.class_field.coef) else 1.0
    except (ValueError, TypeError, TrainComp.DoesNotExist):
        coef_val_get = 1.0

    secure_price = int(base_price_val * coef_val_get)

    # Применяем наценку 10% за автоапгрейд, если опция активна и выбран не максимальный класс
    if auto_upgrade_param == 'true':
        CLASS_HIERARCHY = [
            WagonClassID.SITTING, WagonClassID.ECONOMY, WagonClassID.COMPARTMENT,
            WagonClassID.SV, WagonClassID.FIRST,
        ]
        train_class_ids = set(
            TrainComp.objects.filter(trip=trip).values_list('class_field_id', flat=True)
        )
        max_class_in_train = None
        for cls in reversed(CLASS_HIERARCHY):
            if cls in train_class_ids:
                max_class_in_train = cls
                break
        
        if w_obj_get and w_obj_get.class_field_id != max_class_in_train:
            secure_price = int(secure_price * 1.1)

    selected_services = []
    extra_price_total = 0
    if extra_services_param:
        service_ids = extra_services_param.split(',')
        selected_services = ExtraServices.objects.filter(id__in=service_ids)
        extra_price_total = sum((s.price or 0) for s in selected_services)
        
    total_price = secure_price + extra_price_total

    # Получаем подробную информацию о маршруте из БД
    stops = RouteStops.objects.filter(route_id=trip.route_id).select_related('station').order_by('stop_order')
    first_stop = stops.first()
    last_stop = stops.last()

    # Используем станции, выбранные пассажиром, если они есть
    if from_station_id:
        try:
            _ps = RouteStops.objects.filter(route_id=trip.route_id, station_id=int(from_station_id)).select_related('station').first()
            if _ps:
                first_stop = _ps
        except (ValueError, Exception):
            pass
    if to_station_id:
        try:
            _pe = RouteStops.objects.filter(route_id=trip.route_id, station_id=int(to_station_id)).select_related('station').first()
            if _pe:
                last_stop = _pe
        except (ValueError, Exception):
            pass

    start_station = first_stop.station.station_name if first_stop else "Пункт А"
    end_station = last_stop.station.station_name if last_stop else "Пункт Б"
    dep_track = first_stop.arrival_track if first_stop else 1
    arr_track = last_stop.arrival_track if last_stop else 1
    
    # Получаем фактическое время прибытия из БД, используя time_from_start
    arrival_dt = None
    if last_stop and last_stop.time_from_start:
        arrival_dt = trip.departure_time + last_stop.time_from_start

    # Детали о месте и вагоне
    wagon_class = "---"
    seat_type = "---"
    seat_pos = "---"
    
    try:
        w_num = int(wagon)
        s_num = int(seat)
        
        w_obj = TrainComp.objects.filter(trip_id=trip_id, wagon_num=w_num).select_related('class_field').first()
        if w_obj:
            wagon_class = w_obj.class_field.class_name
            class_id = w_obj.class_field_id
            
            # СТРОГО берем данные из БД
            layout = SeatLayouts.objects.filter(class_field_id=class_id, seat_num=s_num).select_related('seat_type').first()
            if layout:
                seat_pos = layout.shelf_type or "---"
                seat_type = layout.seat_type.type_name if layout.seat_type else "---"
    except:
        pass

    context = {
        'trip': trip,
        'wagon': wagon,
        'wagon_class': wagon_class,
        'seat': seat,
        'seat_type': seat_type,
        'seat_pos': seat_pos,
        'start_station': start_station,
        'end_station': end_station,
        'dep_track': dep_track,
        'arr_track': arr_track,
        'arrival_dt': arrival_dt,
        'base_price': secure_price,
        'total_price': total_price,
        'selected_services': selected_services,
        'extra_services_param': extra_services_param,
        'from_station_id': from_station_id or '',
        'to_station_id': to_station_id or '',
        'auto_upgrade_param': auto_upgrade_param,
        'user': user,
        'user_doc': user_doc
    }
    return render(request, 'checkout.html', context)

from django.http import JsonResponse
def toggle_notification_view(request, trip_id):
    """
    API-эндпоинт для переключения состояния подписки (колокольчика) на уведомления.
    Добавляет или удаляет подписку на освободившееся место в вагоне.
    """
    user_id = request.session.get('user_id')
    if not user_id or request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Not authenticated'})
        
    try:
        user = Users.objects.get(id=user_id)
        trip = Trips.objects.get(id=trip_id)
        
        import json
        data = json.loads(request.body)
        wagon_num = int(data.get('wagon_num'))
        
        notif = Notifications.objects.filter(user=user, route_id=trip.route_id, wagon_num=wagon_num).first()
        if notif:
            notif.delete()
            return JsonResponse({'success': True, 'state': 'removed'})
        else:
            # Определяем станции отправления и прибытия из запроса
            import json as _json
            from_station_id = data.get('from_station_id')
            to_station_id   = data.get('to_station_id')
            departure_point = None
            arrival_point   = None
            if from_station_id and to_station_id:
                try:
                    departure_point = Stations.objects.get(id=int(from_station_id))
                    arrival_point   = Stations.objects.get(id=int(to_station_id))
                except (Stations.DoesNotExist, ValueError):
                    pass
            # Запасной вариант: берем первую и последнюю остановки маршрута
            if not departure_point or not arrival_point:
                route_stops = RouteStops.objects.filter(route_id=trip.route_id).select_related('station').order_by('stop_order')
                if not departure_point and route_stops.first():
                    departure_point = route_stops.first().station
                if not arrival_point and route_stops.last():
                    arrival_point = route_stops.last().station

            Notifications.objects.create(
                user=user,
                route_id=trip.route_id,
                wagon_num=wagon_num,
                departure_point=departure_point,
                arrival_point=arrival_point
            )
            return JsonResponse({'success': True, 'state': 'added'})
            
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

def privacy_view(request):
    return render(request, 'privacy.html')
