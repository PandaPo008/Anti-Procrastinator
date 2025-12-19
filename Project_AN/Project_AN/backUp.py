import psycopg2
import time
import bcrypt
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from db import init_db  # твой файл с init_db

# ================= НАСТРОЙКИ =================
MAIN_DB_CONFIG = {
    "dbname": "Your_db_name",
    "user": "postgres",
    "password": "Your_password",
    "host": "localhost",
    "port": "5432"
}
BACKUP_DB_NAME = "postgres_backup"
BACKUP_INTERVAL = 1728000  # 20 дней

# ================= СОЗДАНИЕ РЕЗЕРВНОЙ БД =================
def create_backup_db_if_not_exists():
    conn = psycopg2.connect(
        dbname="postgres",
        user=MAIN_DB_CONFIG["user"],
        password=MAIN_DB_CONFIG["password"],
        host=MAIN_DB_CONFIG["host"],
        port=MAIN_DB_CONFIG["port"]
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute(f"SELECT 1 FROM pg_database WHERE datname='{BACKUP_DB_NAME}'")
    if not cur.fetchone():
        cur.execute(f"CREATE DATABASE {BACKUP_DB_NAME}")
        print(f"✅ База {BACKUP_DB_NAME} создана")
    cur.close()
    conn.close()

# ================= ПОДКЛЮЧЕНИЕ К РЕЗЕРВНОЙ БД =================
def get_backup_conn():
    cfg = MAIN_DB_CONFIG.copy()
    cfg["dbname"] = BACKUP_DB_NAME
    return psycopg2.connect(**cfg)

# ================= СОЗДАНИЕ ТАБЛИЦЫ ADMINS =================
def create_admins_table(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id SERIAL PRIMARY KEY,
            tg_id BIGINT NOT NULL UNIQUE,
            first_name VARCHAR(50) NOT NULL,
            last_name VARCHAR(50) NOT NULL,
            email VARCHAR(100) NOT NULL UNIQUE,
            birth_date DATE,
            password VARCHAR(255) NOT NULL
        );
    """)
    conn.commit()
    cur.close()
    print("✅ Таблица admins создана/проверена в резервной БД")

# ================= ВСТАВКА СЕРВИСНОГО АДМИНА =================
def insert_admin_if_not_exists(conn):
    cur = conn.cursor()
    password_hash = bcrypt.hashpw("12345".encode(), bcrypt.gensalt()).decode()
    cur.execute("""
        INSERT INTO admins (tg_id, first_name, last_name, email, birth_date, password)
        VALUES (%s,%s,%s,%s,%s,%s)
        ON CONFLICT (tg_id) DO NOTHING;
    """, (
        1432549962,
        "Человек",
        "Человекович",
        "admin@gmail.com",
        "2007-07-07",
        password_hash
    ))
    conn.commit()
    cur.close()
    print("🔐 Администратор проверен/добавлен")

# ================= КОПИРОВАНИЕ ТАБЛИЦ =================
def backup_table(conn_main, conn_backup, table_name, unique_column):
    cur_main = conn_main.cursor()
    cur_backup = conn_backup.cursor()
    try:
        # Берём все данные из основной таблицы
        cur_main.execute(f"SELECT * FROM {table_name}")
        rows = cur_main.fetchall()
        if not rows:
            return

        # Берём колонки
        cur_main.execute(f"""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name=%s ORDER BY ordinal_position
        """, (table_name,))
        columns = [col[0] for col in cur_main.fetchall()]

        col_list = ", ".join(columns)
        placeholders = ", ".join(["%s"] * len(columns))
        update_list = ", ".join([f"{col}=EXCLUDED.{col}" for col in columns if col != unique_column])

        query = f"""
            INSERT INTO {table_name} ({col_list}) VALUES ({placeholders})
            ON CONFLICT ({unique_column}) DO UPDATE SET {update_list};
        """
        cur_backup.executemany(query, rows)
        conn_backup.commit()
        print(f"🔁 Таблица {table_name} синхронизирована")
    except Exception as e:
        print(f"⚠ Ошибка при бэкапе {table_name}: {e}")
    finally:
        cur_main.close()
        cur_backup.close()

# ================= ОСНОВНОЙ ЦИКЛ =================
def main_backup_loop():
    create_backup_db_if_not_exists()

    # Инициализация резервной БД (создание всех нужных таблиц)
    cfg = MAIN_DB_CONFIG.copy()
    cfg["dbname"] = BACKUP_DB_NAME
    init_db(cfg["dbname"])  # init_db создаёт все таблицы кроме admins, admins создаём отдельно

    # Подключение
    conn_main = psycopg2.connect(**MAIN_DB_CONFIG)
    conn_backup = get_backup_conn()

    # Создаём таблицу admins и вставляем сервисного админа
    create_admins_table(conn_backup)
    insert_admin_if_not_exists(conn_backup)

    # Таблицы для бэкапа
    tables_to_backup = [
        ("users", "id_user"),
        ("users_tg", "id_user_tg"),
        ("schedule_days", "id_day"),
        ("schedule_tasks", "id_task"),
        ("notes", "id"),
        ("ai_generated_schedules", "id"),
        ("admins", "id")
    ]

    print("🚀 Автобэкап запущен. Обновление каждые 20 дней...")
    while True:
        for table, unique_col in tables_to_backup:
            backup_table(conn_main, conn_backup, table, unique_col)
        print("✅ Бэкап выполнен")
        time.sleep(1728000)  # 20 дней

# ================= ЗАПУСК =================
if __name__ == "__main__":
    main_backup_loop()