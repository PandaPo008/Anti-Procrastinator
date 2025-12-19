# flask_monitor.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
from datetime import date
import threading
import time
import win32gui
import win32process
import psutil
import sys

# Глобальная переменная для user_id
current_user_id = None
flask_app = None


def set_user_id(user_id):
    """Установить user_id извне (вызывается из Flet приложения)"""
    global current_user_id
    if user_id:
        current_user_id = int(user_id) if isinstance(user_id, str) and user_id.isdigit() else user_id
        print(f"✅ Установлен user_id для мониторинга: {current_user_id}")
    else:
        current_user_id = None
        print("⚠️ User_id сброшен (пользователь вышел)")


def get_user_id():
    """Получаем текущий user_id - ТОЛЬКО установленный, не из базы!"""
    global current_user_id
    return current_user_id  # Только установленный, не пытаемся получить из базы!


def create_app():
    """Создает и настраивает Flask приложение"""
    app = Flask(__name__)

    # Настройка CORS
    CORS(app, resources={
        r"/*": {
            "origins": ["chrome-extension://*", "http://127.0.0.1:*", "http://localhost:*"],
            "methods": ["GET", "POST", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"]
        }
    })

    @app.after_request
    def after_request(response):
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        return response

    DB_CONFIG = {
        "dbname": "Your_db_name",
        "user": "postgres",
        "password": "Your_password",
        "host": "localhost",
        "port": "5432"
    }

    activity_buffer = {}
    CHECK_INTERVAL = 10
    DB_SAVE_INTERVAL = 60
    browser_active = False

    # ================== Python мониторинг ==================
    def get_active_app_name():
        nonlocal browser_active
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                browser_active = False
                return None

            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process = psutil.Process(pid)
            process_name = process.name().lower()
            window_title = win32gui.GetWindowText(hwnd).strip()

            if window_title in ("Program Manager", ""):
                browser_active = False
                return None

            if process_name in ("chrome.exe", "msedge.exe", "firefox.exe"):
                browser_active = True
                return "Browser"

            browser_active = False
            return window_title or process_name.title()
        except Exception as e:
            print("Ошибка получения активного приложения:", e)
            browser_active = False
            return None

    def activity_loop():
        """Цикл отслеживания активных приложений - работает ТОЛЬКО если user_id установлен"""
        while True:
            try:
                user_id = get_user_id()
                if not user_id:
                    # Если user_id не установлен, НЕ отслеживаем
                    time.sleep(CHECK_INTERVAL)
                    continue

                app_name = get_active_app_name()
                today = date.today()
                if app_name:
                    key = (user_id, app_name, today)
                    activity_buffer[key] = activity_buffer.get(key, 0) + CHECK_INTERVAL
                    print(f"🟢 User {user_id}: {app_name} | +{CHECK_INTERVAL} сек")
            except Exception as e:
                print("Ошибка в activity_loop:", e)
            time.sleep(CHECK_INTERVAL)

    def save_loop():
        """Сохранение в БД - работает ТОЛЬКО если user_id установлен"""
        while True:
            time.sleep(DB_SAVE_INTERVAL)

            user_id = get_user_id()
            if not user_id:
                # Если user_id не установлен, НЕ сохраняем
                continue

            if not activity_buffer:
                continue

            try:
                conn = psycopg2.connect(**DB_CONFIG)
                cur = conn.cursor()
                for (user_id_key, app_name, activity_date), seconds in list(activity_buffer.items()):
                    # Сохраняем только для текущего пользователя
                    if user_id_key == user_id:
                        cur.execute("""
                            INSERT INTO activity_monitoring (user_id, app_name, total_seconds, activity_date)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (user_id, app_name, activity_date)
                            DO UPDATE SET total_seconds = activity_monitoring.total_seconds + EXCLUDED.total_seconds;
                        """, (user_id, app_name, seconds, activity_date))
                conn.commit()
                activity_buffer.clear()
                cur.close()
                conn.close()
                print("💾 Данные из буфера сохранены в БД")
            except Exception as e:
                print("Ошибка подключения к БД:", e)

    def start_monitoring():
        threading.Thread(target=activity_loop, daemon=True).start()
        threading.Thread(target=save_loop, daemon=True).start()

    # ================== ЭНДПОИНТЫ ==================
    @app.route("/")
    def home():
        user_id = get_user_id()
        return jsonify({
            "status": "running" if user_id else "waiting_for_auth",
            "service": "activity_monitor",
            "user_id": user_id,
            "message": "Авторизуйтесь в Flet приложении" if not user_id else "Мониторинг активен",
            "endpoints": {
                "/": "эта страница (GET)",
                "/log_activity": "прием данных от расширения (POST) - ТРЕБУЕТ user_id",
                "/browser_status": "статус браузера (GET)",
                "/current_user": "текущий user_id (GET)",
                "/ping": "проверка связи (GET)"
            }
        })

    @app.route("/ping", methods=["GET"])
    def ping():
        return jsonify({"status": "ok", "message": "pong", "user_id": get_user_id()})

    # ================== JS логирование ==================
    @app.route("/log_activity", methods=["POST", "OPTIONS"])
    def log_activity():
        # Обработка OPTIONS запросов для CORS
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200

        try:
            # Проверяем user_id ПЕРВЫМ делом!
            user_id = get_user_id()
            if not user_id:
                print("❌ ОТКАЗ: user_id не установлен. Авторизуйтесь в Flet приложении.")
                return jsonify({
                    "status": "error",
                    "message": "User ID не установлен. Авторизуйтесь в Flet приложении.",
                    "code": "NO_USER_ID"
                }), 403  # 403 Forbidden - доступ запрещен без авторизации

            data = request.json
            if not data:
                return jsonify({"status": "error", "message": "Нет данных"}), 400

            site_times = data.get("site_times", {})
            today = date.today()

            if not site_times:
                return jsonify({"status": "ok", "message": "Нет данных для сохранения"})

            print(f"📨 Получены данные для user {user_id}: {site_times}")

            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()
            for site, seconds in site_times.items():
                cur.execute("""
                    INSERT INTO activity_monitoring (user_id, app_name, total_seconds, activity_date)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_id, app_name, activity_date)
                    DO UPDATE SET total_seconds = activity_monitoring.total_seconds + EXCLUDED.total_seconds;
                """, (user_id, site, seconds, today))
            conn.commit()
            cur.close()
            conn.close()

            print(f"✅ Данные для user {user_id} сохранены в БД")
            return jsonify({
                "status": "ok",
                "saved_sites": len(site_times),
                "user_id": user_id
            })
        except Exception as e:
            print(f"❌ Ошибка в /log_activity: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/browser_status", methods=["GET"])
    def get_browser_status():
        return jsonify({"browser_active": browser_active, "user_id": get_user_id()})

    @app.route("/current_user", methods=["GET"])
    def get_current_user():
        user_id = get_user_id()
        return jsonify({
            "user_id": user_id,
            "has_user": bool(user_id),
            "message": "Авторизуйтесь в Flet приложении" if not user_id else "Пользователь авторизован"
        })

    # Запускаем мониторинг в фоне
    start_monitoring()

    return app


# Глобальный экземпляр приложения
flask_app = create_app()


def start_flask_monitor():
    """Запуск Flask сервера"""
    print("=" * 60)
    print("🚀 Flask Activity Monitor запускается на порту 5000")
    print("📡 Статус: ОЖИДАНИЕ АВТОРИЗАЦИИ")
    print("👉 Авторизуйтесь в Flet приложении для активации мониторинга")
    print("")
    print("🔍 Проверка статуса:")
    print("   http://127.0.0.1:5000/current_user")
    print("   http://127.0.0.1:5000/")
    print("=" * 60)

    flask_app.run(port=5000, debug=False, use_reloader=False)


if __name__ == "__main__":
    start_flask_monitor()