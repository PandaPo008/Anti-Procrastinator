import flet as ft
from flet_route import Params, Basket
import google.generativeai as genai
import psycopg2
from psycopg2 import extras
from datetime import datetime, timedelta
import json
import re

# --- 1. КОНФИГУРАЦИЯ API И БД ---

genai.configure(api_key="Your_API_KEY")
model = genai.GenerativeModel("gemini-2.5-flash")

DB_CONFIG = {
    "host": "localhost",
    "dbname": "Your_db_name",
    "user": "postgres",
    "password": "Your_password",
    "port": 5432
}


# --- 2. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ БД ---

def get_user_schedule(user_id):
    """Извлекает расписание пользователя из БД и форматирует его."""
    schedule_data = {}
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=extras.DictCursor)

        query = """
        SELECT 
            sd.day_of_week,
            st.start_time,
            st.description
        FROM 
            schedule_days sd
        JOIN 
            schedule_tasks st ON sd.id_day = st.day_id
        WHERE 
            sd.user_id = %s
        ORDER BY 
            sd.day_of_week, st.start_time;
        """
        cursor.execute(query, (user_id,))
        results = cursor.fetchall()

        # Дни недели для отображения
        days_of_week = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]

        for row in results:
            day_num = row['day_of_week']
            day_name = days_of_week[day_num - 1] if 1 <= day_num <= 7 else f"День {day_num}"
            start_time = row['start_time']
            description = row['description']

            if day_name not in schedule_data:
                schedule_data[day_name] = []
            # НОВЫЙ ФОРМАТ: время задача
            schedule_data[day_name].append(f"{start_time} {description}")

    except (Exception, psycopg2.Error) as error:
        print(f"Ошибка при работе с PostgreSQL: {error}")
        return None, f"Ошибка БД: {error}"
    finally:
        if conn:
            conn.close()

    # Форматирование расписания в строку
    formatted_schedule = ""
    if schedule_data:
        formatted_schedule = "\n\nТЕКУЩЕЕ РАСПИСАНИЕ ПОЛЬЗОВАТЕЛЯ:\n"
        for day, tasks in schedule_data.items():
            formatted_schedule += f"--- {day} ---\n"
            for task in tasks:
                formatted_schedule += f"{task}\n"
            formatted_schedule += "\n"
    else:
        formatted_schedule = "\n\nТЕКУЩЕЕ РАСПИСАНИЕ ПОЛЬЗОВАТЕЛЯ: (Расписание не найдено)\n"

    return formatted_schedule, None


