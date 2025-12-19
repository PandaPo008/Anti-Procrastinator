import flet as ft
from route import Router
from db import init_db
import threading
import backUp
import mon  # Импортируем модуль Flask
from tg_page import TelegramBot  # Импортируем класс бота расписания
from tgAdmin import TelegramBackupBot  # Импортируем класс backup бота

# Глобальная переменная для хранения user_id
current_user_id = None
telegram_bot = None  # Глобальная ссылка на бота расписания
backup_bot = None  # Глобальная ссылка на backup бота

# Конфигурация Telegram ботов
SCHEDULE_BOT_TOKEN = 'Your_TGBOT_TOKEN'
BACKUP_BOT_TOKEN = 'Your_TGBOT_TOKEN'

DB_CONFIG = {
    "dbname": "Your_db_name",
    "user": "postgres",
    "password": "Your_password",
    "host": "localhost",
    "port": "5432"
}

BACKUP_DB_CONFIG = {
    "dbname": "postgres_backup",
    "user": "postgres",
    "password": "Your_password",
    "host": "localhost",
    "port": "5432"
}


def run_backup():
    backUp.main_backup_loop()


def run_flask_server():
    """Запуск Flask сервера в отдельном потоке"""
    try:
        # Передаем текущий user_id в Flask мониторинг
        mon.set_user_id(current_user_id)
        mon.start_flask_monitor()
    except Exception as e:
        print(f"❌ Ошибка запуска Flask мониторинга: {e}")


def run_schedule_bot():
    """Запуск Telegram бота расписания в отдельном потоке"""
    global telegram_bot
    try:
        # Создаем экземпляр бота расписания
        telegram_bot = TelegramBot(
            token=SCHEDULE_BOT_TOKEN,
            db_config=DB_CONFIG,
            on_user_authorized=lambda user_id: update_user_id(user_id)
        )
        telegram_bot.start_bot()
    except Exception as e:
        print(f"❌ Ошибка запуска Telegram бота расписания: {e}")


def run_backup_bot():
    """Запуск Telegram backup бота в отдельном потоке"""
    global backup_bot
    try:
        # Создаем экземпляр backup бота
        backup_bot = TelegramBackupBot(
            token=BACKUP_BOT_TOKEN,
            db_config=DB_CONFIG,
            backup_db_config=BACKUP_DB_CONFIG
        )
        backup_bot.start_bot()
    except Exception as e:
        print(f"❌ Ошибка запуска Telegram backup бота: {e}")


def update_user_id(user_id):
    """Обновляет user_id глобально и в Flask мониторинге"""
    global current_user_id
    current_user_id = user_id

    # Обновляем в Flask мониторинге
    try:
        mon.set_user_id(user_id)
        print(f"✅ User_id обновлен в Flask мониторинге: {user_id}")
    except:
        pass

    # Здесь можно добавить логику для Telegram бота расписания
    # Например, обновить информацию о пользователе


def create_telegram_bots_control(page):
    """Создает панель управления обоими ботами"""

    # Статус бота расписания
    schedule_status = ft.Text("Бот расписания: Запускается...", color=ft.colors.BLUE)
    schedule_users = ft.Text("Пользователей: 0", size=12)

    # Статус backup бота
    backup_status = ft.Text("Backup бот: Запускается...", color=ft.colors.BLUE)
    backup_users = ft.Text("Пользователей: 0", size=12)

    def update_bots_status():
        """Обновляет статус обоих ботов"""
        # Обновляем статус бота расписания
        if telegram_bot:
            try:
                status = telegram_bot.get_status() if hasattr(telegram_bot, 'get_status') else {}
                if status.get('running', False):
                    schedule_status.value = "Бот расписания: Работает ✅"
                    schedule_status.color = ft.colors.GREEN
                    if 'authorized_users' in status:
                        schedule_users.value = f"Пользователей: {status['authorized_users']}"
                else:
                    schedule_status.value = "Бот расписания: Остановлен ❌"
                    schedule_status.color = ft.colors.RED
            except:
                schedule_status.value = "Бот расписания: Ошибка получения статуса"
                schedule_status.color = ft.colors.ORANGE

        # Обновляем статус backup бота
        if backup_bot:
            try:
                status = backup_bot.get_status() if hasattr(backup_bot, 'get_status') else {}
                if status.get('running', False):
                    backup_status.value = "Backup бот: Работает ✅"
                    backup_status.color = ft.colors.GREEN
                    if 'authorized_users' in status:
                        backup_users.value = f"Пользователей: {status['authorized_users']}"
                else:
                    backup_status.value = "Backup бот: Остановлен ❌"
                    backup_status.color = ft.colors.RED
            except:
                backup_status.value = "Backup бот: Ошибка получения статуса"
                backup_status.color = ft.colors.ORANGE

        schedule_status.update()
        schedule_users.update()
        backup_status.update()
        backup_users.update()

    def restart_schedule_bot(e):
        """Перезапуск бота расписания"""
        if telegram_bot:
            telegram_bot.stop_bot()
        schedule_status.value = "Бот расписания: Перезапуск..."
        schedule_status.color = ft.colors.YELLOW
        schedule_status.update()

        threading.Thread(target=run_schedule_bot, daemon=True).start()

        # Обновляем статус через 3 секунды
        import time
        time.sleep(3)
        update_bots_status()

    def restart_backup_bot(e):
        """Перезапуск backup бота"""
        if backup_bot:
            backup_bot.stop_bot()
        backup_status.value = "Backup бот: Перезапуск..."
        backup_status.color = ft.colors.YELLOW
        backup_status.update()

        threading.Thread(target=run_backup_bot, daemon=True).start()

        # Обновляем статус через 3 секунды
        import time
        time.sleep(3)
        update_bots_status()

    # Контейнер для бота расписания
    schedule_card = ft.Container(
        content=ft.Column([
            ft.Text("📅 Бот расписания", weight=ft.FontWeight.BOLD),
            ft.Divider(height=5),
            schedule_status,
            schedule_users,
            ft.ElevatedButton(
                "Перезапустить",
                icon=ft.icons.REFRESH,
                on_click=restart_schedule_bot,
                width=150
            )
        ]),
        padding=15,
        border=ft.border.all(1, ft.colors.BLUE_100),
        border_radius=10,
        bgcolor=ft.colors.BLUE_50
    )

    # Контейнер для backup бота
    backup_card = ft.Container(
        content=ft.Column([
            ft.Text("💾 Backup бот", weight=ft.FontWeight.BOLD),
            ft.Divider(height=5),
            backup_status,
            backup_users,
            ft.ElevatedButton(
                "Перезапустить",
                icon=ft.icons.REFRESH,
                on_click=restart_backup_bot,
                width=150
            )
        ]),
        padding=15,
        border=ft.border.all(1, ft.colors.GREEN_100),
        border_radius=10,
        bgcolor=ft.colors.GREEN_50
    )

    # Основной контейнер
    return ft.Container(
        content=ft.Column([
            ft.Text("🤖 Управление Telegram ботами",
                    size=24, weight=ft.FontWeight.BOLD),
            ft.Divider(),
            ft.Row([
                schedule_card,
                backup_card
            ], spacing=20),
            ft.Row([
                ft.ElevatedButton(
                    "Обновить статусы",
                    icon=ft.icons.UPDATE,
                    on_click=lambda e: update_bots_status()
                ),
                ft.ElevatedButton(
                    "Перезапустить всех",
                    icon=ft.icons.RESTART_ALT,
                    on_click=lambda e: [restart_schedule_bot(e), restart_backup_bot(e)]
                )
            ], spacing=10),
            ft.Text(
                "Боты работают в фоновом режиме и управляют разными функциями",
                size=12,
                color=ft.colors.GREY_600
            )
        ]),
        padding=20,
        margin=10
    )


