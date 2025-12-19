# telegram_bot.py
import telebot
import psycopg2
from psycopg2 import Error
from telebot import types
import bcrypt
import threading
import time
from datetime import datetime
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ================= КОНФИГУРАЦИЯ БД =================
DB_CONFIG = {
    "host": "localhost",
    "dbname": "Your_db_name",
    "user": "postgres",
    "password": "Your_password",
    "port": 5432
}


class TelegramBot:
    def __init__(self, token, db_config=None, on_user_authorized=None):
        self.bot = telebot.TeleBot(token)
        # Используем DB_CONFIG если не передана другая конфигурация
        self.db_config = db_config or DB_CONFIG
        self.on_user_authorized = on_user_authorized  # Callback при авторизации

        # Подключение к БД
        try:
            self.conn = psycopg2.connect(**self.db_config)
            self.conn.autocommit = True
            logger.info("✅ Подключение к PostgreSQL успешно")
        except Error as e:
            logger.error(f"❌ Ошибка БД: {e}")
            self.conn = None

        # Стейты
        self.user_states = {}
        self.user_temp = {}
        self.authorized_users = set()

        # Регистрация обработчиков
        self.register_handlers()

    def register_handlers(self):
        # START
        @self.bot.message_handler(commands=['start', 'help'])
        def start(message):
            self.handle_start(message)

        # CHECK (для отладки)
        @self.bot.message_handler(commands=['check'])
        def check_schedule(message):
            self.handle_check_schedule(message)

        # ВЫХОД
        @self.bot.message_handler(func=lambda m: m.text == "Выйти")
        def logout(message):
            self.handle_logout(message)

        # ПРОСМОТР РАСПИСАНИЯ
        @self.bot.message_handler(func=lambda m: m.text == "Посмотреть расписание")
        def show_schedule_days(message):
            self.handle_show_schedule_days(message)

        # ВХОД
        @self.bot.message_handler(func=lambda m: m.text == "Вход")
        def login_start(message):
            self.handle_login_start(message)

        # РЕГИСТРАЦИЯ
        @self.bot.message_handler(func=lambda m: m.text == "Регистрация")
        def register_start(message):
            self.handle_register_start(message)

        # ОБРАБОТКА ПАРОЛЯ (вход)
        @self.bot.message_handler(func=lambda m: self.user_states.get(m.from_user.id) == "login_password")
        def login_password(message):
            self.handle_login_password(message)

        # ОБРАБОТКА EMAIL (регистрация)
        @self.bot.message_handler(func=lambda m: self.user_states.get(m.from_user.id) == "reg_email")
        def register_email(message):
            self.handle_register_email(message)

        # ОБРАБОТКА ПАРОЛЯ (регистрация)
        @self.bot.message_handler(func=lambda m: self.user_states.get(m.from_user.id) == "reg_password")
        def register_password(message):
            self.handle_register_password(message)

        # CALLBACK для дней недели
        @self.bot.callback_query_handler(func=lambda call: call.data.isdigit())
        def get_schedule(call):
            self.handle_get_schedule(call)

    # ================= ОБРАБОТЧИКИ СООБЩЕНИЙ =================
    def handle_start(self, message):
        tg_id = message.from_user.id

        if tg_id in self.authorized_users:
            self.bot.send_message(
                message.chat.id,
                "Вы в аккаунте ✅",
                reply_markup=self.logout_keyboard()
            )
        else:
            text = (
                "👋 Добро пожаловать!\n\n"
                "🔐 Чтобы пользоваться ботом, войдите в аккаунт платформы "
                "«Анти-Прокрастинатор».\n"
                "Используйте тот же email и пароль, что и на платформе.\n\n"
                "🤖 Этот бот — ваш помощник по расписанию.\n"
                "После входа бот будет автоматически присылать напоминания\n"
                "о ваших задачах в нужное время.\n"
                "Все задачи берутся из вашего аккаунта на платформе."
            )

            self.bot.send_message(
                message.chat.id,
                text,
                reply_markup=self.main_keyboard()
            )

    def handle_check_schedule(self, message):
        """Обработчик команды /check для отладки"""
        tg_id = message.from_user.id

        if tg_id in self.authorized_users:
            response = self.force_schedule_check(tg_id)
            self.bot.send_message(message.chat.id, response)
        else:
            self.bot.send_message(message.chat.id, "Сначала авторизуйтесь!")

    def handle_logout(self, message):
        tg_id = message.from_user.id
        if tg_id in self.authorized_users:
            self.authorized_users.discard(tg_id)
            self.bot.send_message(message.chat.id, "Вы вышли из аккаунта 🚪",
                                  reply_markup=self.main_keyboard())

    def handle_show_schedule_days(self, message):
        tg_id = message.from_user.id
        if tg_id in self.authorized_users:
            self.bot.send_message(message.chat.id, "Выберите день недели:",
                                  reply_markup=self.days_inline_keyboard())
        else:
            self.bot.send_message(message.chat.id, "Сначала авторизуйтесь!",
                                  reply_markup=self.main_keyboard())

    # ================= ВХОД =================
    def handle_login_start(self, message):
        tg_id = message.from_user.id

        # Проверяем, есть ли уже привязанный аккаунт
        try:
            if not self.conn:
                self.bot.send_message(message.chat.id, "❌ Ошибка подключения к базе данных.")
                return

            cursor = self.conn.cursor()
            cursor.execute("SELECT user_id FROM users_tg WHERE tg_id = %s", (tg_id,))
            if cursor.fetchone():
                self.user_states[tg_id] = "login_password"
                self.bot.send_message(message.chat.id, "Введите пароль:")
            else:
                self.bot.send_message(message.chat.id, "У вас нет привязанного аккаунта. Сначала зарегистрируйтесь.",
                                      reply_markup=self.main_keyboard())
            cursor.close()
        except Exception as e:
            logger.error(f"Ошибка при проверке аккаунта: {e}")
            self.bot.send_message(message.chat.id, f"❌ Ошибка при проверке аккаунта: {str(e)}")

    def handle_login_password(self, message):
        tg_id = message.from_user.id
        password = message.text

        try:
            if not self.conn:
                self.bot.send_message(message.chat.id, "❌ Ошибка подключения к базе данных.")
                return

            cursor = self.conn.cursor()
            # Получаем хеш пароля из users_tg
            cursor.execute("SELECT password_hash FROM users_tg WHERE tg_id = %s", (tg_id,))
            row = cursor.fetchone()

            if row and bcrypt.checkpw(password.encode('utf-8'), row[0].encode('utf-8')):
                self.authorized_users.add(tg_id)
                cursor.execute("SELECT email FROM users_tg WHERE tg_id = %s", (tg_id,))
                email_result = cursor.fetchone()
                email = email_result[0] if email_result else "пользователь"

                # Вызываем callback если он установлен
                if self.on_user_authorized:
                    try:
                        cursor.execute("SELECT user_id FROM users_tg WHERE tg_id = %s", (tg_id,))
                        user_id_result = cursor.fetchone()
                        if user_id_result:
                            self.on_user_authorized(user_id_result[0])
                    except Exception as e:
                        logger.error(f"Ошибка в callback: {e}")

                self.bot.send_message(message.chat.id, f"Вход успешен! 👤 {email}",
                                      reply_markup=self.logout_keyboard())
            else:
                self.bot.send_message(message.chat.id, "❌ Неверный пароль")

            cursor.close()
        except Exception as e:
            logger.error(f"Ошибка при входе: {e}")
            self.bot.send_message(message.chat.id, f"❌ Произошла ошибка при входе: {str(e)}")

        self.user_states.pop(tg_id, None)

    # ================= РЕГИСТРАЦИЯ =================
    def handle_register_start(self, message):
        tg_id = message.from_user.id

        # Проверяем, не привязан ли уже аккаунт
        try:
            if not self.conn:
                self.bot.send_message(message.chat.id, "❌ Ошибка подключения к базе данных.")
                return

            cursor = self.conn.cursor()
            cursor.execute("SELECT user_id FROM users_tg WHERE tg_id = %s", (tg_id,))
            if cursor.fetchone():
                self.bot.send_message(message.chat.id, "У вас уже есть привязанный аккаунт. Используйте вход.",
                                      reply_markup=self.main_keyboard())
                cursor.close()
                return
            cursor.close()
        except Exception as e:
            logger.error(f"Ошибка при проверке: {e}")
            self.bot.send_message(message.chat.id, f"❌ Ошибка при проверке: {str(e)}")
            return

        self.user_states[tg_id] = "reg_email"
        self.bot.send_message(message.chat.id, "Введите email, который использовали при регистрации на платформе:")

    def handle_register_email(self, message):
        tg_id = message.from_user.id
        email = message.text.strip().lower()

        # Проверяем email в основной таблице users
        try:
            if not self.conn:
                self.bot.send_message(message.chat.id, "❌ Ошибка подключения к базе данных.")
                self.user_states.pop(tg_id, None)
                return

            cursor = self.conn.cursor()
            cursor.execute("SELECT id_user FROM users WHERE email = %s", (email,))
            if not cursor.fetchone():
                self.bot.send_message(message.chat.id,
                                      "❌ Аккаунт с таким email не найден. Сначала создайте аккаунт на сайте.",
                                      reply_markup=self.main_keyboard())
                self.user_states.pop(tg_id, None)
                cursor.close()
                return

            # Проверяем, не привязан ли уже этот email к другому Telegram аккаунту
            cursor.execute("SELECT tg_id FROM users_tg WHERE email = %s", (email,))
            if cursor.fetchone():
                self.bot.send_message(message.chat.id, "❌ Этот email уже привязан к другому Telegram аккаунту.",
                                      reply_markup=self.main_keyboard())
                self.user_states.pop(tg_id, None)
                cursor.close()
                return

            self.user_temp[tg_id] = {"email": email}
            self.user_states[tg_id] = "reg_password"
            self.bot.send_message(message.chat.id, "Введите пароль от вашего аккаунта:")
            cursor.close()
        except Exception as e:
            logger.error(f"Ошибка при проверке email: {e}")
            self.bot.send_message(message.chat.id, f"❌ Ошибка при проверке email: {str(e)}")

    def handle_register_password(self, message):
        tg_id = message.from_user.id
        if tg_id not in self.user_temp:
            self.bot.send_message(message.chat.id, "❌ Сессия устарела. Начните заново.",
                                  reply_markup=self.main_keyboard())
            self.user_states.pop(tg_id, None)
            return

        email = self.user_temp[tg_id]["email"]
        password = message.text

        try:
            if not self.conn:
                self.bot.send_message(message.chat.id, "❌ Ошибка подключения к базе данных.")
                self.user_states.pop(tg_id, None)
                self.user_temp.pop(tg_id, None)
                return

            cursor = self.conn.cursor()
            # Получаем пользователя и проверяем пароль
            cursor.execute("SELECT id_user, password_hash FROM users WHERE email = %s", (email,))
            row = cursor.fetchone()

            if not row:
                self.bot.send_message(message.chat.id, "❌ Аккаунт не найден.",
                                      reply_markup=self.main_keyboard())
            elif bcrypt.checkpw(password.encode('utf-8'), row[1].encode('utf-8')):
                # Привязываем Telegram аккаунт
                cursor.execute("""
                    INSERT INTO users_tg (user_id, tg_id, email, password_hash) 
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE 
                    SET tg_id = EXCLUDED.tg_id, email = EXCLUDED.email
                """, (row[0], tg_id, email, row[1]))

                self.authorized_users.add(tg_id)

                # Вызываем callback если он установлен
                if self.on_user_authorized:
                    try:
                        self.on_user_authorized(row[0])
                    except Exception as e:
                        logger.error(f"Ошибка в callback: {e}")

                self.bot.send_message(message.chat.id, "✅ Аккаунт успешно привязан!",
                                      reply_markup=self.logout_keyboard())
            else:
                self.bot.send_message(message.chat.id, "❌ Неверный пароль")

            cursor.close()
        except Exception as e:
            logger.error(f"Ошибка при регистрации: {e}")
            self.bot.send_message(message.chat.id, f"❌ Произошла ошибка при регистрации: {str(e)}")

        self.user_states.pop(tg_id, None)
        self.user_temp.pop(tg_id, None)

    # ================= ОБРАБОТКА CALLBACK =================
    def handle_get_schedule(self, call):
        tg_id = call.from_user.id

        if tg_id not in self.authorized_users:
            self.bot.send_message(call.message.chat.id, "Сначала авторизуйтесь!",
                                  reply_markup=self.main_keyboard())
            return

        day_number = int(call.data)

        try:
            if not self.conn:
                self.bot.send_message(call.message.chat.id, "❌ Ошибка подключения к базе данных.",
                                      reply_markup=self.main_keyboard())
                return

            cursor = self.conn.cursor()
            cursor.execute("SELECT user_id FROM users_tg WHERE tg_id = %s", (tg_id,))
            user_row = cursor.fetchone()
            if not user_row:
                self.bot.send_message(call.message.chat.id, "❌ Не найден пользователь.",
                                      reply_markup=self.main_keyboard())
                return
            user_id = user_row[0]

            cursor.execute("""
                SELECT schedule_tasks.description, TO_CHAR(schedule_tasks.start_time, 'HH24:MI') as start_time
                FROM schedule_tasks
                INNER JOIN schedule_days ON schedule_tasks.day_id = schedule_days.id_day
                WHERE day_of_week = %s AND user_id = %s
                ORDER BY schedule_tasks.start_time
            """, (day_number, user_id))
            tasks = cursor.fetchall()

            if tasks:
                # Получаем название дня недели
                days = ["", "Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
                day_name = days[day_number] if day_number < len(days) else f"День {day_number}"

                response = f"📅 Расписание на {day_name.lower()}:\n\n"
                for t in tasks:
                    response += f"• {t[0]} ⏰ {t[1]}\n"
            else:
                response = f"📅 На этот день задач нет."

            self.bot.send_message(call.message.chat.id, response, reply_markup=self.logout_keyboard())
            cursor.close()
        except Exception as e:
            logger.error(f"Ошибка при получении расписания: {e}")
            self.bot.send_message(call.message.chat.id, f"❌ Ошибка при получении расписания: {str(e)}",
                                  reply_markup=self.logout_keyboard())

    # ================= КЛАВИАТУРЫ =================
    def main_keyboard(self):
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(types.KeyboardButton("Вход"), types.KeyboardButton("Регистрация"))
        return kb

    def logout_keyboard(self):
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(types.KeyboardButton("Посмотреть расписание"), types.KeyboardButton("Выйти"))
        return kb

    def days_inline_keyboard(self):
        kb = types.InlineKeyboardMarkup(row_width=2)
        days = [("Понедельник", 1), ("Вторник", 2), ("Среда", 3),
                ("Четверг", 4), ("Пятница", 5), ("Суббота", 6), ("Воскресенье", 7)]
        buttons = [types.InlineKeyboardButton(text=name, callback_data=str(num)) for name, num in days]
        kb.add(*buttons)
        return kb

    # ================= ПРОВЕРКА РАСПИСАНИЯ =================
    def schedule_checker(self):
        """Проверка расписания и отправка напоминаний"""
        while True:
            try:
                now = datetime.now()
                current_time = now.strftime("%H:%M")
                day_number = now.isoweekday()

                # Логируем проверку времени (каждые 5 минут для отладки)
                if current_time.endswith(":00") or current_time.endswith(":05") or current_time.endswith(":10"):
                    logger.info(f"🕐 Проверка времени: {current_time}, день недели: {day_number}")

                if self.conn:
                    cursor = None
                    try:
                        cursor = self.conn.cursor()

                        # Получаем всех пользователей, у которых есть привязанный Telegram ID
                        cursor.execute("""
                            SELECT DISTINCT tg_id, user_id 
                            FROM users_tg 
                            WHERE tg_id IS NOT NULL AND user_id IS NOT NULL
                        """)
                        users = cursor.fetchall()

                        if current_time.endswith(":00"):
                            logger.info(f"👥 Найдено пользователей в БД: {len(users)}")

                        for tg_id, user_id in users:
                            try:
                                # Получаем задачи для этого пользователя в текущее время
                                cursor.execute("""
                                    SELECT DISTINCT 
                                        schedule_tasks.description, 
                                        TO_CHAR(schedule_tasks.start_time, 'HH24:MI') as start_time
                                    FROM schedule_tasks
                                    INNER JOIN schedule_days ON schedule_tasks.day_id = schedule_days.id_day
                                    WHERE schedule_days.day_of_week = %s 
                                    AND schedule_days.user_id = %s
                                    AND TO_CHAR(schedule_tasks.start_time, 'HH24:MI') = %s
                                    AND schedule_tasks.description IS NOT NULL
                                    AND schedule_tasks.description != ''
                                """, (day_number, user_id, current_time))

                                tasks = cursor.fetchall()

                                if tasks:
                                    logger.info(
                                        f"✅ Найдено {len(tasks)} задач для пользователя {tg_id} в {current_time}")

                                    # Отправляем напоминание для каждой задачи
                                    for task_description, task_time in tasks:
                                        try:
                                            message_text = f"⏰ Напоминание: {task_description} в {task_time}"
                                            self.bot.send_message(tg_id, message_text)
                                            logger.info(
                                                f"📤 Отправлено сообщение пользователю {tg_id}: {task_description}")
                                        except Exception as send_error:
                                            # Если пользователь заблокировал бота или произошла другая ошибка
                                            error_msg = str(send_error)
                                            if "bot was blocked" in error_msg.lower() or "chat not found" in error_msg.lower():
                                                logger.warning(
                                                    f"⚠ Пользователь {tg_id} заблокировал бота. Очищаем tg_id...")
                                                # Очищаем tg_id для этого пользователя
                                                cursor.execute("UPDATE users_tg SET tg_id = NULL WHERE user_id = %s",
                                                               (user_id,))
                                                self.conn.commit()
                                                logger.info(f"🗑️ Очищен tg_id для пользователя {user_id}")
                                            else:
                                                logger.error(f"❌ Ошибка отправки пользователю {tg_id}: {send_error}")

                            except Exception as user_error:
                                logger.error(f"❌ Ошибка обработки пользователя {tg_id}: {user_error}")
                                continue

                    except Exception as query_error:
                        logger.error(f"❌ Ошибка запроса к БД: {query_error}")
                    finally:
                        if cursor:
                            cursor.close()
                else:
                    if current_time.endswith(":00"):
                        logger.warning("⚠ Нет подключения к БД")

            except Exception as e:
                logger.error(f"❌ Общая ошибка в schedule_checker: {e}")
                # Не прерываем цикл, продолжаем работу

            # Спим 59 секунд, чтобы проверка происходила каждую минуту
            time.sleep(59)

    # ================= МЕТОД ДЛЯ ОТЛАДКИ =================
    def force_schedule_check(self, tg_id):
        """Принудительная проверка расписания для отладки"""
        try:
            now = datetime.now()
            current_time = now.strftime("%H:%M")
            day_number = now.isoweekday()

            if not self.conn:
                return "❌ Нет подключения к БД"

            cursor = None
            try:
                cursor = self.conn.cursor()

                # Получаем user_id по tg_id
                cursor.execute("SELECT user_id FROM users_tg WHERE tg_id = %s", (tg_id,))
                user_row = cursor.fetchone()

                if not user_row:
                    return "❌ Пользователь не найден в users_tg"

                user_id = user_row[0]

                # Получаем все задачи на сегодня
                cursor.execute("""
                    SELECT DISTINCT 
                        schedule_tasks.description, 
                        TO_CHAR(schedule_tasks.start_time, 'HH24:MI') as start_time
                    FROM schedule_tasks
                    INNER JOIN schedule_days ON schedule_tasks.day_id = schedule_days.id_day
                    WHERE schedule_days.day_of_week = %s 
                    AND schedule_days.user_id = %s
                    AND schedule_tasks.description IS NOT NULL
                    AND schedule_tasks.description != ''
                    ORDER BY schedule_tasks.start_time
                """, (day_number, user_id))

                tasks = cursor.fetchall()

                response = f"📅 Расписание на сегодня ({datetime.now().strftime('%d.%m.%Y')}):\n\n"

                if tasks:
                    for description, task_time in tasks:
                        response += f"• {description} ⏰ {task_time}\n"

                    # Проверяем задачи на текущее время
                    current_tasks = [t for t in tasks if t[1] == current_time]
                    if current_tasks:
                        response += f"\n✅ Найдено задач на текущее время ({current_time}): {len(current_tasks)}"
                        for task in current_tasks:
                            response += f"\n  - {task[0]}"
                    else:
                        response += f"\nℹ Нет задач на текущее время ({current_time})"

                    # Показываем следующие задачи
                    future_tasks = [t for t in tasks if t[1] > current_time]
                    if future_tasks:
                        response += f"\n\n⏭ Следующие задачи сегодня:"
                        for task in future_tasks[:3]:  # Показываем 3 следующие задачи
                            response += f"\n  - {task[0]} в {task[1]}"
                else:
                    response = f"📅 На сегодня задач нет."

                # Также показываем информацию о пользователе
                cursor.execute("SELECT email FROM users_tg WHERE tg_id = %s", (tg_id,))
                email_row = cursor.fetchone()
                email = email_row[0] if email_row else "неизвестно"

                response += f"\n\n👤 Информация:\n"
                response += f"• User ID: {user_id}\n"
                response += f"• Telegram ID: {tg_id}\n"
                response += f"• Email: {email}\n"
                response += f"• Текущее время: {current_time}\n"
                response += f"• День недели: {day_number}"

                return response

            except Exception as e:
                return f"❌ Ошибка запроса: {str(e)}"
            finally:
                if cursor:
                    cursor.close()

        except Exception as e:
            return f"❌ Ошибка: {str(e)}"

    # ================= УПРАВЛЕНИЕ БОТОМ =================
    def start_bot(self):
        """Запуск бота в отдельном потоке"""
        logger.info("🤖 Telegram бот запускается...")

        # Запуск проверки расписания в отдельном потоке
        schedule_thread = threading.Thread(target=self.schedule_checker, daemon=True)
        schedule_thread.start()
        logger.info("✅ Поток проверки расписания запущен")

        # Запуск бота
        try:
            logger.info("🤖 Начинаем polling...")
            self.bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            logger.error(f"Ошибка при запуске бота: {e}")

    def stop_bot(self):
        """Остановка бота"""
        logger.info("🛑 Telegram бот останавливается...")
        try:
            self.bot.stop_polling()
        except:
            pass

    def get_status(self):
        """Получить статус бота"""
        return {
            "running": True,
            "authorized_users": len(self.authorized_users),
            "db_connected": self.conn is not None,
            "total_users": len(self.authorized_users)
        }


# ================= ЗАПУСК БОТА =================
if __name__ == "__main__":
    # Токен вашего бота
    TELEGRAM_BOT_TOKEN = "8578502705:AAEn_F_WPHBjghJKX8qMfgmg7CfRec-aJWI"

    # Создаем и запускаем бота
    try:
        bot = TelegramBot(
            token=TELEGRAM_BOT_TOKEN,
            db_config=None,  # Используется DB_CONFIG по умолчанию
            on_user_authorized=lambda user_id: print(f"Пользователь {user_id} авторизовался")
        )

        print("=" * 50)
        print("🤖 Telegram бот для расписания")
        print("=" * 50)
        print("✅ Подключение к БД настроено")
        print(f"📊 Параметры БД:")
        print(f"   Host: {DB_CONFIG['host']}")
        print(f"   Database: {DB_CONFIG['dbname']}")
        print(f"   User: {DB_CONFIG['user']}")
        print(f"   Port: {DB_CONFIG['port']}")
        print("=" * 50)
        print("📝 Доступные команды:")
        print("   /start - Начать работу с ботом")
        print("   /check - Проверить расписание (отладка)")
        print("   Вход - Авторизация")
        print("   Регистрация - Привязать аккаунт")
        print("   Посмотреть расписание - Посмотреть задачи")
        print("   Выйти - Выйти из аккаунта")
        print("=" * 50)

        bot.start_bot()

    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен пользователем")
    except Exception as e:
        print(f"❌ Ошибка при запуске бота: {e}")