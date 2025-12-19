import flet as ft
from flet_route import Params, Basket
import psycopg2
import bcrypt
from email_validator import validate_email, EmailNotValidError
import time
import threading


def SignUP_page(page: ft.Page, params: Params, basket: Basket):
    page.title = "Register"
    page.theme_mode = "light"
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.window_full_screen = True

    color_top = "#E6FFF0"
    color_bottom = "#ADF0C3"

    # ---- SnackBar (создаём один раз) ----
    snackbar = ft.SnackBar(ft.Text(""), open=False)
    page.snack_bar = snackbar

    def show_message(msg, is_error=False):
        snackbar.bgcolor = ft.Colors.RED if is_error else ft.Colors.GREEN
        snackbar.content = ft.Text(msg)
        snackbar.open = True
        page.update()

    # -----------------------------
    # Проверка email формата
    # -----------------------------
    ALLOWED_DOMAINS = [
        "gmail.com",
        "mail.ru",
        "yandex.ru",
        "outlook.com",
        "yahoo.com"
    ]

    def is_valid_email(email):
        try:
            v = validate_email(email)
            domain = v.domain.lower()
            return domain in ALLOWED_DOMAINS
        except EmailNotValidError:
            return False

    # -----------------------------
    # Флаг показа пароля
    # -----------------------------
    show_password = False

    # -----------------------------
    # Регистрация пользователя
    # -----------------------------
    def register(e):
        email = user_email.value.strip()
        password = user_password.value

        # Проверка email
        if not is_valid_email(email):
            show_message("Некорректный Email", is_error=True)
            return

        # Проверка пароля
        if len(password) < 4:
            show_message("Некорректный пароль. Минимум 4 символа.", is_error=True)
            return

        # Хэшируем пароль
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

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
                "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id_user",
                (email, password_hash)
            )

            user_id = cursor.fetchone()[0]
            conn.commit()
            cursor.close()
            conn.close()

            username = email.split('@')[0]

            # ✅ ВАЖНО: Сохраняем в session
            page.session.set("user_id", str(user_id))
            page.session.set("username", username)

            # ✅ ВАЖНО: Сохраняем в basket
            basket.user_data = {
                "user_id": str(user_id),
                "username": username,
                "email": email
            }

            # ✅ ВАЖНО: Вызываем глобальный колбэк для Flask мониторинга
            if hasattr(page, 'set_user_id_global'):
                page.set_user_id_global(str(user_id))
                print(f"SignUP: Отправлен user_id={user_id} в глобальный колбэк")
            else:
                print("Ошибка: set_user_id_global не найден на page")

            # ✅ ВАЖНО: Также используем set_auth если он доступен
            if hasattr(page, 'set_auth'):
                page.set_auth(str(user_id), username)
            else:
                print("Ошибка: set_auth не найден на page")

            show_message(f"Регистрация успешна! Добро пожаловать, {username}!")

            # Перенаправляем на главную через 1 секунду
            def redirect():
                time.sleep(1)
                page.go("/home")

            threading.Thread(target=redirect, daemon=True).start()

            # Очищаем поля
            user_email.value = ""
            user_password.value = ""
            btn_reg.disabled = True

        except psycopg2.errors.UniqueViolation:
            show_message("Такой Email уже зарегистрирован", is_error=True)
        except Exception as e:
            show_message(f"Ошибка: {e}", is_error=True)

    # -----------------------------
    # Проверка на заполнение
    # -----------------------------
    def validate(e):
        btn_reg.disabled = not (user_email.value.strip() and user_password.value)
        page.update()

    # -----------------------------
    # Показ / скрытие пароля
    # -----------------------------
    def toggle_password_visibility(e):
        nonlocal show_password
        show_password = not show_password
        user_password.password = not show_password
        visibility_icon.icon = ft.Icons.VISIBILITY_OFF if user_password.password else ft.Icons.VISIBILITY
        page.update()

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
        on_change=validate
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
        on_submit=register
    )

    visibility_icon = ft.IconButton(
        icon=ft.Icons.VISIBILITY_OFF,
        on_click=toggle_password_visibility
    )

    password_row = ft.Row([
        user_password,  # поле пароля
        visibility_icon
    ],
    spacing=5,
    alignment=ft.MainAxisAlignment.CENTER,)

    btn_reg = ft.ElevatedButton(
        text="Зарегистрироваться",
        width=500,
        height=50,
        bgcolor="#9AF28B",
        color=ft.Colors.BLACK,
        disabled=True,
        on_click=register
    )

    content = ft.Column(
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Container(height=100),
            ft.Text("Регистрация", size=32, weight=ft.FontWeight.BOLD),
            ft.Container(height=25),

            user_email,
            ft.Container(height=15),

            password_row,
            ft.Container(height=25),

            btn_reg,
            ft.Container(height=15),

            ft.Row(
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[
                    ft.Text("Уже есть аккаунт?"),
                    ft.TextButton(
                        "Войти",
                        on_click=lambda _: page.go("/login")
                    ),
                ]
            )

        ]
    )

    gradient_container = ft.Container(
        expand=True,
        alignment=ft.alignment.center,
        gradient=ft.LinearGradient(
            begin=ft.alignment.top_center,
            end=ft.alignment.bottom_center,
            colors=[color_top, color_bottom],
        ),
        content=content,
    )

    return ft.View(
        route="/signup",
        padding=0,
        controls=[gradient_container, snackbar]
    )