# telegram_backup_bot.py
import telebot
import psycopg2
import psycopg2.extras
from telebot import types
import bcrypt
import re
from datetime import datetime
import threading
import logging
import time

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================= КОНФИГУРАЦИЯ БАЗ ДАННЫХ =================
DB_CONFIG = {
    "host": "localhost",
    "dbname": "Your_db_name",
    "user": "postgres",
    "password": "Your_password",
    "port": 5432
}

BACKUP_DB_CONFIG = {
    "host": "localhost",
    "dbname": "postgres_backup",  # Или другое имя для резервной БД
    "user": "postgres",
    "password": "Your_password",
    "port": 5432
}


class TelegramBackupBot:
    def __init__(self, token, db_config=None, backup_db_config=None):
        self.bot = telebot.TeleBot(token)
        # Используем конфигурации по умолчанию если не переданы
        self.db_config = db_config or DB_CONFIG
        self.backup_db_config = backup_db_config or BACKUP_DB_CONFIG
        self.authorized_users = {}
        self.admin_tg_ids = set()  # Сюда будем сохранять Telegram ID админов

        # Подключения к БД
        self.conn = None
        self.backup_conn = None
        self.connect_databases()

        # Загружаем Telegram ID админов при запуске
        self.load_admin_tg_ids()

        # Регистрация обработчиков
        self.register_handlers()

        # Флаг для управления потоком
        self.running = True

    def connect_databases(self):
        """Подключение к базам данных"""
        try:
            self.conn = psycopg2.connect(**self.db_config)
            self.conn.autocommit = False
            logger.info("✅ Подключение к основной БД успешно")
            logger.info(f"📊 Основная БД: {self.db_config['dbname']}@{self.db_config['host']}:{self.db_config['port']}")
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к основной БД: {e}")
            self.conn = None

        try:
            self.backup_conn = psycopg2.connect(**self.backup_db_config)
            self.backup_conn.autocommit = False
            logger.info("✅ Подключение к резервной БД успешно")
            logger.info(
                f"📊 Резервная БД: {self.backup_db_config['dbname']}@{self.backup_db_config['host']}:{self.backup_db_config['port']}")
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к резервной БД: {e}")
            self.backup_conn = None

    def load_admin_tg_ids(self):
        """Загружаем Telegram ID админов из основной БД"""
        if not self.conn:
            return

        try:
            cursor = self.conn.cursor()

            # Проверяем, есть ли таблица admins и поле telegram_id
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'admins' AND column_name = 'telegram_id'
            """)

            if cursor.fetchone():
                cursor.execute("SELECT telegram_id FROM admins WHERE telegram_id IS NOT NULL")
                tg_ids = cursor.fetchall()
                self.admin_tg_ids = {str(tg_id[0]) for tg_id in tg_ids if tg_id[0]}
                logger.info(f"✅ Загружено {len(self.admin_tg_ids)} Telegram ID админов")
            else:
                logger.warning("⚠ В таблице admins нет поля telegram_id")

            cursor.close()
        except Exception as e:
            logger.error(f"❌ Ошибка при загрузке Telegram ID админов: {e}")

    def is_admin_by_tg_id(self, tg_id):
        """Проверяет, является ли пользователь админом по Telegram ID"""
        # Проверяем в загруженных ID
        if str(tg_id) in self.admin_tg_ids:
            return True

        # Дополнительная проверка в базе
        if not self.conn:
            return False

        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM admins WHERE telegram_id = %s", (tg_id,))
            result = cursor.fetchone()
            cursor.close()
            return result[0] > 0 if result else False
        except:
            return False

    def register_handlers(self):
        """Регистрация всех обработчиков сообщений"""

        @self.bot.message_handler(commands=['start'])
        def start(message):
            self.handle_start(message)

        @self.bot.message_handler(func=lambda message: True)
        def buttons(message):
            self.handle_buttons(message)

    # ================= ОБРАБОТЧИК СТАРТА =================
    def handle_start(self, message):
        tg_id = message.chat.id

        # Проверяем, есть ли пользователь в списке админов
        if self.is_admin_by_tg_id(tg_id):
            self.authorized_users[tg_id] = True
            self.bot.send_message(
                message.chat.id,
                f"👑 Добро пожаловать, администратор!\n\n"
                f"Вы можете восстановить данные из резервной копии.\n\n"
                f"📊 Статус подключений:\n"
                f"• Основная БД: {'✅' if self.conn else '❌'}\n"
                f"• Резервная БД: {'✅' if self.backup_conn else '❌'}",
                reply_markup=self.login_keyboard()
            )
        else:
            self.authorized_users[tg_id] = False
            welcome_text = (
                "🔐 Бот для восстановления данных\n\n"
                "Этот бот предназначен только для администраторов.\n"
                "Для получения доступа свяжитесь с администратором системы.\n\n"
                "📊 Статус подключений:\n"
                f"• Основная БД: {'✅' if self.conn else '❌'}\n"
                f"• Резервная БД: {'✅' if self.backup_conn else '❌'}"
            )
            self.bot.send_message(
                message.chat.id,
                welcome_text,
                reply_markup=self.start_keyboard()
            )

    # ================= ФУНКЦИИ ДЛЯ СБОРА ДАННЫХ =================
    def get_first_name(self, message):
        user_data = {"first_name": message.text.strip()}
        if not user_data["first_name"]:
            self.bot.send_message(message.chat.id, "Неправильный формат. Введите имя заново:")
            self.bot.register_next_step_handler(message, self.get_first_name)
            return
        self.bot.send_message(message.chat.id, "Введите вашу фамилию:")
        self.bot.register_next_step_handler(message, self.get_last_name, user_data)

    def get_last_name(self, message, user_data):
        user_data["last_name"] = message.text.strip()
        if not user_data["last_name"]:
            self.bot.send_message(message.chat.id, "Неправильный формат. Введите фамилию заново:")
            self.bot.register_next_step_handler(message, self.get_last_name, user_data)
            return
        self.bot.send_message(message.chat.id, "Введите ваш email:")
        self.bot.register_next_step_handler(message, self.get_email, user_data)

    def get_email(self, message, user_data):
        user_data["email"] = message.text.strip()
        if not re.match(r"[^@]+@[^@]+\.[^@]+", user_data["email"]):
            self.bot.send_message(message.chat.id, "Неправильный формат email. Попробуйте снова:")
            self.bot.register_next_step_handler(message, self.get_email, user_data)
            return
        self.bot.send_message(message.chat.id, "Введите дату рождения (YYYY-MM-DD):")
        self.bot.register_next_step_handler(message, self.get_birth_date, user_data)

    def get_birth_date(self, message, user_data):
        user_data["birth_date"] = message.text.strip()
        try:
            datetime.strptime(user_data["birth_date"], "%Y-%m-%d")
        except ValueError:
            self.bot.send_message(message.chat.id, "Неправильный формат даты. Используйте YYYY-MM-DD:")
            self.bot.register_next_step_handler(message, self.get_birth_date, user_data)
            return
        self.bot.send_message(message.chat.id, "Введите пароль:")
        self.bot.register_next_step_handler(message, self.get_password, user_data)

    def get_password(self, message, user_data):
        if not self.backup_conn:
            self.bot.send_message(message.chat.id, "❌ Ошибка подключения к базе данных.")
            return

        password = message.text.strip()
        if len(password) < 4:
            self.bot.send_message(message.chat.id, "Пароль слишком короткий. Введите заново:")
            self.bot.register_next_step_handler(message, self.get_password, user_data)
            return

        try:
            cur = self.backup_conn.cursor()
            cur.execute("""
                SELECT password FROM admins 
                WHERE first_name=%s AND last_name=%s AND email=%s AND birth_date=%s 
            """, (user_data["first_name"], user_data["last_name"], user_data["email"], user_data["birth_date"]))
            result = cur.fetchone()
            cur.close()

            if result and bcrypt.checkpw(password.encode(), result[0].encode()):
                self.authorized_users[message.chat.id] = True
                # Сохраняем Telegram ID в основную БД
                self.save_admin_tg_id(message.chat.id, user_data)

                self.bot.send_message(
                    message.chat.id,
                    f"✅ Добро пожаловать, {user_data['first_name']}!\n"
                    f"Теперь вы можете использовать быстрый вход.",
                    reply_markup=self.login_keyboard()
                )
            else:
                self.bot.send_message(message.chat.id, "❌ Неверные данные. Попробуйте снова.")
        except Exception as e:
            self.bot.send_message(message.chat.id, f"❌ Ошибка при проверке данных: {e}")

    def save_admin_tg_id(self, tg_id, user_data):
        """Сохраняет Telegram ID админа в основную БД"""
        if not self.conn:
            return

        try:
            cursor = self.conn.cursor()

            # Проверяем, есть ли поле telegram_id в таблице admins
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'admins' AND column_name = 'telegram_id'
            """)

            if not cursor.fetchone():
                # Добавляем поле если его нет
                cursor.execute("ALTER TABLE admins ADD COLUMN telegram_id BIGINT")
                self.conn.commit()
                logger.info("✅ Добавлено поле telegram_id в таблицу admins")

            # Обновляем Telegram ID для админа
            cursor.execute("""
                UPDATE admins 
                SET telegram_id = %s 
                WHERE first_name = %s AND last_name = %s AND email = %s AND birth_date = %s
            """, (tg_id, user_data["first_name"], user_data["last_name"], user_data["email"], user_data["birth_date"]))

            self.conn.commit()
            cursor.close()

            # Обновляем кэш
            self.admin_tg_ids.add(str(tg_id))
            logger.info(f"✅ Telegram ID {tg_id} сохранён для админа {user_data['email']}")

        except Exception as e:
            logger.error(f"❌ Ошибка при сохранении Telegram ID: {e}")
            if self.conn:
                self.conn.rollback()

    # ================= УЛУЧШЕННАЯ ФУНКЦИЯ ВОССТАНОВЛЕНИЯ =================
    def restore_from_backup(self, chat_id):
        if not self.authorized_users.get(chat_id):
            self.bot.send_message(chat_id, "❌ Пожалуйста, войдите в аккаунт перед восстановлением данных.")
            return

        if not self.backup_conn or not self.conn:
            self.bot.send_message(chat_id, "❌ Ошибка подключения к базам данных.")
            return

        try:
            self.bot.send_message(chat_id, "🔄 Начинаю восстановление данных...")

            cur_backup = self.backup_conn.cursor()
            cur_main = self.conn.cursor()

            # Получаем ВСЕ таблицы из резервной БД
            cur_backup.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema='public' AND table_type='BASE TABLE'
                ORDER BY table_name
            """)
            tables = [t[0] for t in cur_backup.fetchall()]

            if not tables:
                self.bot.send_message(chat_id, "❌ В резервной БД нет таблиц для восстановления.")
                return

            restored_tables = []
            empty_tables_restored = []
            errors = []

            for table in tables:
                try:
                    # Пропускаем таблицу admins для восстановления данных, но создаём структуру
                    skip_data = (table == 'admins')

                    # Получаем структуру таблицы
                    cur_backup.execute(f"""
                        SELECT column_name, data_type, is_nullable, column_default,
                               character_maximum_length, numeric_precision, numeric_scale
                        FROM information_schema.columns
                        WHERE table_name = %s
                        ORDER BY ordinal_position
                    """, (table,))
                    columns_info = cur_backup.fetchall()

                    # Проверяем существование таблицы в основной БД
                    cur_main.execute("""
                        SELECT 1 
                        FROM information_schema.tables 
                        WHERE table_schema='public' AND table_name=%s
                    """, (table,))

                    table_exists = cur_main.fetchone()

                    if not table_exists:
                        # Создаём таблицу с правильной структурой
                        create_columns = []
                        primary_keys = []

                        # Получаем первичные ключи
                        cur_backup.execute("""
                            SELECT kcu.column_name
                            FROM information_schema.table_constraints tc
                            JOIN information_schema.key_column_usage kcu 
                            ON tc.constraint_name = kcu.constraint_name
                            WHERE tc.table_name = %s AND tc.constraint_type = 'PRIMARY KEY'
                        """, (table,))
                        pk_columns = [row[0] for row in cur_backup.fetchall()]

                        for col_info in columns_info:
                            col_name, data_type, is_nullable, default, char_max_len, num_precision, num_scale = col_info

                            # Формируем тип данных
                            if data_type == 'character varying':
                                if char_max_len:
                                    type_def = f"VARCHAR({char_max_len})"
                                else:
                                    type_def = "TEXT"
                            elif data_type == 'numeric':
                                if num_precision and num_scale:
                                    type_def = f"NUMERIC({num_precision}, {num_scale})"
                                elif num_precision:
                                    type_def = f"NUMERIC({num_precision})"
                                else:
                                    type_def = "NUMERIC"
                            elif data_type == 'integer' and 'id' in col_name.lower() and col_name in pk_columns:
                                type_def = "SERIAL PRIMARY KEY"
                            else:
                                type_def = data_type.upper()

                            col_def = f"{col_name} {type_def}"

                            # Добавляем DEFAULT если есть
                            if default and 'nextval' not in str(default):  # Исключаем последовательности
                                col_def += f" DEFAULT {default}"

                            # Добавляем NOT NULL если нужно
                            if is_nullable == 'NO' and 'PRIMARY KEY' not in type_def:
                                col_def += " NOT NULL"

                            create_columns.append(col_def)

                        # Если нет SERIAL PRIMARY KEY, добавляем первичный ключ отдельно
                        if pk_columns and not any('SERIAL PRIMARY KEY' in col for col in create_columns):
                            create_columns.append(f"PRIMARY KEY ({', '.join(pk_columns)})")

                        create_query = f"CREATE TABLE {table} ({', '.join(create_columns)});"

                        try:
                            cur_main.execute(create_query)
                            self.conn.commit()
                            logger.info(f"✅ Создана таблица {table}")
                        except Exception as create_error:
                            self.conn.rollback()
                            logger.error(f"❌ Ошибка создания таблицы {table}: {create_error}")
                            # Пробуем создать без ограничений
                            simple_columns = []
                            for col_info in columns_info:
                                col_name, data_type, is_nullable, default, char_max_len, num_precision, num_scale = col_info
                                type_def = data_type.upper()
                                if data_type == 'character varying':
                                    type_def = 'TEXT'
                                simple_columns.append(f"{col_name} {type_def}")

                            simple_query = f"CREATE TABLE {table} ({', '.join(simple_columns)});"
                            try:
                                cur_main.execute(simple_query)
                                self.conn.commit()
                                logger.info(f"✅ Создана упрощённая таблица {table}")
                            except:
                                errors.append(f"Не удалось создать таблицу {table}")
                                continue

                    # Восстанавливаем данные (если не таблица admins)
                    if not skip_data:
                        cur_backup.execute(f"SELECT COUNT(*) FROM {table}")
                        row_count = cur_backup.fetchone()[0]

                        if row_count > 0:
                            # Получаем все данные
                            cur_backup.execute(f"SELECT * FROM {table}")
                            rows = cur_backup.fetchall()

                            # Получаем названия колонок
                            cur_backup.execute(f"""
                                SELECT column_name 
                                FROM information_schema.columns 
                                WHERE table_name=%s ORDER BY ordinal_position
                            """, (table,))
                            columns = [c[0] for c in cur_backup.fetchall()]

                            # Очищаем таблицу перед восстановлением
                            try:
                                cur_main.execute(f"TRUNCATE TABLE {table} CASCADE")
                            except:
                                pass  # Игнорируем ошибки очистки

                            # Вставляем данные
                            placeholders = ", ".join(["%s"] * len(columns))
                            insert_columns = ", ".join(columns)

                            insert_query = f"INSERT INTO {table} ({insert_columns}) VALUES ({placeholders})"

                            try:
                                # Используем execute_batch для эффективной вставки
                                psycopg2.extras.execute_batch(cur_main, insert_query, rows)
                                self.conn.commit()
                                restored_tables.append((table, row_count))
                                logger.info(f"✅ Восстановлена таблица {table} ({row_count} записей)")
                            except Exception as insert_error:
                                self.conn.rollback()
                                logger.error(f"❌ Ошибка вставки в таблицу {table}: {insert_error}")
                                errors.append(f"Ошибка вставки в {table}: {str(insert_error)[:100]}")
                        else:
                            # Таблица существует но пустая
                            empty_tables_restored.append(table)
                            logger.info(f"ℹ Таблица {table} пустая в резервной копии")

                    # Восстанавливаем последовательности
                    if 'id' in table.lower() or table.endswith('_id'):
                        try:
                            cur_backup.execute(f"SELECT pg_get_serial_sequence('{table}', 'id')")
                            seq = cur_backup.fetchone()
                            if seq and seq[0]:
                                cur_main.execute(
                                    f"SELECT setval('{seq[0]}', (SELECT COALESCE(MAX(id), 1) FROM {table}))")
                                self.conn.commit()
                        except:
                            pass  # Игнорируем ошибки последовательностей

                except Exception as e:
                    error_msg = f"❌ Ошибка при восстановлении таблицы {table}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    if self.conn:
                        self.conn.rollback()

            cur_backup.close()
            cur_main.close()

            # Формируем отчёт
            report = "📊 Отчёт о восстановлении:\n\n"

            if restored_tables:
                report += "✅ Восстановлены таблицы с данными:\n"
                for table, count in restored_tables:
                    report += f"   • {table}: {count} записей\n"
                report += "\n"

            if empty_tables_restored:
                report += "ℹ Созданы/проверены пустые таблицы:\n"
                for table in empty_tables_restored:
                    report += f"   • {table}\n"
                report += "\n"

            if errors:
                report += "⚠ Возникшие ошибки:\n"
                for i, error in enumerate(errors[:10], 1):  # Показываем первые 10 ошибок
                    report += f"   {i}. {error}\n"
                if len(errors) > 10:
                    report += f"   ... и ещё {len(errors) - 10} ошибок\n"

            report += f"\n📈 Итого: {len(restored_tables)} таблиц с данными, "
            report += f"{len(empty_tables_restored)} пустых таблиц, "
            report += f"{len(errors)} ошибок"

            self.bot.send_message(chat_id, report)

            # Отправляем сводку
            total_records = sum(count for _, count in restored_tables)
            summary = (
                f"🎉 Восстановление завершено!\n\n"
                f"• Всего обработано таблиц: {len(tables)}\n"
                f"• Восстановлено записей: {total_records}\n"
                f"• Успешных таблиц: {len(restored_tables)}\n"
                f"• Ошибок: {len(errors)}"
            )
            self.bot.send_message(chat_id, summary)

        except Exception as e:
            logger.error(f"❌ Критическая ошибка восстановления: {e}")
            self.bot.send_message(chat_id, f"⚠ Критическая ошибка восстановления: {e}")

    # ================= ОБРАБОТЧИК КНОПОК =================
    def handle_buttons(self, message):
        if message.text == "Вход":
            # Проверяем, есть ли пользователь в списке админов по Telegram ID
            if self.is_admin_by_tg_id(message.chat.id):
                self.authorized_users[message.chat.id] = True
                self.bot.send_message(
                    message.chat.id,
                    "✅ Вы авторизованы!",
                    reply_markup=self.login_keyboard()
                )
            else:
                self.bot.send_message(message.chat.id, "Введите ваше имя для входа:")
                self.bot.register_next_step_handler(message, self.get_first_name)

        elif message.text == "Выход":
            if self.authorized_users.get(message.chat.id):
                self.authorized_users[message.chat.id] = False
                self.bot.send_message(
                    message.chat.id,
                    "Вы вышли из аккаунта.",
                    reply_markup=self.start_keyboard()
                )

        elif message.text == "Восстановить данные":
            self.restore_from_backup(message.chat.id)

    # ================= КНОПКИ =================
    def start_keyboard(self):
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add(types.KeyboardButton("Вход"))
        return keyboard

    def login_keyboard(self):
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add(types.KeyboardButton("Восстановить данные"))
        keyboard.add(types.KeyboardButton("Выход"))
        return keyboard

    # ================= УПРАВЛЕНИЕ БОТОМ =================
    def start_bot(self):
        """Запуск бота в отдельном потоке"""
        logger.info("🤖 Backup бот запускается...")
        self.running = True

        def poll():
            try:
                while self.running:
                    try:
                        # Убрали параметр restart_on_change
                        self.bot.infinity_polling(timeout=30, long_polling_timeout=30)
                    except Exception as e:
                        logger.error(f"❌ Ошибка polling: {e}")
                        if self.running:
                            time.sleep(5)  # Пауза перед перезапуском
                            continue
                        else:
                            break
            except KeyboardInterrupt:
                logger.info("🛑 Бот остановлен по запросу")
            except Exception as e:
                logger.error(f"❌ Критическая ошибка: {e}")

        # Запускаем polling в отдельном потоке
        self.poll_thread = threading.Thread(target=poll, daemon=True)
        self.poll_thread.start()
        logger.info("✅ Backup бот запущен в фоновом режиме")

    def stop_bot(self):
        """Остановка бота"""
        logger.info("🛑 Останавливаю backup бота...")
        self.running = False

        # Закрываем соединения с БД
        if self.conn:
            try:
                self.conn.close()
            except:
                pass
        if self.backup_conn:
            try:
                self.backup_conn.close()
            except:
                pass

        logger.info("✅ Backup бот остановлен")

    def get_status(self):
        """Получить статус бота"""
        return {
            "running": self.running,
            "poll_thread_alive": self.poll_thread.is_alive() if hasattr(self, 'poll_thread') else False,
            "authorized_users": len([uid for uid, auth in self.authorized_users.items() if auth]),
            "admin_tg_ids": len(self.admin_tg_ids),
            "db_connected": self.conn is not None and self.backup_conn is not None
        }


# ================= ЗАПУСК БОТА =================
if __name__ == "__main__":
    # Токен вашего бота (получите у @BotFather)
    TELEGRAM_BOT_TOKEN = "8063150333:AAHBdKq-SrL0yEJ2xS6wzcpEaszQbH2k-HQ"  # Замените на реальный токен

    # Создаем и запускаем бота
    try:
        bot = TelegramBackupBot(
            token=TELEGRAM_BOT_TOKEN,
            db_config=None,  # Используется DB_CONFIG по умолчанию
            backup_db_config=None  # Используется BACKUP_DB_CONFIG по умолчанию
        )

        print("🤖 Backup бот запускается...")
        print("✅ Подключения к БД настроены")
        print(f"📊 Основная БД:")
        print(f"   Host: {DB_CONFIG['host']}")
        print(f"   Database: {DB_CONFIG['dbname']}")
        print(f"   User: {DB_CONFIG['user']}")
        print(f"   Port: {DB_CONFIG['port']}")
        print(f"📊 Резервная БД:")
        print(f"   Host: {BACKUP_DB_CONFIG['host']}")
        print(f"   Database: {BACKUP_DB_CONFIG['dbname']}")
        print(f"   User: {BACKUP_DB_CONFIG['user']}")
        print(f"   Port: {BACKUP_DB_CONFIG['port']}")

        bot.start_bot()

    except KeyboardInterrupt:
        print("\n🛑 Backup бот остановлен пользователем")
    except Exception as e:
        print(f"❌ Ошибка при запуске бота: {e}")