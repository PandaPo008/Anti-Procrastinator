import flet as ft
import psycopg2
from flet_route import Params, Basket
import datetime
import json
import threading
import time

# --- Настройки подключения ---
DB_CONFIG = {
    "host": "localhost",
    "dbname": "Your_db_name",
    "user": "postgres",
    "password": "Your_password",
    "port": 5432
}

# Цвета для градиента
GRADIENT_COLORS = ["#E6FFF0", "#ADF0C3"]


def Schedule_page(page: ft.Page, params: Params, basket: Basket):
    page.title = "Профиль - AntiPro"
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.theme_mode = ft.ThemeMode.LIGHT  # Изменено на LIGHT для более светлого дизайна
    page.window_full_screen = True
    page.padding = 0
    page.bgcolor = GRADIENT_COLORS[0]  # Устанавливаем цвет фона

    days = [
        "Понедельник", "Вторник", "Среда",
        "Четверг", "Пятница", "Суббота", "Воскресенье"
    ]

    week_blocks = []

    # Получаем user_id из basket (переданного из роутера)
    user_id = None
    if basket and hasattr(basket, 'user_data'):
        user_id = basket.user_data.get("user_id")

    # Если не нашли в basket, пробуем получить из client_storage
    if not user_id:
        user_id = page.get_user_id()

    # Если все еще нет user_id, перенаправляем на логин
    if not user_id:
        print("Ошибка: пользователь не авторизован")
        page.go("/login")
        return

    print(f"Пользователь авторизован (ID: {user_id})")

    # Кэш для хранения загруженных данных
    ai_schedules_cache = {}
    current_schedule_cache = {}
    conn_pool = []

    # --- Функция для получения соединения с БД (с пулом) ---
    def get_conn():
        try:
            if conn_pool:
                return conn_pool.pop()
            return psycopg2.connect(**DB_CONFIG)
        except Exception as e:
            print(f"Ошибка подключения к БД: {e}")
            return None

    # --- Функция для возврата соединения в пул ---
    def release_conn(conn):
        if conn and not conn.closed:
            conn_pool.append(conn)

    # --- Функция для быстрого выполнения запроса ---
    def execute_query(query, params=None, fetchone=False, fetchall=False, commit=False):
        conn = get_conn()
        if not conn:
            return None

        try:
            cur = conn.cursor()
            cur.execute(query, params or ())

            if commit:
                conn.commit()

            result = None
            if fetchone:
                result = cur.fetchone()
            elif fetchall:
                result = cur.fetchall()

            cur.close()
            release_conn(conn)
            return result

        except Exception as e:
            print(f"Ошибка выполнения запроса: {e}")
            if conn:
                conn.rollback()
                release_conn(conn)
            return None

    # --- Функция для отображения сообщений ---
    def show_message(text: str, color=ft.Colors.RED_ACCENT_200):
        # Закрываем предыдущий snackbar, если он открыт
        if hasattr(page, 'snack_bar') and page.snack_bar.open:
            page.snack_bar.open = False
            page.update()

        page.snack_bar = ft.SnackBar(
            content=ft.Text(text, size=14, color=ft.Colors.WHITE),
            bgcolor=color,
            action="OK",
            duration=2000
        )
        page.snack_bar.open = True
        page.update()

    # --- Создание элементов выбора времени ---
    _hours = [str(i).zfill(2) for i in range(24)]
    _minutes = [str(i).zfill(2) for i in range(0, 60, 5)]

    def create_time_picker(initial_hour: str = "", initial_minute: str = "") -> ft.Container:
        hour_dropdown = ft.Dropdown(
            width=70,
            text_size=12,
            content_padding=3,
            options=[ft.dropdown.Option(h) for h in _hours],
            value=initial_hour if initial_hour in _hours else None,
            border_color=ft.Colors.GREEN_400,
            border_radius=6,
            filled=True,
            fill_color=ft.Colors.WHITE,
        )

        minute_dropdown = ft.Dropdown(
            width=70,
            text_size=12,
            content_padding=3,
            options=[ft.dropdown.Option(m) for m in _minutes],
            value=initial_minute if initial_minute in _minutes else None,
            border_color=ft.Colors.GREEN_400,
            border_radius=6,
            filled=True,
            fill_color=ft.Colors.WHITE,
        )

        return ft.Container(
            content=ft.Row(
                controls=[hour_dropdown, ft.Text(":", size=10), minute_dropdown],
                spacing=2,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            width=140,
        )

    # --- Создание строки задачи ---
    def create_task_row(start_time: str = "", description: str = "") -> ft.Row:
        initial_hour, initial_minute = "", ""
        if start_time and ":" in start_time:
            try:
                h, m = start_time.split(":")
                initial_hour = h.zfill(2)
                initial_minute = m.zfill(2)
            except:
                pass

        time_picker = create_time_picker(initial_hour, initial_minute)

        return ft.Row(
            controls=[
                time_picker,
                ft.TextField(
                    value=description,
                    hint_text="Описание задачи",
                    expand=True,
                    text_size=12,
                    content_padding=3,
                    border_color=ft.Colors.GREEN_400,
                    border_radius=6,
                    filled=True,
                    fill_color=ft.Colors.WHITE,
                    on_change=lambda e: update_days_with_tasks_dropdown()
                ),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    # --- Получение времени из строки задачи ---
    def get_time_from_row(row: ft.Row) -> str:
        try:
            time_container = row.controls[0]
            time_row = time_container.content
            hour_dropdown = time_row.controls[0]
            minute_dropdown = time_row.controls[2]

            hour = hour_dropdown.value
            minute = minute_dropdown.value

            if hour and minute:
                return f"{hour}:{minute}"
            return ""
        except:
            return ""

    # --- Получение текущего графика из БД с кэшированием ---
    def get_current_schedule_from_db(day_index: int):
        cache_key = f"current_{user_id}_{day_index}"

        if cache_key in current_schedule_cache:
            return current_schedule_cache[cache_key]

        try:
            result = execute_query("""
                SELECT st.start_time, st.description 
                FROM schedule_days sd 
                JOIN schedule_tasks st ON sd.id_day = st.day_id 
                WHERE sd.user_id = %s AND sd.day_of_week = %s 
                ORDER BY st.start_time
            """, (user_id, day_index), fetchall=True)

            tasks = []
            if result:
                for start_time, description in result:
                    if isinstance(start_time, datetime.time):
                        time_str = start_time.strftime("%H:%M")
                    else:
                        time_str = str(start_time)[:5]
                    tasks.append(f"{time_str} - {description}")

            current_schedule_cache[cache_key] = tasks
            return tasks

        except Exception as ex:
            print(f"Ошибка при получении графика: {ex}")
            return []

    # --- Получение AI-графика с кэшированием ---
    def get_ai_schedule(day_index: int):
        cache_key = f"ai_{user_id}_{day_index}"

        if cache_key in ai_schedules_cache:
            return ai_schedules_cache[cache_key]

        try:
            result = execute_query(
                "SELECT data FROM ai_generated_schedules WHERE user_id = %s AND day_of_week = %s",
                (user_id, day_index), fetchone=True
            )

            if result and result[0]:
                ai_schedules_cache[cache_key] = result[0]
                return result[0]
            return None
        except Exception as ex:
            print(f"Ошибка при получении AI-графика: {ex}")
            return None

    # --- Удаление AI-графика из БД ---
    def delete_ai_schedule(day_index: int):
        try:
            cache_key = f"ai_{user_id}_{day_index}"
            ai_schedules_cache.pop(cache_key, None)

            execute_query(
                "DELETE FROM ai_generated_schedules WHERE user_id = %s AND day_of_week = %s",
                (user_id, day_index), commit=True
            )
            return True
        except Exception as ex:
            print(f"Ошибка при удалении AI-графика: {ex}")
            return False

    # --- Сохранение графика в БД ---
    def save_schedule_to_db(day_index: int, tasks_list):
        try:
            execute_query(
                "DELETE FROM schedule_days WHERE user_id = %s AND day_of_week = %s",
                (user_id, day_index), commit=True
            )

            result = execute_query("""
                INSERT INTO schedule_days (user_id, day_of_week) 
                VALUES (%s, %s) RETURNING id_day
            """, (user_id, day_index), fetchone=True)

            if not result:
                return False

            day_id = result[0]

            tasks_to_insert = []
            for task in tasks_list:
                if " - " in task:
                    try:
                        time_part, desc_part = task.split(" - ", 1)
                        if ":" in time_part:
                            h, m = map(int, time_part.split(":"))
                            if 0 <= h <= 23 and 0 <= m <= 59:
                                start_time_obj = datetime.time(hour=h, minute=m)
                                tasks_to_insert.append((day_id, start_time_obj, desc_part.strip()))
                    except:
                        continue

            if tasks_to_insert:
                conn = get_conn()
                if conn:
                    cur = conn.cursor()
                    cur.executemany(
                        "INSERT INTO schedule_tasks (day_id, start_time, description) VALUES (%s, %s, %s)",
                        tasks_to_insert
                    )
                    conn.commit()
                    cur.close()
                    release_conn(conn)

            cache_key = f"current_{user_id}_{day_index}"
            current_schedule_cache[cache_key] = tasks_list

            return True

        except Exception as ex:
            print(f"Ошибка при сохранении графика: {ex}")
            return False

    # --- Показ диалога сравнения ---
    def show_comparison_dialog(day_index: int):
        current_tasks = get_current_schedule_from_db(day_index)
        ai_data = get_ai_schedule(day_index)

        if not ai_data:
            show_message("AI-график не найден", ft.Colors.ORANGE_400)
            return

        day_name = ""
        for wb in week_blocks:
            if wb["day_index"] == day_index:
                day_name = wb["day"]
                break

        ai_tasks = []
        try:
            if isinstance(ai_data, str):
                try:
                    parsed_data = json.loads(ai_data)
                except json.JSONDecodeError:
                    parsed_data = ai_data
            else:
                parsed_data = ai_data

            print(f"Парсинг AI данных для дня {day_index}: {type(parsed_data)}")

            if isinstance(parsed_data, dict):
                if "time_slots" in parsed_data and isinstance(parsed_data["time_slots"], list):
                    print(f"Найдено time_slots: {len(parsed_data['time_slots'])} записей")
                    for item in parsed_data["time_slots"]:
                        if isinstance(item, dict):
                            time_val = item.get('time', '')
                            desc_val = item.get('description', '')

                            if desc_val:
                                if not time_val:
                                    time_val = "00:00"
                                ai_tasks.append(f"{time_val} - {desc_val}")

                elif "tasks" in parsed_data and isinstance(parsed_data["tasks"], list):
                    for item in parsed_data["tasks"]:
                        if isinstance(item, dict):
                            time_val = item.get('time', '') or item.get('start_time', '')
                            desc_val = item.get('description', '') or item.get('desc', '') or item.get('task', '')

                            if desc_val:
                                if not time_val:
                                    time_val = "00:00"
                                ai_tasks.append(f"{time_val} - {desc_val}")

                if "note" in parsed_data:
                    print(f"Note: {parsed_data['note']}")

            elif isinstance(parsed_data, list):
                print(f"Парсинг как списка: {len(parsed_data)} элементов")
                for item in parsed_data:
                    if isinstance(item, dict):
                        time_val = item.get('time', '') or item.get('start_time', '')
                        desc_val = item.get('description', '') or item.get('desc', '') or item.get('task', '')

                        if desc_val:
                            if not time_val:
                                time_val = "00:00"
                            ai_tasks.append(f"{time_val} - {desc_val}")

            print(f"Получено AI задач: {len(ai_tasks)}")

        except Exception as ex:
            print(f"Ошибка при парсинге AI-данных: {ex}")
            import traceback
            traceback.print_exc()
            ai_tasks = ["Ошибка при чтении AI-графика"]

        print(f"Current tasks: {current_tasks}")
        print(f"AI tasks: {ai_tasks}")

        ai_additional_info = []
        if not ai_tasks and isinstance(parsed_data, dict):
            if "note" in parsed_data:
                ai_additional_info.append(f"Примечание: {parsed_data['note']}")
            if "focus_areas" in parsed_data:
                ai_additional_info.append(f"Фокус: {', '.join(parsed_data['focus_areas'])}")
            if "productivity_score" in parsed_data:
                ai_additional_info.append(f"Продуктивность: {parsed_data['productivity_score']}/10")

        def apply_ai_schedule(e):
            if save_schedule_to_db(day_index, ai_tasks):
                delete_ai_schedule(day_index)

                for wb in week_blocks:
                    if wb["day_index"] == day_index:
                        wb["tasks"].controls.clear()

                        if ai_tasks and "Ошибка" not in ai_tasks[0]:
                            for task_str in ai_tasks:
                                if " - " in task_str:
                                    time_part, desc_part = task_str.split(" - ", 1)
                                    wb["tasks"].controls.append(
                                        create_task_row(time_part.strip(), desc_part.strip())
                                    )

                        if not wb["tasks"].controls:
                            wb["tasks"].controls.append(create_task_row())

                        wb["tasks"].update()
                        break

                update_compare_buttons()
                show_message(f"AI-график сохранен", ft.Colors.GREEN_400)
            else:
                show_message("Ошибка при сохранении", ft.Colors.RED_400)

            page.close(dlg)

        def save_current_schedule(e):
            if delete_ai_schedule(day_index):
                update_compare_buttons()
                show_message(f"Ваш график сохранен", ft.Colors.BLUE_400)
            else:
                show_message("Ошибка при удалении", ft.Colors.RED_400)

            page.close(dlg)

        ai_content_controls = []
        if ai_tasks:
            for task in ai_tasks:
                ai_content_controls.append(ft.Text(f"• {task}", size=14))
        elif ai_additional_info:
            for info in ai_additional_info:
                ai_content_controls.append(ft.Text(f"• {info}", size=12, italic=True))
            ai_content_controls.append(ft.Text("(Нет конкретных временных слотов)", size=12, italic=True))
        else:
            ai_content_controls.append(ft.Text("Нет предложений", italic=True))

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Сравнение: {day_name}", size=20),
            content=ft.Column([
                ft.Text("Ваш график:", size=16, color=ft.Colors.BLUE_700),
                ft.Container(
                    content=ft.Column(
                        controls=[ft.Text(f"• {task}", size=14) for task in current_tasks] or
                                 [ft.Text("Нет задач", italic=True)],
                        spacing=5,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                    padding=10,
                    border=ft.border.all(1, ft.Colors.BLUE_400),
                    border_radius=10,
                    height=150,
                    width=400,
                ),
                ft.Divider(),
                ft.Text("AI-график:", size=16, color=ft.Colors.GREEN_700),
                ft.Container(
                    content=ft.Column(
                        controls=ai_content_controls,
                        spacing=5,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                    padding=10,
                    border=ft.border.all(1, ft.Colors.GREEN_400),
                    border_radius=10,
                    height=150,
                    width=400,
                ),
            ], height=350, width=450, scroll=ft.ScrollMode.AUTO),
            actions=[
                ft.ElevatedButton(
                    "💾 Оставить свой",
                    on_click=save_current_schedule,
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.BLUE_600,
                        color=ft.Colors.WHITE
                    )
                ),
                ft.ElevatedButton(
                    "🤖 Применить AI",
                    on_click=apply_ai_schedule,
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.GREEN_600,
                        color=ft.Colors.WHITE
                    )
                )
            ],
            actions_alignment=ft.MainAxisAlignment.CENTER
        )

        page.open(dlg)

    # --- Функция сравнения ---
    def compare_day_schedule(day_index: int, e=None):
        show_comparison_dialog(day_index)

    # --- Обновление кнопок сравнения ---
    def update_compare_buttons():
        try:
            result = execute_query(
                "SELECT day_of_week FROM ai_generated_schedules WHERE user_id = %s",
                (user_id,), fetchall=True
            )

            ai_days = set(row[0] for row in result) if result else set()

            for wb in week_blocks:
                has_ai = wb["day_index"] in ai_days
                wb["compare_button"].visible = has_ai

                if has_ai:
                    wb["day_title"].value = f"{wb['day']} 🔄"
                    wb["day_title"].color = ft.Colors.BLUE_700
                else:
                    wb["day_title"].value = wb['day']
                    wb["day_title"].color = ft.Colors.BLACK

                wb["compare_button"].update()
                wb["day_title"].update()

        except Exception as ex:
            print(f"Ошибка при обновлении кнопок: {ex}")

    # --- Создание дневного блока ---
    def create_day_block(day_name: str, day_index: int):
        tasks_column = ft.Column(controls=[create_task_row()], spacing=8)

        day_title = ft.Text(day_name, size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.BLACK)

        compare_button = ft.IconButton(
            icon=ft.Icons.COMPARE_ARROWS,
            icon_color=ft.Colors.BLUE_600,
            tooltip="Сравнить с AI",
            visible=False,
            on_click=lambda e, idx=day_index: compare_day_schedule(idx)
        )

        def add_task(e):
            tasks_column.controls.append(create_task_row())
            tasks_column.update()

        block_content = ft.Column(
            controls=[
                ft.Row([day_title, ft.Container(expand=True), compare_button]),
                ft.Divider(color=ft.Colors.GREEN_300, height=2),
                ft.Row([
                    ft.Container(ft.Text("Время", size=12, color=ft.Colors.BLACK), width=140),
                    ft.Text("Описание", size=12, color=ft.Colors.BLACK)
                ], spacing=10),
                ft.Divider(color=ft.Colors.GREEN_200, height=1),
                tasks_column,
                ft.ElevatedButton(
                    "Добавить задачу",
                    icon=ft.Icons.ADD,
                    on_click=add_task,
                    width=200,
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.GREEN_500,
                        color=ft.Colors.WHITE,
                        padding=10
                    )
                )
            ],
            spacing=10,
        )

        container = ft.Container(
            content=block_content,
            padding=15,
            width=380,
            height=420,
            border_radius=12,
            bgcolor=ft.Colors.WHITE,
            border=ft.border.all(1, ft.Colors.GREEN_300),
            shadow=ft.BoxShadow(
                spread_radius=1,
                blur_radius=10,
                color=ft.Colors.BLACK12,
            )
        )

        week_blocks.append({
            "day": day_name,
            "day_index": day_index,
            "tasks": tasks_column,
            "content": block_content,
            "container": container,
            "has_tasks": False,
            "day_title": day_title,
            "compare_button": compare_button
        })

        return container

    # Создаем недельный layout с днями по 2 в строке
    week_layout_rows = []
    for i in range(0, len(days), 2):
        row_days = []
        for j in range(2):
            if i + j < len(days):
                day_index = i + j + 1
                day_name = days[i + j]
                row_days.append(create_day_block(day_name, day_index))

        week_layout_rows.append(
            ft.Row(
                controls=row_days,
                spacing=20,
                alignment=ft.MainAxisAlignment.CENTER,
            )
        )

    week_layout = ft.Column(controls=week_layout_rows, spacing=20)

    # --- Проверка наличия задач в дне ---
    def check_day_has_tasks(day_index: int) -> bool:
        for wb in week_blocks:
            if wb["day_index"] == day_index:
                for row in wb["tasks"].controls:
                    if get_time_from_row(row) or row.controls[1].value.strip():
                        return True
                return False
        return False

    # --- Обновление dropdown с днями ---
    def update_days_with_tasks_dropdown():
        days_with_tasks = []
        for wb in week_blocks:
            if check_day_has_tasks(wb["day_index"]):
                days_with_tasks.append(wb["day"])

        clear_day_dropdown.options = [ft.dropdown.Option(day) for day in days_with_tasks]

        if days_with_tasks:
            clear_day_dropdown.value = days_with_tasks[0]
            clear_day_dropdown.hint_text = "Выберите день для очистки"
        else:
            clear_day_dropdown.value = None
            clear_day_dropdown.hint_text = "Нет задач"

        clear_day_dropdown.update()

    # --- Очистка выбранного дня ---
    def clear_selected_day(e):
        selected_day = clear_day_dropdown.value
        if not selected_day:
            show_message("Выберите день", ft.Colors.ORANGE_400)
            return

        day_index = days.index(selected_day) + 1

        def confirm_delete(e):
            try:
                execute_query(
                    "DELETE FROM schedule_days WHERE user_id = %s AND day_of_week = %s",
                    (user_id, day_index), commit=True
                )

                cache_key = f"current_{user_id}_{day_index}"
                current_schedule_cache.pop(cache_key, None)

                for wb in week_blocks:
                    if wb["day_index"] == day_index:
                        wb["tasks"].controls.clear()
                        wb["tasks"].controls.append(create_task_row())
                        wb["content"].update()
                        wb["has_tasks"] = False
                        break

                update_days_with_tasks_dropdown()
                update_compare_buttons()

                show_message(f"{selected_day} удален из базы данных", ft.Colors.GREEN_400)
                page.update()

            except Exception as ex:
                show_message(f"Ошибка при удалении: {ex}", ft.Colors.RED_400)

            page.close(dlg)

        def cancel_delete(e):
            page.close(dlg)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Подтверждение удаления", size=20),
            content=ft.Column([
                ft.Text(f"Вы уверены, что хотите удалить день:"),
                ft.Text(f"📅 {selected_day}", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_600),
                ft.Text("Это действие удалит все задачи этого дня из базы данных."),
                ft.Text("Вы можете просто очистить поле, чтобы оставить день пустым.", size=12, italic=True),
            ], spacing=10, width=400),
            actions=[
                ft.TextButton("Отмена", on_click=cancel_delete),
                ft.ElevatedButton(
                    "🗑️ Удалить день",
                    on_click=confirm_delete,
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.RED_600,
                        color=ft.Colors.WHITE
                    )
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.CENTER
        )

        page.open(dlg)

    # --- Сохранение графика ---
    def save_schedule(e):
        try:
            all_tasks = []

            for wb in week_blocks:
                day_index = wb["day_index"]
                tasks_for_day = []

                for row in wb["tasks"].controls:
                    start_time = get_time_from_row(row)
                    description = row.controls[1].value.strip()

                    if start_time and description:
                        try:
                            h, m = map(int, start_time.split(":"))
                            if 0 <= h <= 23 and 0 <= m <= 59:
                                tasks_for_day.append((day_index, start_time, description))
                        except:
                            pass

                if tasks_for_day:
                    all_tasks.extend(tasks_for_day)

            if not all_tasks:
                show_message("Нет задач для сохранения", ft.Colors.ORANGE_400)
                return

            execute_query("DELETE FROM schedule_days WHERE user_id = %s", (user_id,), commit=True)

            days_map = {}
            for day_index, start_time, description in all_tasks:
                if day_index not in days_map:
                    days_map[day_index] = []
                days_map[day_index].append((start_time, description))

            saved_count = 0
            for day_index, tasks in days_map.items():
                result = execute_query("""
                    INSERT INTO schedule_days (user_id, day_of_week) 
                    VALUES (%s, %s) RETURNING id_day
                """, (user_id, day_index), fetchone=True)

                if result:
                    day_id = result[0]
                    for start_time, description in tasks:
                        h, m = map(int, start_time.split(":"))
                        execute_query(
                            "INSERT INTO schedule_tasks (day_id, start_time, description) VALUES (%s, %s, %s)",
                            (day_id, datetime.time(h, m), description), commit=True
                        )
                        saved_count += 1

            current_schedule_cache.clear()

            update_days_with_tasks_dropdown()
            update_compare_buttons()

            show_message(f"Сохранено {saved_count} задач", ft.Colors.GREEN_400)

        except Exception as ex:
            show_message(f"Ошибка при сохранении: {ex}")

    # --- Загрузка графика ---
    def load_schedule():
        try:
            result = execute_query("""
                SELECT sd.day_of_week, st.start_time, st.description 
                FROM schedule_days sd 
                LEFT JOIN schedule_tasks st ON sd.id_day = st.day_id 
                WHERE sd.user_id = %s 
                ORDER BY sd.day_of_week, st.start_time
            """, (user_id,), fetchall=True)

            if not result:
                return

            days_map = {}
            for day_index, start_time, description in result:
                if day_index not in days_map:
                    days_map[day_index] = []
                if start_time and description:
                    days_map[day_index].append((start_time, description))

            for wb in week_blocks:
                day_index = wb["day_index"]
                tasks_column = wb["tasks"]
                tasks_column.controls.clear()

                if day_index in days_map and days_map[day_index]:
                    for start_time, description in days_map[day_index]:
                        if isinstance(start_time, datetime.time):
                            start_time_str = start_time.strftime("%H:%M")
                        else:
                            start_time_str = str(start_time)[:5]
                        tasks_column.controls.append(
                            create_task_row(start_time_str, description)
                        )
                else:
                    tasks_column.controls.append(create_task_row())

            update_days_with_tasks_dropdown()

        except Exception as ex:
            print(f"Ошибка при загрузке: {ex}")

    # --- Элементы управления ---
    clear_day_dropdown = ft.Dropdown(
        width=200,
        text_size=14,
        content_padding=10,
        hint_text="Выберите день",
        options=[],
        border_color=ft.Colors.GREEN_400,
        border_radius=8,
        filled=True,
        fill_color=ft.Colors.WHITE,
    )

    btn_clear_selected = ft.ElevatedButton(
        "🗑️ Очистить день",
        on_click=clear_selected_day,
        width=220,
        style=ft.ButtonStyle(
            bgcolor=ft.Colors.RED_600,
            color=ft.Colors.WHITE,
            padding=10
        ),
    )

    btn_save = ft.ElevatedButton(
        "💾 Сохранить график",
        on_click=save_schedule,
        width=200,
        style=ft.ButtonStyle(
            bgcolor=ft.Colors.GREEN_600,
            color=ft.Colors.WHITE,
            padding=12
        )
    )

    btn_logout = ft.ElevatedButton(
        "Выйти",
        on_click=lambda _: page.go("/login"),
        width=150,
        style=ft.ButtonStyle(
            bgcolor=ft.Colors.BLUE_GREY_600,
            color=ft.Colors.WHITE,
            padding=10
        )
    )

    # --- Основной layout ---
    main_column = ft.Column(
        [
            # Шапка
            ft.Container(
                content=ft.Row([
                    ft.Text("Профиль", size=32, weight=ft.FontWeight.BOLD, color=ft.Colors.BLACK),
                    ft.Container(expand=True),
                    ft.Text("AntiPro", size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_700),
                ]),
                padding=ft.padding.only(top=20, left=30, right=30),
            ),

            ft.Divider(color=ft.Colors.GREEN_300, height=2),

            # Панель управления
            ft.Container(
                content=ft.Column([
                    ft.Row([
                        btn_save,
                        btn_clear_selected,
                        btn_logout,
                    ], spacing=20, alignment=ft.MainAxisAlignment.CENTER),
                    ft.Divider(color=ft.Colors.GREEN_200, height=1),
                    ft.Row([
                        ft.Text("Очистка дня:", size=16, color=ft.Colors.BLACK),
                        clear_day_dropdown,
                    ], spacing=10, alignment=ft.MainAxisAlignment.CENTER),
                ], spacing=15, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=20,
                bgcolor=ft.Colors.WHITE,
                border_radius=12,
                margin=ft.margin.symmetric(horizontal=30, vertical=10),
                border=ft.border.all(1, ft.Colors.GREEN_200),
            ),

            ft.Divider(color=ft.Colors.GREEN_300, height=2),

            # Заголовок недельного графика
            ft.Container(
                content=ft.Text("📅 График недели", size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.BLACK),
                padding=ft.padding.only(top=10, bottom=10),
            ),

            # Недельный график
            ft.Container(
                content=week_layout,
                padding=20,
                margin=ft.margin.symmetric(horizontal=30),
            ),

            # Кнопки навигации
            ft.Container(
                content=ft.Column([
                    ft.ElevatedButton(
                        "📊 Детализация активности",
                        on_click=lambda _: page.go("/detaliz"),
                        width=350,
                        icon=ft.Icons.BAR_CHART,
                        style=ft.ButtonStyle(
                            bgcolor=ft.Colors.BLUE_600,
                            color=ft.Colors.WHITE,
                            padding=12
                        )
                    ),
                    ft.ElevatedButton(
                        "🏠 На главную",
                        on_click=lambda _: page.go("/home"),
                        width=350,
                        style=ft.ButtonStyle(
                            bgcolor=ft.Colors.GREEN_600,
                            color=ft.Colors.WHITE,
                            padding=12
                        )
                    ),
                    ft.Container(height=20),
                ], spacing=15, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=20,
            ),
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=0,
        scroll=ft.ScrollMode.AUTO,
    )

    # Обертка с градиентом
    gradient_container = ft.Container(
        expand=True,
        alignment=ft.alignment.center,
        gradient=ft.LinearGradient(
            begin=ft.alignment.top_center,
            end=ft.alignment.bottom_center,
            colors=GRADIENT_COLORS,
        ),
        content=main_column,
    )

    view = ft.View(route="/schedule", controls=[gradient_container])

    # Загружаем данные после инициализации
    def init_data():
        load_schedule()
        update_compare_buttons()
        page.update()

    threading.Thread(target=init_data, daemon=True).start()

    return view