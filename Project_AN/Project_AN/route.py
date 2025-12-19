import flet as ft
from flet_route import Routing, path, Basket
from functools import wraps

from pages.Login import Login_page
from pages.SignUp import SignUP_page
from pages.home import Home_page
from pages.loading import Loading_page
from pages.schedule import Schedule_page
from pages.Detaiz_page import Detalization_page


class Router:
    def __init__(self, page: ft.Page):
        self.page = page
        self.user_id = None
        self.username = None

        def auth_required(view_func):
            @wraps(view_func)
            def wrapper(page: ft.Page, basket: Basket, params):
                if not self.user_id:
                    print(f"Пользователь не авторизован. Перенаправление на /login")
                    page.go("/login")
                    return ft.View(route="/login", controls=[])
                basket.user_id = self.user_id
                basket.username = self.username
                return view_func(page, basket, params)

            return wrapper

        # ✅ ВАЖНО: Добавляем функцию глобального колбэка для всех страниц
        def set_user_id_global(user_id: str):
            """Глобальная функция для установки user_id из любых страниц"""
            self.user_id = user_id
            print(f"Router: Получен user_id = {user_id} из глобального колбэка")

            # ✅ Тут можно добавить вызов к Flask мониторингу
            # Пример: если у вас есть объект flask_monitor
            # flask_monitor.set_current_user(user_id)

            # Также сохраняем в session для надежности
            page.session.set("global_user_id", user_id)

        # Функции для управления авторизацией
        def set_auth(user_id: str, username: str):
            """Устанавливает данные авторизации"""
            self.user_id = user_id
            self.username = username
            print(f"Пользователь авторизован: {username} (ID: {user_id})")

            # ✅ Сохраняем в session
            page.session.set("user_id", user_id)
            page.session.set("username", username)

            # ✅ Вызываем глобальный колбэк
            set_user_id_global(user_id)

            # После установки авторизации перенаправляем на главную страницу
            page.go("/home")

        def clear_auth():
            """Очищает данные авторизации"""
            self.user_id = None
            self.username = None
            print("Данные авторизации очищены")

            # ✅ Очищаем session
            page.session.remove("user_id")
            page.session.remove("username")
            page.session.remove("global_user_id")

            # ✅ Очищаем через глобальный колбэк
            set_user_id_global(None)

            # Перенаправляем на страницу логина
            page.go("/login")

        # Передаем функции управления авторизацией в page
        self.page.set_auth = set_auth
        self.page.clear_auth = clear_auth
        self.page.get_user_id = lambda: self.user_id
        self.page.get_username = lambda: self.username

        # ✅ ВАЖНО: Добавляем глобальный колбэк в page для доступа из Login.py и SignUP.py
        self.page.set_user_id_global = set_user_id_global

        # Определяем все роуты
        self.app_routes = [
            path(url="/", clear=True, view=self.public_redirect),
            path(url="/home", clear=False, view=self.public_home),
            path(url="/loading", clear=False, view=Loading_page),
            path(url="/login", clear=True, view=Login_page),
            path(url="/signup", clear=False, view=SignUP_page),
            path(url="/schedule", clear=False, view=auth_required(Schedule_page)),
            path(url="/detaliz", clear=True, view=auth_required(Detalization_page)),
        ]

        Routing(
            page=self.page,
            app_routes=self.app_routes,
        )
        self.page.go("/loading")

    def public_redirect(self, page: ft.Page, basket: Basket, params):
        if self.user_id:
            page.go("/home")
        else:
            page.go("/login")
        return ft.View(route="/", controls=[])

    def public_home(self, page: ft.Page, basket: Basket, params):
        basket.is_authenticated = bool(self.user_id)
        basket.user_id = self.user_id
        basket.username = self.username
        return Home_page(page, basket, params)