def main(page: ft.Page):
    init_db()

    # Запускаем бекап в отдельном потоке
    threading.Thread(target=run_backup, daemon=True).start()

    # Запускаем Flask мониторинг в отдельном потоке
    flask_thread = threading.Thread(target=run_flask_server, daemon=True)
    flask_thread.start()

    # Запускаем Telegram бот расписания в отдельном потоке
    schedule_thread = threading.Thread(target=run_schedule_bot, daemon=True)
    schedule_thread.start()

    # Запускаем Telegram backup бот в отдельном потоке
    backup_thread = threading.Thread(target=run_backup_bot, daemon=True)
    backup_thread.start()

    # Создаем Router и передаем функцию для обновления user_id
    router_instance = Router(page)

    # Добавляем метод для обновления user_id в page
    def set_user_id_global(user_id):
        update_user_id(user_id)

    page.set_user_id_global = set_user_id_global

    # Добавляем панель управления ботами в интерфейс
    # В зависимости от вашей архитектуры Router, вы можете:
    # 1. Добавить как отдельную страницу
    # 2. Добавить как секцию на существующую страницу
    # 3. Создать отдельный маршрут

    # Пример добавления в Router (если у вас есть метод для создания страниц):
    if hasattr(router_instance, 'add_telegram_page'):
        bot_control_panel = create_telegram_bots_control(page)
        router_instance.add_telegram_page(bot_control_panel)

    # Даем время на запуск
    import time
    time.sleep(2)

    # Проверка запуска потоков
    status_messages = []

    if flask_thread.is_alive():
        status_messages.append("✅ Flask мониторинг успешно запущен")
    else:
        status_messages.append("❌ Flask мониторинг не запустился")

    if schedule_thread.is_alive():
        status_messages.append("✅ Telegram бот расписания успешно запущен")
    else:
        status_messages.append("❌ Telegram бот расписания не запустился")

    if backup_thread.is_alive():
        status_messages.append("✅ Telegram backup бот успешно запущен")
    else:
        status_messages.append("❌ Telegram backup бот не запустился")

    # Выводим все статусы
    for msg in status_messages:
        print(msg)

    # Периодическое обновление статуса ботов
    def periodic_status_update():
        while True:
            time.sleep(30)  # Каждые 30 секунд
            try:
                if page and hasattr(page, 'update'):
                    # Здесь можно обновить UI статуса ботов
                    pass
            except:
                pass

    threading.Thread(target=periodic_status_update, daemon=True).start()


def stop_application():
    """Остановка всех компонентов приложения"""
    print("🛑 Останавливаю приложение...")

    if telegram_bot:
        telegram_bot.stop_bot()

    if backup_bot:
        backup_bot.stop_bot()

    print("✅ Приложение остановлено")


if __name__ == '__main__':
    try:
        ft.app(target=main, view=ft.WEB_BROWSER)
    except KeyboardInterrupt:
        stop_application()
    except Exception as e:
        print(f"❌ Ошибка в основном приложении: {e}")
        stop_application()