from django.urls import path
from . import views

urlpatterns = [
    # Основные страницы: Поиск и оформление билетов
    path('', views.search_view, name='search'),  # Главная страница (поиск рейсов)
    path('seats/<int:trip_id>/', views.seat_selection_view, name='seat_selection'),  # Выбор вагона и места
    path('checkout/<int:trip_id>/', views.checkout_view, name='checkout'),  # Оформление и оплата билета
    path('success/', views.success_view, name='success'),  # Страница успешной покупки

    # Аутентификация
    path('login/', views.login_view, name='login'),  # Вход в аккаунт
    path('register/', views.register_view, name='register'),  # Регистрация нового пользователя
    path('logout/', views.logout_view, name='logout'),  # Выход из аккаунта

    # Личный кабинет: Профиль и документы
    path('profile/', views.profile_view, name='profile'),  # Главная страница личного кабинета
    path('profile/update/', views.profile_update_user_view, name='profile_update_user'),  # Обновление личных данных
    path('profile/doc/add/', views.profile_add_doc_view, name='profile_add_doc'),  # Добавление нового документа
    path('profile/doc/<int:doc_id>/edit/', views.profile_edit_doc_view, name='profile_edit_doc'),  # Редактирование документа
    path('profile/doc/<int:doc_id>/delete/', views.profile_delete_doc_view, name='profile_delete_doc'),  # Удаление документа
    
    # Личный кабинет: Управление билетами и уведомлениями
    path('profile/ticket/<int:ticket_id>/cancel/', views.profile_cancel_ticket_view, name='profile_cancel_ticket'),
    path('profile/ticket/<int:ticket_id>/add_services/', views.profile_add_services_view, name='profile_add_services'),  # Оформление возврата билета
    path('profile/notification/<int:notif_id>/delete/', views.profile_delete_notification_view, name='profile_delete_notification'),  # Удаление подписки на уведомления
    path('profile/notification/add/<int:trip_id>/', views.profile_add_notification_view, name='profile_add_notification'),  # Ручное добавление уведомления
    path('profile/notification/toggle/<int:trip_id>/', views.toggle_notification_view, name='toggle_notification'),  # Переключение статуса уведомления (колокольчик)
    path('profile/delete/', views.delete_account_view, name='delete_account'),  # Удаление аккаунта пользователя

    # Информационные страницы
    path('privacy/', views.privacy_view, name='privacy'),  # Политика конфиденциальности
]
