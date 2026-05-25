from .models import Users

def custom_user(request):
    """
    Контекстный процессор для передачи объекта текущего пользователя
    (если он авторизован) во все шаблоны Django.
    """
    user_id = request.session.get('user_id')
    if user_id:
        try:
            user = Users.objects.get(id=user_id)
            return {'current_user': user}
        except Users.DoesNotExist:
            pass
    return {'current_user': None}
