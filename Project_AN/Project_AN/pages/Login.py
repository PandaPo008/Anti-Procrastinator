import flet as ft
from flet_route import Params, Basket
import psycopg2
import bcrypt


def Login_page(page: ft.Page, params: Params, basket: Basket):
    # -----------------------------
    # Настройки страницы
    # -----------------------------
    page.title = "Login Page"
    page.theme_mode = "light"
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.window_full_screen = True

    color_top = "#E6FFF0"
    color_bottom = "#ADF0C3"

    # -----------------------------
    # SnackBar
    # -----------------------------
    snackbar = ft.SnackBar(ft.Text(""), open=False)
    page.snack_bar = snackbar

    def show_message(msg, is_error=False):
        snackbar.bgcolor = ft.Colors.RED if is_error else ft.Colors.GREEN
        snackbar.content = ft.Text(msg)
        snackbar.open = True
        page.update()

    # -----------------------------
    # Проверка заполнения
    # -----------------------------
    def validate(e):
        btn_login.disabled = not (user_email.value.strip() and user_password.value)
        page.update()

    # -----------------------------
    # Флаг показа пароля
    # -----------------------------
    show_password = False

    def toggle_password_visibility(e):
        nonlocal show_password
        show_password = not show_password
        user_password.password = not show_password
        visibility_icon.icon = (
            ft.Icons.VISIBILITY_OFF if user_password.password else ft.Icons.VISIBILITY
        )
        page.update()

    # -----------------------------
    # Логика входа
    # -----------------------------
    def login(e):
        email = user_email.value.strip()
        password = user_password.value

        # Валидация email
        if not email or "@" not in email:
            user_email.error_text = "Введите корректный email"
            user_email.border_color = ft.Colors.RED
            page.update()
            return

        if not password:
            user_password.error_text = "Введите пароль"
            user_password.border_color = ft.Colors.RED
            page.update()
            return

        # Сбрасываем ошибки
        user_email.error_text = None
        user_email.border_color = ft.Colors.BLACK26
        user_password.error_text = None
        user_password.border_color = ft.Colors.BLACK26
        page.update()

        try:
            conn = psycopg2.connect(
                dbname="Your_db_name",
                user="postgres",
                password="Your_password",
                host="localhost",
                port="5432"
            )
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id_user, email, password_hash FROM users WHERE email = %s",
                (email,)
            )
            user = cursor.fetchone()
            cursor.close()
            conn.close()

            if user:
                db_user_id = user[0]
                db_email = user[1]
                db_password_hash = user[2]

                # Проверяем пароль через bcrypt
                if bcrypt.checkpw(password.encode('utf-8'), db_password_hash.encode('utf-8')):
                    # Используем page.set_auth() для установки авторизации
                    if hasattr(page, 'set_auth'):
                        username = db_email.split('@')[0]
                        page.set_auth(str(db_user_id), username)

                        # Обновляем user_id в Flask мониторинге
                        if hasattr(page, 'set_user_id_global'):
                            page.set_user_id_global(str(db_user_id))

                        show_message(f"Успешный вход! Добро пожаловать, {username}!")

                        # Добавляем небольшую задержку для отображения сообщения
                        import threading
                        def redirect():
                            import time
                            time.sleep(1)
                            page.go("/home")

                        threading.Thread(target=redirect, daemon=True).start()
                    else:
                        show_message("Ошибка: функция set_auth не найдена", is_error=True)
                else:
                    user_password.error_text = "Неверный пароль"
                    user_password.border_color = ft.Colors.RED
                    user_password.value = ""
                    show_message("Неверный пароль", is_error=True)
                    page.update()
            else:
                user_email.error_text = "Пользователь не найден"
                user_email.border_color = ft.Colors.RED
                user_email.value = ""
                show_message("Пользователь с таким email не найден", is_error=True)
                page.update()

        except Exception as ex:
            show_message(f"Ошибка подключения к базе данных: {ex}", is_error=True)

    # -----------------------------
    # UI элементы
    # -----------------------------
    user_email = ft.TextField(
        hint_text="Email",
        width=500,
        height=50,
        bgcolor="#F0FFF0",
        border_radius=6,
        border_color=ft.Colors.BLACK26,
        content_padding=20,
        on_change=validate,
        on_submit=login
    )

    user_password = ft.TextField(
        hint_text="Пароль",
        password=True,
        width=454,
        height=50,
        bgcolor="#F0FFF0",
        border_radius=6,
        border_color=ft.Colors.BLACK26,
        content_padding=20,
        on_change=validate,
        on_submit=login
    )

    visibility_icon = ft.IconButton(
        icon=ft.Icons.VISIBILITY_OFF,
        on_click=toggle_password_visibility,
        icon_color=ft.Colors.BLACK45
    )

    password_row = ft.Row(
        [user_password, visibility_icon],
        spacing=5,
        alignment=ft.MainAxisAlignment.CENTER
    )

    btn_login = ft.ElevatedButton(
        text="Войти",
        width=500,
        height=50,
        bgcolor="#9AF28B",
        color=ft.Colors.BLACK,
        disabled=True,
        on_click=login,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=6),
        )
    )

    # Если пользователь уже авторизован
    auth_content = None
    if hasattr(page, 'get_user_id') and page.get_user_id():
        auth_content = ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(height=50),
                ft.Text(f"Вы уже вошли как: {page.get_username()}",
                       size=18,
                       weight=ft.FontWeight.BOLD,
                       color=ft.Colors.GREEN),
                ft.Container(height=25),
                ft.ElevatedButton(
                    "Перейти на главную",
                    on_click=lambda _: page.go("/home"),
                    width=300,
                    height=50,
                    bgcolor="#9AF28B",
                    color=ft.Colors.BLACK,
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=6),
                    )
                ),
                ft.Container(height=10),
                ft.ElevatedButton(
                    "Выйти",
                    on_click=lambda _: (page.clear_auth() if hasattr(page, 'clear_auth') else None),
                    width=200,
                    height=40,
                    color=ft.Colors.RED,
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=6),
                    )
                )
            ]
        )

    # Контент для неавторизованных пользователей
    login_content = ft.Column(
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Container(height=50),
            ft.Text("Вход", size=28, weight=ft.FontWeight.BOLD),
            ft.Container(height=25),

            user_email,
            ft.Container(height=15),

            password_row,
            ft.Container(height=25),

            btn_login,
            ft.Container(height=15),

            ft.Row(
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[
                    ft.Text("Нет аккаунта?"),
                    ft.TextButton(
                        "Регистрация",
                        on_click=lambda _: page.go("/signup")
                    ),
                ],
            ),
            ft.Container(height=10),

        ]
    )

    # Выбираем отображаемый контент
    main_content = auth_content if (hasattr(page, 'get_user_id') and page.get_user_id()) else login_content

    gradient_container = ft.Container(
        expand=True,
        alignment=ft.alignment.center,
        gradient=ft.LinearGradient(
            begin=ft.alignment.top_center,
            end=ft.alignment.bottom_center,
            colors=[color_top, color_bottom],
        ),
        content=main_content,
    )

    return ft.View(
        route="/login",
        padding=0,
        controls=[gradient_container, snackbar]
    )