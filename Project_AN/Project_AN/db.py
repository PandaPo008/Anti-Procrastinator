import psycopg2
import bcrypt


def init_db(db_name="Your_db_name"):
    conn = psycopg2.connect(
        dbname=db_name,
        user="postgres",
        password="Your_password",
        host="localhost",
        port="5432"
    )

    cur = conn.cursor()

    # ------------------ Таблицы ------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id_user SERIAL PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL
    );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS activity_monitoring (
            id SERIAL PRIMARY KEY,
            user_id INT NOT NULL
                REFERENCES users(id_user)
                ON DELETE CASCADE,
            app_name TEXT NOT NULL,
            total_seconds INT NOT NULL DEFAULT 0,
            activity_date DATE NOT NULL,
            UNIQUE (user_id, app_name, activity_date)
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users_tg (
            user_id INTEGER PRIMARY KEY,  -- PRIMARY KEY
            tg_id BIGINT NOT NULL UNIQUE,
            email TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            CONSTRAINT fk_users_tg_user
                FOREIGN KEY (user_id)
                REFERENCES users(id_user)
                ON DELETE CASCADE
        );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS schedule_days (
        id_day SERIAL PRIMARY KEY,
        user_id INT NOT NULL REFERENCES users(id_user) ON DELETE CASCADE,
        day_of_week INT NOT NULL,
        UNIQUE(user_id, day_of_week)
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS schedule_tasks (
        id_task SERIAL PRIMARY KEY,
        day_id INT NOT NULL REFERENCES schedule_days(id_day) ON DELETE CASCADE,
        description TEXT NOT NULL,
        start_time TIME(0) NOT NULL 
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS ai_generated_schedules (
        id SERIAL PRIMARY KEY,
        user_id INT NOT NULL REFERENCES users(id_user) ON DELETE CASCADE,
        day_of_week INT NOT NULL,
        data JSONB NOT NULL
    );
    """)

    # ------------------ ИНДЕКСЫ (ВАЖНО для производительности) ------------------
    print("Создаю индексы для ускорения работы...")

    # Индексы для activity_monitoring
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_activity_user_date 
        ON activity_monitoring(user_id, activity_date);
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_activity_user_app 
        ON activity_monitoring(user_id, app_name);
    """)

    # Индексы для schedule_days
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_schedule_days_user_day 
        ON schedule_days(user_id, day_of_week);
    """)

    # Индексы для schedule_tasks
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_schedule_tasks_day 
        ON schedule_tasks(day_id);
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_schedule_tasks_day_time 
        ON schedule_tasks(day_id, start_time);
    """)

    # Индекс для users
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_email 
        ON users(email);
    """)

    # Индексы для ai_generated_schedules
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_ai_schedules_user_day 
        ON ai_generated_schedules(user_id, day_of_week);
    """)


    # Индекс для users_tg
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_tg_tg_id 
        ON users_tg(tg_id);
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_tg_user_id 
        ON users_tg(user_id);
    """)

    conn.commit()

    # Проверяем созданные индексы
    cur.execute("""
        SELECT tablename, indexname, indexdef 
        FROM pg_indexes 
        WHERE schemaname = 'public' 
        ORDER BY tablename, indexname;
    """)

    indexes = cur.fetchall()
    print(f"\nСоздано {len(indexes)} индексов:")
    for table, index, definition in indexes:
        print(f"  • {index} ({table})")

    cur.close()
    conn.close()
    print("\n✅ База данных и индексы успешно созданы!")