def get_user_activity_data(user_id, days=7):
    """Получает данные об активности пользователя за последние N дней."""
    activity_data = {}
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=extras.DictCursor)

        # Рассчитываем дату начала периода
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days - 1)

        query = """
        SELECT 
            activity_date,
            app_name,
            total_seconds
        FROM 
            activity_monitoring
        WHERE 
            user_id = %s
            AND activity_date BETWEEN %s AND %s
        ORDER BY 
            activity_date, total_seconds DESC;
        """
        cursor.execute(query, (user_id, start_date, end_date))
        results = cursor.fetchall()

        # Группируем данные по датам
        for row in results:
            date_str = row['activity_date'].strftime("%Y-%m-%d")
            app_name = row['app_name']
            hours = row['total_seconds'] / 3600

            if date_str not in activity_data:
                activity_data[date_str] = []

            activity_data[date_str].append({
                'app': app_name,
                'hours': round(hours, 2)
            })

    except (Exception, psycopg2.Error) as error:
        print(f"Ошибка при получении данных активности: {error}")
        return None, f"Ошибка БД активности: {error}"
    finally:
        if conn:
            conn.close()

    # Форматируем данные активности
    formatted_activity = ""
    if activity_data:
        formatted_activity = "\n\n📊 СТАТИСТИКА ИСПОЛЬЗОВАНИЯ ПРИЛОЖЕНИЙ ЗА ПОСЛЕДНИЕ 7 ДНЕЙ:\n"

        # Общая статистика по приложениям за неделю
        app_totals = {}
        app_categories = categorize_apps(activity_data)

        for date_str, apps in activity_data.items():
            for app_data in apps:
                app_name = app_data['app']
                app_totals[app_name] = app_totals.get(app_name, 0) + app_data['hours']

        # Рассчитываем СРЕДНЕЕ В ДЕНЬ для каждого приложения
        days_with_data = len(activity_data)
        app_daily_average = {}
        if days_with_data > 0:
            for app_name, total_hours in app_totals.items():
                app_daily_average[app_name] = total_hours / days_with_data

        # Группируем по категориям
        productivity_time = 0
        entertainment_time = 0
        social_time = 0
        gaming_time = 0
        other_time = 0

        productivity_daily = 0
        entertainment_daily = 0
        social_daily = 0
        gaming_daily = 0
        other_daily = 0

        for app_name, total_hours in app_totals.items():
            category = app_categories.get(app_name, 'other')
            daily_avg = app_daily_average.get(app_name, 0)

            if category == 'productivity':
                productivity_time += total_hours
                productivity_daily += daily_avg
            elif category == 'entertainment':
                entertainment_time += total_hours
                entertainment_daily += daily_avg
            elif category == 'social':
                social_time += total_hours
                social_daily += daily_avg
            elif category == 'gaming':
                gaming_time += total_hours
                gaming_daily += daily_avg
            else:
                other_time += total_hours
                other_daily += daily_avg

        formatted_activity += f"\n📈 ОБЩАЯ СТАТИСТИКА ЗА НЕДЕЛЮ:\n"
        formatted_activity += f"• Игры: {round(gaming_time, 1)} часов (в среднем {round(gaming_daily, 1)} часов/день)\n"
        formatted_activity += f"• Социальные сети: {round(social_time, 1)} часов (в среднем {round(social_daily, 1)} часов/день)\n"
        formatted_activity += f"• Развлечения: {round(entertainment_time, 1)} часов (в среднем {round(entertainment_daily, 1)} часов/день)\n"
        formatted_activity += f"• Продуктивные приложения: {round(productivity_time, 1)} часов (в среднем {round(productivity_daily, 1)} часов/день)\n"
        formatted_activity += f"• Прочее: {round(other_time, 1)} часов\n"

        formatted_activity += f"\n🎯 САМЫЕ ИСПОЛЬЗУЕМЫЕ ПРИЛОЖЕНИЯ (СРЕДНЕЕ В ДЕНЬ):\n"
        # Сортируем по среднему в день
        sorted_apps = sorted(app_daily_average.items(), key=lambda x: x[1], reverse=True)

        for app_name, daily_avg in sorted_apps[:7]:
            total_hours = app_totals.get(app_name, 0)
            category = app_categories.get(app_name, 'other')
            category_icon = get_category_icon(category)
            formatted_activity += f"  {category_icon} {app_name}: {round(daily_avg, 1)} ч/день (всего {round(total_hours, 1)} ч)\n"

        # Добавляем анализ по дням
        formatted_activity += f"\n📅 ДНЕВНАЯ СТАТИСТИКА:\n"
        for date_str, apps in activity_data.items():
            day_total = sum(app['hours'] for app in apps)
            formatted_activity += f"  {date_str}: {round(day_total, 2)} часов активности\n"

    else:
        formatted_activity = "\n\n📊 Статистика активности: (Данные не найдены за последние 7 дней)\n"

    return formatted_activity, None


def categorize_apps(activity_data):
    """Категоризирует приложения по типам."""
    app_categories = {}

    # Определяем категории по ключевым словам
    gaming_keywords = ['game', 'steam', 'epic', 'origin', 'battle.net', 'dota', 'cs:', 'fortnite', 'minecraft',
                       'roblox']
    social_keywords = ['facebook', 'instagram', 'vk', 'telegram', 'whatsapp', 'messenger', 'twitter', 'x.com', 'tiktok',
                       'discord']
    entertainment_keywords = ['youtube', 'netflix', 'spotify', 'twitch', 'disney+', 'hbo', 'prime video', 'kinopoisk']
    productivity_keywords = ['word', 'excel', 'powerpoint', 'notion', 'todo', 'calendar', 'outlook', 'gmail', 'slack',
                             'teams', 'zoom', 'figma', 'photoshop']

    # Проходим по всем данным и категоризируем
    for date_str, apps in activity_data.items():
        for app_data in apps:
            app_name = app_data['app'].lower()

            if any(keyword in app_name for keyword in gaming_keywords):
                app_categories[app_data['app']] = 'gaming'
            elif any(keyword in app_name for keyword in social_keywords):
                app_categories[app_data['app']] = 'social'
            elif any(keyword in app_name for keyword in entertainment_keywords):
                app_categories[app_data['app']] = 'entertainment'
            elif any(keyword in app_name for keyword in productivity_keywords):
                app_categories[app_data['app']] = 'productivity'
            else:
                app_categories[app_data['app']] = 'other'

    return app_categories


def get_category_icon(category):
    """Возвращает иконку для категории приложения."""
    icons = {
        'gaming': '🎮',
        'social': '💬',
        'entertainment': '🎬',
        'productivity': '💼',
        'other': '📱'
    }
    return icons.get(category, '📱')


