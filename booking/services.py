from django.core.mail import send_mail
from .models import Ticket, BookedService, NotificationSubscription

class TicketBuilder:
    """
    Паттерн Builder для пошагового конструирования объекта билета.
    (Устаревший/экспериментальный код, не используется в текущей реализации checkout_view)
    """
    def __init__(self, user, trip, start_station, end_station):
        self.ticket = Ticket(
            user=user,
            trip=trip,
            start_station=start_station,
            end_station=end_station,
            status='BOOKED',
            price=0,
            extra_price=0
        )
        self.services = []

    def set_seat(self, wagon, seat, base_price):
        self.ticket.wagon = wagon
        self.ticket.seat = seat
        # Цена с учетом коэффициента вагона
        self.ticket.price = base_price * wagon.cost_coef
        return self

    def bind_user_doc(self, user_doc):
        self.ticket.user_doc = user_doc
        return self

    def add_booked_service(self, extra_service):
        self.services.append(extra_service)
        self.ticket.extra_price += extra_service.price
        return self

    def set_auto_upgrade(self, auto_upgrade):
        self.ticket.auto_upgrade = auto_upgrade
        return self

    def build(self):
        self.ticket.save()
        for svc in self.services:
            BookedService.objects.create(ticket=self.ticket, extra_service=svc)
        return self.ticket


class BookingTransactionFacade:
    """
    Паттерн Facade для скрытия сложности процесса бронирования.
    (Устаревший/экспериментальный код)
    """
    def process_booking(self, ticket_builder, payment_api_mock=True):
        """
        Фасад для бронирования. Проверяет занятость места, создает билет,
        и проводит оплату.
        """
        ticket = ticket_builder.ticket

        # 1. Проверка доступности места
        is_taken = Ticket.objects.filter(
            trip=ticket.trip,
            wagon=ticket.wagon,
            seat=ticket.seat,
            status__in=['BOOKED', 'CONFIRMED']
        ).exists()

        if is_taken:
            return False, "Место уже занято."

        # 2. Создание билета (бронирование)
        built_ticket = ticket_builder.build()

        # 3. Имитация оплаты
        if not payment_api_mock:
            built_ticket.status = 'CANCELLED'
            built_ticket.save()
            return False, "Сбой платежа."

        built_ticket.status = 'CONFIRMED'
        built_ticket.save()
        
        return True, built_ticket


class CentralAvailabilityTracker:
    """
    Паттерн Observer для рассылки уведомлений подписчикам.
    (Устаревший/экспериментальный код, заменен на функции в email_utils.py)
    """
    @staticmethod
    def notify_subscribers(trip, wagon_class_name, available_seats_count):
        """
        Observer pattern: Уведомляет подписанных пользователей о появлении билетов.
        """
        if available_seats_count <= 0:
            return

        subs = NotificationSubscription.objects.filter(trip=trip).select_related('user')
        
        recipient_list = [sub.user.email for sub in subs if sub.user.email]
        
        if not recipient_list:
            return

        subject = f'Свободные места на рейс {trip.trip_number}'
        message = (
            f"Отличные новости!\n"
            f"На рейс {trip.trip_number} появились билеты ({available_seats_count} шт.) "
            f"в вагонах класса '{wagon_class_name}'. Успейте купить!"
        )

        # Отправляем email. В settings.py нужно будет настроить EMAIL_BACKEND 
        # (например, console.EmailBackend для локальной разработки)
        try:
            send_mail(
                subject,
                message,
                'noreply@railway.local',
                recipient_list,
                fail_silently=True,
            )
        except Exception as e:
            print(f"Ошибка отправки почты: {e}")