def save_ai_schedule(user_id, schedule_data_by_day):
    """Сохраняет расписание, предложенное AI, в таблицу ai_generated_schedules.
    schedule_data_by_day: словарь {день_недели: [список_задач]}
    """
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        saved_days = []

        for day_of_week, schedule_data in schedule_data_by_day.items():
            if not schedule_data:  # Пропускаем пустые дни
                continue

            # Удаляем старые записи для этого пользователя и дня недели
            delete_query = """
            DELETE FROM ai_generated_schedules 
            WHERE user_id = %s AND day_of_week = %s
            """
            cursor.execute(delete_query, (user_id, day_of_week))

            # Вставляем новое расписание
            insert_query = """
            INSERT INTO ai_generated_schedules (user_id, day_of_week, data)
            VALUES (%s, %s, %s)
            """
            cursor.execute(insert_query, (user_id, day_of_week, json.dumps(schedule_data, ensure_ascii=False)))
            saved_days.append(day_of_week)

        conn.commit()
        return saved_days, None

    except (Exception, psycopg2.Error) as error:
        if conn:
            conn.rollback()
        print(f"Ошибка при сохранении расписания AI: {error}")
        return [], f"Ошибка БД: {error}"
    finally:
        if conn:
            conn.close()


def parse_ai_response_for_schedule(ai_response):
    """Парсит ответ AI и извлекает расписание для нескольких дней."""
    # Сначала проверяем, не является ли ответ отказом
    if any(phrase in ai_response.lower() for phrase in [
        "не могу помочь", "не могу составить", "не умею",
        "не мой профиль", "это не моя задача", "не понимаю запрос",
        "извините, но", "к сожалению,", "я не специализируюсь"
    ]):
        return {}

    # Ищем все дни недели в ответе
    days_mapping = {
        'понедельник': 1, 'вторник': 2, 'среда': 3,
        'четверг': 4, 'пятница': 5, 'суббота': 6, 'воскресенье': 7
    }

    # Ищем все блоки с днями
    schedule_by_day = {}
    current_day = None
    lines = ai_response.split('\n')

    for line in lines:
        line_original = line.strip()
        line_lower = line_original.lower()

        # Ищем начало нового дня
        for day_name, day_num in days_mapping.items():
            if day_name in line_lower:
                # Проверяем, что это заголовок дня
                if ('---' in line_original or
                        line_original.startswith(day_name.capitalize()) or
                        f'день {day_num}' in line_lower or
                        'расписание на' in line_lower):

                    current_day = day_num
                    if current_day not in schedule_by_day:
                        schedule_by_day[current_day] = []
                    break

        # Если нашли временную запись и есть текущий день
        if current_day and line_original:
            # Упрощенный парсинг времени
            # Формат: "08:00 задача" или "08:00 - задача"
            if re.search(r'^\d{1,2}[:.]\d{2}', line_original):
                parts = re.split(r'[-–—\s]+', line_original, maxsplit=1)
                if len(parts) >= 2:
                    time_part = parts[0].strip()
                    description = parts[1].strip()

                    # Преобразуем 08.00 в 08:00
                    time_part = time_part.replace('.', ':')

                    # Проверяем валидность времени
                    try:
                        # Пробуем разные форматы времени
                        if ':' in time_part:
                            datetime.strptime(time_part, '%H:%M')
                        else:
                            continue

                        # Убираем звездочки из описания
                        description = description.replace('*', '').replace('•', '').strip()

                        schedule_by_day[current_day].append({
                            'time': time_part,
                            'description': description
                        })
                    except ValueError:
                        continue

    return schedule_by_day


def get_day_of_week_from_date(date_str):
    """Конвертирует строку даты в день недели (1-7)."""
    days_mapping = {
        'понедельник': 1, 'вторник': 2, 'среда': 3,
        'четверг': 4, 'пятница': 5, 'суббота': 6, 'воскресенье': 7
    }

    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        # В Python: 0=понедельник, 6=воскресенье
        day_num = date_obj.weekday() + 1  # Конвертируем в 1-7
        return day_num
    except ValueError:
        return None


def extract_days_from_query(user_query, is_logged_in=False, basket=None):
    """Извлекает дни недели из запроса пользователя с учетом дат."""
    query_lower = user_query.lower()
    found_days = []

    # Базовое маппирование дней
    days_mapping = {
        'понедельник': 1, 'вторник': 2, 'среда': 3,
        'четверг': 4, 'пятница': 5, 'суббота': 6, 'воскресенье': 7
    }

    # 1. Проверяем конкретные дни недели
    for day_name, day_num in days_mapping.items():
        if day_name in query_lower:
            found_days.append(day_num)

    # 2. Проверяем относительные дни
    today = datetime.now()

    if 'сегодня' in query_lower:
        found_days.append(today.weekday() + 1)
    elif 'завтра' in query_lower:
        tomorrow = today + timedelta(days=1)
        found_days.append(tomorrow.weekday() + 1)
    elif 'послезавтра' in query_lower:
        day_after_tomorrow = today + timedelta(days=2)
        found_days.append(day_after_tomorrow.weekday() + 1)
    elif 'в понедельник' in query_lower:
        # Находим ближайший понедельник
        days_ahead = 0 - today.weekday()  # 0 = понедельник
        if days_ahead <= 0:  # Если сегодня понедельник или позже
            days_ahead += 7
        found_days.append(1)
    elif 'во вторник' in query_lower:
        days_ahead = 1 - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        found_days.append(2)
    # и так далее для других дней

    # 3. Проверяем диапазоны
    if 'с понедельника по пятницу' in query_lower:
        found_days = [1, 2, 3, 4, 5]
    elif 'на неделю' in query_lower or 'на всю неделю' in query_lower:
        found_days = [1, 2, 3, 4, 5, 6, 7]
    elif 'на выходные' in query_lower:
        found_days = [6, 7]
    elif 'на рабочие дни' in query_lower:
        found_days = [1, 2, 3, 4, 5]

    return found_days


def is_valid_schedule_request(user_query):
    """Проверяет, является ли запрос подходящим для составления расписания."""
    query_lower = user_query.lower()

    # Ключевые слова для запросов о расписании
    schedule_keywords = [
        'расписание', 'график', 'распиши', 'составь', 'планирование',
        'на понедельник', 'на вторник', 'на среду', 'на четверг', 'на пятницу',
        'на субботу', 'на воскресенье', 'на неделю', 'на выходные',
        'тайм-менеджмент', 'организовать время', 'оптимизировать',
        'как планировать', 'управление временем', 'режим дня',
        'учеба', 'работа', 'занятия', 'тренировки', 'спорт'
    ]

    # Проверяем, содержит ли запрос ключевые слова
    for keyword in schedule_keywords:
        if keyword in query_lower:
            return True

    # Проверяем запросы о сокращении времени
    if any(word in query_lower for word in ['сократить', 'уменьшить', 'меньше', 'трачу много']):
        if any(word in query_lower for word in ['время', 'игр', 'соцсет', 'ютуб', 'телеграм']):
            return True

    # Проверяем запросы о продуктивности
    if any(word in query_lower for word in ['продуктив', 'эффектив', 'успевать', 'успеваю', 'не успеваю']):
        return True

    # Проверяем запросы о целях
    if any(word in query_lower for word in ['цель', 'хочу научиться', 'нужно добавить', 'заняться']):
        if any(word in query_lower for word in ['время', 'расписание', 'график', 'когда']):
            return True

    return False




# --- 3. ГЛАВНЫЙ ПРОМПТ ДЛЯ AI ---

AI_PROMPT = """
Ты — персональный ассистент "Анти-прокрастинатор". 
Твоя специализация — помощь с составлением расписания, тайм-менеджментом и оптимизацией времени.

ЕСЛИ ПОЛЬЗОВАТЕЛЬ ЗАДАЕТ ЗАПРОС, НЕ СВЯЗАННЫЙ С РАСПИСАНИЕМ, ТАЙМ-МЕНЕДЖМЕНТОМ ИЛИ ОПТИМИЗАЦИЕЙ ВРЕМЕНИ:
1. ВЕЖЛИВО ОТКАЖИ в помощи
2. Объясни, что ты специализируешься только на вопросах расписания и управления временем
3. Предложи переформулировать запрос или задать вопрос о расписании

ЕСЛИ ЗАПРОС СВЯЗАН С РАСПИСАНИЕМ:
1. Проанализируй активность пользователя (игры, соцсети, продуктивность)
2. Учти текущее расписание
3. Составь конкретное расписание с временными слотами

ФОРМАТИРОВАНИЕ ОТВЕТА:
1. Всегда разделяй ответ на две части: "РАСПИСАНИЕ" и "СОВЕТЫ"
2. В расписании используй формат: ВРЕМЯ ЗАДАЧА (например: 08:00 Завтрак)
3. Не используй markdown форматирование (**, __ и т.д.)
4. Не используй звездочки (*) или другие маркеры
5. Для каждого дня указывай заголовок: --- ДЕНЬ НЕДЕЛИ ---

ПРИМЕР ПРАВИЛЬНОГО ФОРМАТА:
--- ПОНЕДЕЛЬНИК ---
08:00 Подъем и зарядка
08:30 Завтрак
09:00 Работа над проектом
12:00 Обед

--- ВТОРНИК ---
08:00 Подъем
08:30 Йога
...

СОВЕТЫ:
1. Старайтесь...
2. Рекомендую...

СТИЛЬ: Всегда вежливый, дружелюбный, но четко обозначай границы своей компетенции.
"""


# --- 4. ФУНКЦИЯ ГЛАВНОЙ СТРАНИЦЫ (Home_page) ---
def Home_page(page: ft.Page, params: Params, basket: Basket):
    page.title = "Анти-Прокрастинатор: Чат-помощник"
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.window_full_screen = True
    page.scroll = ft.ScrollMode.AUTO
    page.bgcolor = "transparent"
    page.padding = 0
    page.spacing = 0

    # Определяем, авторизован ли пользователь
    USER_ID = page.get_user_id()
    is_logged_in = USER_ID is not None

    # Переменные для хранения данных
    current_ai_response = ft.Text("", size=16)
    current_schedule_data = {}
    requested_days = []

    # Список сообщений чата
    chat_messages = ft.Column(
        spacing=10,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    # Приветственное сообщение в зависимости от статуса
    if is_logged_in:
        welcome_message = ft.Container(
            content=ft.Column([
                ft.Text(
                    f"Привет! Я ваш ассистент по тайм-менеджменту",
                    size=18,
                    color=ft.Colors.BLACK87,
                    weight=ft.FontWeight.BOLD
                ),
                ft.Text(
                    "Помогу составить расписание, оптимизировать время и повысить продуктивность",
                    color=ft.Colors.BLACK87,
                    size=14
                ),
                ft.Container(height=10),
                ft.Text("Примеры запросов:", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.BLACK87,
),
                ft.Text("• Помоги меньше времени тратить на игры", size=13, color=ft.Colors.BLACK87,),
                ft.Text("• Как оптимизировать рабочий день?", size=13, color=ft.Colors.BLACK87,),
                ft.Text("• Нужно расписание на неделю", size=13, color=ft.Colors.BLACK87,),
            ]),
            padding=15,
            bgcolor=None,
            border_radius=ft.border_radius.all(15),
            border=ft.border.all(1, ft.Colors.BLUE_200),
            margin=ft.margin.only(bottom=10),
            alignment=ft.alignment.center,
        )
    else:
        welcome_message = ft.Container(
            content=ft.Column([
                ft.Text(
                    "Привет! Я ассистент по тайм-менеджменту",
                    size=18,
                    color=ft.Colors.BLACK87,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Text(
                    "Могу помочь составить расписание, но для персонализации и сохранения расписаний нужна авторизация",
                    size=14, color=ft.Colors.BLACK87,
                ),
                ft.Container(height=10),
                ft.Text("Что вы можете сделать:", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.BLACK87,
),
                ft.Text("• Получить общее расписание на день", size=13, color=ft.Colors.BLACK87,),
                ft.Text("• Получить советы по тайм-менеджменту", size=13, color=ft.Colors.BLACK87,),
                ft.Text("• Проанализировать пример расписания", size=13, color=ft.Colors.BLACK87,),

                ft.Container(height=10),

                ft.ElevatedButton(
                    "Войти / Зарегистрироваться",
                    icon=ft.Icons.LOGIN,
                    bgcolor=ft.Colors.BLUE,
                    color=ft.Colors.WHITE,
                    on_click=lambda _: page.go("/login"),
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=10),
                    )
                ),
            ]),
            padding=15,
            bgcolor=None,
            border_radius=ft.border_radius.all(15),
            border=ft.border.all(1, ft.Colors.ORANGE_200),
            margin=ft.margin.only(bottom=10),
            alignment=ft.alignment.center,
        )

    # добавляем в список сообщений
    chat_messages.controls.append(
        ft.Row(
            [welcome_message],
            alignment=ft.MainAxisAlignment.CENTER
        )
    )

    def add_message(text, is_user=False):
        """Добавляет сообщение в чат"""
        try:
            if is_user:
                # СООБЩЕНИЕ ПОЛЬЗОВАТЕЛЯ - СПРАВА
                message_container = ft.Container(
                    content=ft.Column([
                        # Заголовок с аватаркой справа
                        ft.Row([
                            ft.Container(expand=True),
                            ft.Text("Вы", size=12, color=ft.Colors.GREY_600),
                            ft.CircleAvatar(
                                content=ft.Icon(ft.Icons.PERSON),
                                radius=16,
                                color=ft.Colors.WHITE,
                                bgcolor=ft.Colors.BLUE if is_logged_in else ft.Colors.GREY,
                            ),
                        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),

                        # Сообщение пользователя
                        ft.Container(
                            content=ft.Text(text, size=15, color=ft.Colors.WHITE),  # ← ИСПРАВЛЕНО: WHITE вместо BLACK87
                            padding=ft.padding.all(12),
                            bgcolor=ft.Colors.BLUE if is_logged_in else ft.Colors.GREY,
                            border_radius=ft.border_radius.only(
                                top_left=15,
                                top_right=15,
                                bottom_left=15,
                                bottom_right=5,
                            ),
                            margin=ft.margin.only(left=50),
                        ),
                    ], spacing=5, horizontal_alignment=ft.CrossAxisAlignment.END),
                    margin=ft.margin.only(left=50, right=10, top=5, bottom=5),
                    alignment=ft.alignment.center_right,
                )
            else:
                # СООБЩЕНИЕ АССИСТЕНТА - СЛЕВА
                message_container = ft.Container(
                    content=ft.Column([
                        # Заголовок с аватаркой слева
                        ft.Row([
                            ft.CircleAvatar(
                                content=ft.Text("AI", size=10, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                                # ← Добавить цвет
                                radius=16,
                                color=ft.Colors.WHITE,
                                bgcolor=ft.Colors.GREEN,
                            ),
                            ft.Text("Ассистент", size=12, color=ft.Colors.GREY_600),
                            ft.Container(expand=True),
                        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),

                        # Сообщение ассистента
                        ft.Container(
                            content=ft.Text(text, size=15, color=ft.Colors.BLACK87),  # ← Правильно: черный на белом
                            padding=ft.padding.all(12),
                            bgcolor=ft.Colors.WHITE,
                            border_radius=ft.border_radius.only(
                                top_left=15,
                                top_right=15,
                                bottom_left=5,
                                bottom_right=15,
                            ),
                            border=ft.border.all(1, ft.Colors.GREY_300),
                            shadow=ft.BoxShadow(
                                blur_radius=2,
                                spread_radius=0,
                                offset=ft.Offset(1, 1),
                                color=ft.Colors.GREY_300,
                            ),
                            margin=ft.margin.only(right=50),
                        ),
                    ], spacing=5, horizontal_alignment=ft.CrossAxisAlignment.START),
                    margin=ft.margin.only(left=10, right=50, top=5, bottom=5),
                    alignment=ft.alignment.center_left,
                )

            chat_messages.controls.append(message_container)
            page.update()
            chat_messages.scroll_to(offset=-1, duration=300)

        except Exception as e:
            print(f"Ошибка в add_message: {e}")
            # Добавляем простое сообщение об ошибке
            error_msg = ft.Text(f"Ошибка: {str(e)[:50]}", size=14, color=ft.Colors.RED)  # ← Добавить size
            chat_messages.controls.append(error_msg)
            page.update()

    # Кнопки для сохранения (только для авторизованных)
    save_button_container = ft.Column([], visible=False)

    txt_input = ft.TextField(
        hint_text="Напишите сообщение...",
        height=50,
        expand=True,
        border_radius=ft.border_radius.all(25),
        filled=True,
        fill_color=ft.Colors.WHITE,
        border_color=ft.Colors.GREY_300,
        color=ft.Colors.BLACK87,
        content_padding=ft.padding.only(left=20, right=20),
    )

    def save_all_schedules(e, page, basket, schedule_data_by_day):
        """Сохраняет все расписания в базу данных."""
        if not is_logged_in:
            add_message("Для сохранения расписаний необходимо войти в систему",
                        is_user=False, show_auth_button=True)
            return

        USER_ID = page.get_user_id()

        if USER_ID is None:
            add_message("❌ Ошибка: не удалось определить пользователя", is_user=False)
            return

        if not schedule_data_by_day:
            add_message("❌ Нет расписаний для сохранения!", is_user=False)
            return

        add_message("💾 Сохраняю расписание...", is_user=False)

        days_to_save = schedule_data_by_day

        saved_days, error = save_ai_schedule(USER_ID, days_to_save)

        if error:
            add_message(f"Ошибка при сохранении: {error}", is_user=False)
        else:
            days_names = {1: "понедельник", 2: "вторник", 3: "среда", 4: "четверг",
                          5: "пятница", 6: "суббота", 7: "воскресенье"}
            saved_names = [days_names.get(day, f"день {day}") for day in saved_days]

            if saved_names:
                message = f"Расписание успешно сохранено!\n"
                message += f"Дни: {', '.join(saved_names)}"
                add_message(message, is_user=False)
                save_button_container.visible = False
            else:
                add_message("Не удалось сохранить расписание", is_user=False)

        page.update()

    def send_to_ai(e):
        """Отправляет запрос AI и обрабатывает ответ."""
        nonlocal current_schedule_data, requested_days

        user_text = txt_input.value.strip()
        if not user_text:
            return

        add_message(user_text, is_user=True)
        txt_input.value = ""
        page.update()

        # Проверяем тип запроса
        if not is_valid_schedule_request(user_text):
            message_text = (
                "Я специализируюсь только на вопросах расписания и управления временем.\n\n"
                "Что я могу:\n"
                "• Составление расписания на день/неделю\n"
                "• Оптимизация вашего времени\n"
                "• Рекомендации по тайм-менеджменту\n"
                "• Анализ активности в приложениях\n\n"
            )
            if not is_logged_in:
                message_text += "🔐 Для персонализированных рекомендаций и сохранения расписаний войдите в систему."

            add_message(message_text, is_user=False)
            return

        processing_msg = ft.Container(
            content=ft.Row([
                ft.ProgressRing(width=20, height=20, stroke_width=2),
                ft.Text(" Анализирую запрос...", size=14, color=ft.Colors.BLACK87,),
            ]),
            padding=10,
        )
        chat_messages.controls.append(processing_msg)
        page.update()

        try:
            # Для авторизованных: полный анализ
            if is_logged_in:
                USER_ID = page.get_user_id()
                # ИСПОЛЬЗУЕМ ОБНОВЛЕННУЮ ФУНКЦИЮ
                requested_days = extract_days_from_query(user_text, is_logged_in=True, basket=basket)
                if not requested_days:
                    requested_days = [1]

                schedule_content, schedule_error = get_user_schedule(USER_ID)
                activity_content, activity_error = get_user_activity_data(USER_ID, 7)

                if schedule_error:
                    add_message(f"Ошибка при получении расписания: {schedule_error}", is_user=False)
                    return

                days_names = {1: "понедельник", 2: "вторник", 3: "среда", 4: "четверг",
                              5: "пятница", 6: "суббота", 7: "воскресенье"}
                requested_days_str = ", ".join([days_names[day] for day in requested_days])

                prompt_with_data = (
                        AI_PROMPT +
                        f"\n\nЗАПРОШЕННЫЕ ДНИ: {requested_days_str}" +
                        schedule_content +
                        activity_content +
                        f"\n\nЗАПРОС ПОЛЬЗОВАТЕЛЯ: {user_text}" +
                        f"\n\nПОЖАЛУЙСТА, ПРОАНАЛИЗИРУЙ И СОСТАВЬ РАСПИСАНИЕ:"
                )
            else:
                # Для неавторизованных: общие советы без персонализации
                prompt_with_data = (
                        AI_PROMPT +
                        f"\n\nВНИМАНИЕ: Пользователь не авторизован, поэтому:\n"
                        f"1. НЕТ данных о его активности\n"
                        f"2. НЕТ его текущего расписания\n"
                        f"3. Давай ОБЩИЕ рекомендации\n"
                        f"4. Предложи базовое расписание\n\n"
                        f"ЗАПРОС ПОЛЬЗОВАТЕЛЯ: {user_text}" +
                        f"\n\nПОЖАЛУЙСТА, ДАЙ ОБЩИЕ РЕКОМЕНДАЦИИ:"
                )

            response = model.generate_content(prompt_with_data)
            ai_text = response.candidates[0].content.parts[0].text

            # Удаляем сообщение о обработке БЕЗ проверки типа
            if chat_messages.controls:
                chat_messages.controls.pop()  # Просто удаляем последний элемент

            if any(phrase in ai_text.lower() for phrase in [
                "извините,", "к сожалению,", "не могу помочь", "не мой профиль",
                "не умею", "не специализируюсь", "это не моя задача"
            ]):
                add_message(ai_text, is_user=False)
                return

            # Парсим расписание только для авторизованных
            if is_logged_in:
                current_schedule_data = parse_ai_response_for_schedule(ai_text)

            formatted_response = format_ai_response_for_chat(ai_text)

            # Для неавторизованных добавляем сообщение о регистрации
            if not is_logged_in:
                formatted_response += "\n\n🔐 Для персонализированных рекомендаций и сохранения расписаний войдите в систему."

            add_message(formatted_response, is_user=False)

            # Показываем кнопку сохранения только для авторизованных
            if is_logged_in and current_schedule_data:
                save_btn = ft.ElevatedButton(
                    "Сохранить это расписание",
                    icon=ft.Icons.SAVE,
                    bgcolor=ft.Colors.GREEN,
                    color=ft.Colors.WHITE,
                    on_click=lambda e: save_all_schedules(e, page, basket, current_schedule_data),
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=10),
                    )
                )

                save_button_container.controls = [
                    ft.Container(height=10),
                    save_btn
                ]
                save_button_container.visible = True

                # Просто добавляем отдельное сообщение с кнопкой
                button_msg = ft.Container(
                    content=save_button_container,
                    padding=10,
                    alignment=ft.alignment.center_left,
                    margin=ft.margin.only(left=10, right=50, top=5, bottom=5)
                )
                chat_messages.controls.append(button_msg)

        except Exception as ex:
            print(f"Ошибка в send_to_ai: {ex}")
            # Удаляем сообщение о обработке
            if chat_messages.controls:
                chat_messages.controls.pop()
            add_message(f"Ошибка при обработке запроса: {str(ex)[:100]}", is_user=False)

        page.update()

    def format_ai_response_for_chat(ai_text):
        """Форматирует ответ AI для чата, убирая markdown звездочки."""
        # Убираем markdown форматирование
        formatted = ai_text

        # Заменяем markdown заголовки
        formatted = formatted.replace('**', '').replace('__', '')

        # Убираем звездочки и маркеры списков
        formatted = re.sub(r'^\s*[*•]\s*', '', formatted, flags=re.MULTILINE)
        formatted = re.sub(r'\s*[*•]\s*$', '', formatted, flags=re.MULTILINE)

        # Добавляем emoji и улучшаем читаемость
        lines = formatted.split('\n')
        formatted_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                formatted_lines.append('')
                continue

            # Заменяем заголовки с emoji
            if 'расписание' in line.lower() and ':' in line:
                formatted_lines.append('📅 РАСПИСАНИЕ:')
            elif 'совет' in line.lower() or 'рекомендац' in line.lower():
                if ':' in line:
                    formatted_lines.append('💡 СОВЕТЫ:')
                else:
                    formatted_lines.append(f'💡 {line}')
            elif 'заключен' in line.lower() or 'итог' in line.lower():
                formatted_lines.append(f'🎯 {line}')
            else:
                # Форматируем строки с временем
                time_match = re.search(r'^(\d{1,2}:\d{2})\s+(.+)$', line)
                if time_match:
                    time_str = time_match.group(1)
                    description = time_match.group(2)
                    formatted_lines.append(f"⏰ {time_str} - {description}")
                else:
                    formatted_lines.append(line)

        return '\n'.join(formatted_lines)

    # --- UI LAYOUT В ВИДЕ ЧАТА ---
    return ft.View(
        route="/home",
        controls=[
            ft.Container(
                content=ft.Column([
                    # ШАПКА ЧАТА
                    ft.Container(
                        content=ft.Row([
                            ft.Column([
                                ft.Text(
                                    "Анти-Прокрастинатор",
                                    size=20,
                                    weight=ft.FontWeight.BOLD,
                                    color="#024E1C",
                                )
                            ], spacing=2),
                            ft.Container(expand=True),
                            # Кнопка профиля или входа в зависимости от авторизации
                            ft.IconButton(
                                icon=ft.Icons.PERSON if is_logged_in else ft.Icons.LOGIN,
                                tooltip="Профиль" if is_logged_in else "Войти",
                                icon_color=ft.Colors.BLACK87,
                                on_click=lambda _: page.go("/schedule" if is_logged_in else "/login"),
                            ),
                        ], alignment=ft.MainAxisAlignment.START),
                        padding=ft.padding.all(15),
                        bgcolor="#E7FFF0",
                        opacity=0.6,
                        border=ft.border.only(
                            bottom=ft.BorderSide(1, "#B2B2B2"),
                        ),
                        shadow=ft.BoxShadow(
                            blur_radius=1,
                            spread_radius=0,
                            offset=ft.Offset(0, 2),
                            color=ft.Colors.GREY_300,
                        ),
                    ),

                    # ОБЛАСТЬ СООБЩЕНИЙ
                    ft.Container(
                        content=chat_messages,
                        expand=True,
                        padding=ft.padding.all(15),
                    ),

                    # ПАНЕЛЬ ВВОДА
                    ft.Container(
                        content=ft.Column([
                            ft.Container(
                                content=ft.Row([
                                    txt_input,
                                    ft.IconButton(
                                        icon=ft.Icons.SEND_ROUNDED,
                                        icon_color=ft.Colors.BLUE,
                                        icon_size=30,
                                        tooltip="Отправить",
                                        on_click=send_to_ai,
                                        style=ft.ButtonStyle(
                                            shape=ft.CircleBorder(),
                                            padding=10,
                                        )
                                    ),
                                ], spacing=10),
                                padding=ft.padding.all(15),
                            ),
                        ]),
                        bgcolor="#8EE1AF",
                    ),
                ]),
                expand=True,
                gradient=ft.LinearGradient(
                    begin=ft.alignment.top_center,
                    end=ft.alignment.bottom_center,
                    colors=["#E7FFF0", "#8EE1AF"],
                ),
            ),
        ],
        padding=0,
        spacing=0,
    )
