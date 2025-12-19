import flet as ft
import psycopg2
from flet_route import Params, Basket
import datetime

# --- Настройки подключения ---
DB_CONFIG = {
    "host": "localhost",
    "dbname": "Your_db_name",
    "user": "postgres",
    "password": "Your_password",
    "port": 5432
}


def Detalization_page(page: ft.Page, basket: Basket, params: Params):
    page.title = "Детализация"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.window_full_screen = True
    page.bgcolor = "#8EE1AF"
    page.padding = 0
    page.spacing = 0

    # Получаем user_id из basket
    user_id = basket.user_id

    if not user_id:
        return ft.View(
            route="/detaliz",
            controls=[
                ft.Container(
                    content=ft.Column([
                        ft.Text("Требуется авторизация", size=24, color="#000000"),
                        ft.ElevatedButton("Войти", on_click=lambda e: page.go("/login"))
                    ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    expand=True,
                    alignment=ft.alignment.center
                )
            ]
        )

    # Функция для удаления старых записей (старше 31 дня)
    def cleanup_old_records():
        """Удаляет записи старше 31 дня для текущего пользователя"""
        try:
            connection = psycopg2.connect(**DB_CONFIG)
            cursor = connection.cursor()

            # Вычисляем дату 31 день назад
            cutoff_date = datetime.date.today() - datetime.timedelta(days=31)

            # Удаляем записи старше cutoff_date
            cursor.execute("""
                DELETE FROM activity_monitoring 
                WHERE user_id = %s AND activity_date < %s
            """, (user_id, cutoff_date))

            deleted_count = cursor.rowcount

            connection.commit()
            cursor.close()
            connection.close()

            print(f"Автоматически удалено {deleted_count} записей старше {cutoff_date}")
            return deleted_count

        except Exception as e:
            print(f"Ошибка при удалении старых записей: {e}")
            return 0

    # Функция для форматирования времени
    def format_time(seconds):
        """Преобразует секунды в часы и минуты"""
        hours = seconds / 3600
        return f"{hours:.2f} ч"

    def format_time_minutes(seconds):
        """Преобразует секунды в минуты"""
        minutes = seconds / 60
        return f"{minutes:.0f} мин"

    def format_time_detailed(seconds):
        """Преобразует секунды в часы:минуты"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours:02d}ч {minutes:02d}м"

    # Элементы интерфейса
    period_dropdown = ft.Dropdown(
        label="Выберите период",
        width=220,
        options=[
            ft.dropdown.Option("today", "Сегодня"),
            ft.dropdown.Option("week", "Последние 7 дней"),
            ft.dropdown.Option("month", "Последние 30 дней"),
        ],
        value="today",
        color="#000000",
        label_style=ft.TextStyle(color="#000000"),
        bgcolor="#FFFFFF",
    )

    data_container = ft.Container()
    chart_container = ft.Container()
    summary_text = ft.Text("", size=16, color="#000000")
    debug_text = ft.Text("", size=12, color="#333333")
    date_info_text = ft.Text("", size=12, color="#333333")

    # --- Функция для получения данных из БД ---
    def fetch_data(period):
        try:
            connection = psycopg2.connect(**DB_CONFIG)
            cursor = connection.cursor()

            today = datetime.date.today()

            if period == "today":
                start_date = today
                end_date = today
                cursor.execute("""
                    SELECT 
                        app_name, 
                        SUM(total_seconds) as total_seconds,
                        ROUND(SUM(total_seconds) / 3600.0, 2) as total_hours
                    FROM activity_monitoring 
                    WHERE user_id = %s AND activity_date = %s
                    GROUP BY app_name
                    ORDER BY total_seconds DESC
                """, (user_id, today))
                period_text = "сегодня"

            elif period == "week":
                start_date = today - datetime.timedelta(days=6)
                end_date = today
                cursor.execute("""
                    SELECT 
                        app_name, 
                        SUM(total_seconds) as total_seconds,
                        ROUND(SUM(total_seconds) / 3600.0, 2) as total_hours
                    FROM activity_monitoring 
                    WHERE user_id = %s AND activity_date BETWEEN %s AND %s
                    GROUP BY app_name
                    ORDER BY total_seconds DESC
                """, (user_id, start_date, end_date))
                period_text = "за последние 7 дней"

            else:
                start_date = today - datetime.timedelta(days=29)
                end_date = today
                cursor.execute("""
                    SELECT 
                        app_name, 
                        SUM(total_seconds) as total_seconds,
                        ROUND(SUM(total_seconds) / 3600.0, 2) as total_hours
                    FROM activity_monitoring 
                    WHERE user_id = %s AND activity_date BETWEEN %s AND %s
                    GROUP BY app_name
                    ORDER BY total_seconds DESC
                """, (user_id, start_date, end_date))
                period_text = "за последние 30 дней"

            data = cursor.fetchall()

            cursor.execute("""
                SELECT MIN(activity_date), MAX(activity_date) 
                FROM activity_monitoring 
                WHERE user_id = %s
            """, (user_id,))

            date_range = cursor.fetchone()
            min_date, max_date = date_range if date_range else (None, None)

            if min_date and max_date:
                date_info = f"Данные с {min_date.strftime('%d.%m.%Y')} по {max_date.strftime('%d.%m.%Y')}"
            else:
                date_info = "Нет данных"

            date_info_text.value = f"{date_info} | Запрашиваемый период: {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}"

            debug_text.value = f"Период: {period_text}"

            total_seconds = 0
            app_data = []
            for app_name, total_seconds_db, total_hours_db in data:
                total_seconds += total_seconds_db
                app_data.append({
                    'app_name': app_name,
                    'seconds': total_seconds_db,
                    'hours': total_hours_db
                })

            cursor.close()
            connection.close()

            total_hours = round(total_seconds / 3600, 2) if total_seconds > 0 else 0

            return app_data, total_hours, total_seconds, period_text

        except Exception as e:
            print(f"Ошибка при получении данных: {e}")
            debug_text.value = f"Ошибка: {str(e)}"
            date_info_text.value = f"Ошибка подключения"
            return [], 0, 0, "ошибка"

    # --- Функция для создания диаграммы ---
    def create_chart(app_data, total_seconds, period_text):
        if not app_data or total_seconds == 0:
            return ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.PIE_CHART, size=48, color="#333333"),
                    ft.Text("Нет данных для диаграммы", size=16, color="#000000"),
                    ft.Text(f"Период: {period_text}", size=14, color="#333333"),
                ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                height=300,
                alignment=ft.alignment.center
            )

        colors = [
            "#4A90E2",
            "#50C878",
            "#FF6B6B",
            "#9B59B6",
            "#FFD166",
            "#1ABC9C",
            "#FF9F1C",
            "#FF69B4",
        ]

        top_apps = app_data[:7]
        other_seconds = sum(app['seconds'] for app in app_data[7:]) if len(app_data) > 7 else 0

        chart_sections = []
        legend_items = []

        for i, app in enumerate(top_apps):
            percentage = (app['seconds'] / total_seconds) * 100

            category = "Приложение"
            app_lower = app['app_name'].lower()
            if any(browser in app_lower for browser in
                   ['chrome', 'firefox', 'safari', 'edge', 'opera', 'brave', 'yandex']):
                category = "Браузер"
            elif any(social in app_lower for social in
                     ['telegram', 'whatsapp', 'vk', 'discord', 'instagram', 'facebook', 'twitter']):
                category = "Соцсети"
            elif any(work in app_lower for work in ['vscode', 'pycharm', 'word', 'excel', 'powerpoint', 'notion']):
                category = "Работа"
            elif any(media in app_lower for media in ['spotify', 'youtube', 'netflix', 'twitch', 'tiktok']):
                category = "Медиа"

            chart_sections.append(
                ft.PieChartSection(
                    value=percentage,
                    color=colors[i % len(colors)],
                    radius=80,
                    title=f"{percentage:.1f}%",
                    title_style=ft.TextStyle(
                        size=12,
                        color="#FFFFFF",
                        weight=ft.FontWeight.BOLD
                    ),
                )
            )

            icon = ft.Icons.WEB
            if category == "Браузер":
                icon = ft.Icons.WEB
            elif category == "Соцсети":
                icon = ft.Icons.PEOPLE
            elif category == "Работа":
                icon = ft.Icons.WORK
            elif category == "Медиа":
                icon = ft.Icons.PLAY_CIRCLE

            legend_items.append(
                ft.Container(
                    content=ft.Row([
                        ft.Container(
                            width=12,
                            height=12,
                            bgcolor=colors[i % len(colors)],
                            border_radius=6,
                        ),
                        ft.Icon(icon, size=16, color="#333333"),
                        ft.Text(
                            f"{app['app_name'][:15]}{'...' if len(app['app_name']) > 15 else ''}",
                            size=12,
                            color="#000000",
                            expand=True,
                            tooltip=f"{app['app_name']}\n{category}: {format_time_detailed(app['seconds'])}"
                        ),
                        ft.Text(f"{percentage:.1f}%", size=12, color="#333333", width=40),
                    ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.padding.symmetric(vertical=4, horizontal=8),
                    bgcolor="#FFFFFF",
                    border=ft.border.all(1, "#E0E0E0"),
                    border_radius=6,
                    margin=ft.margin.only(bottom=2),
                )
            )

        if other_seconds > 0:
            other_percentage = (other_seconds / total_seconds) * 100
            chart_sections.append(
                ft.PieChartSection(
                    value=other_percentage,
                    color="#95A5A6",
                    radius=80,
                    title=f"{other_percentage:.1f}%",
                    title_style=ft.TextStyle(
                        size=12,
                        color="#FFFFFF",
                        weight=ft.FontWeight.BOLD
                    ),
                )
            )

            legend_items.append(
                ft.Container(
                    content=ft.Row([
                        ft.Container(
                            width=12,
                            height=12,
                            bgcolor="#95A5A6",
                            border_radius=6,
                        ),
                        ft.Icon(ft.Icons.APPS, size=16, color="#333333"),
                        ft.Text(f"Другие ({len(app_data) - 7} прил.)", size=12, color="#000000", expand=True),
                        ft.Text(f"{other_percentage:.1f}%", size=12, color="#333333", width=40),
                    ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.padding.symmetric(vertical=4, horizontal=8),
                    bgcolor="#FFFFFF",
                    border=ft.border.all(1, "#E0E0E0"),
                    border_radius=6,
                    margin=ft.margin.only(bottom=2),
                )
            )

        chart = ft.PieChart(
            sections=chart_sections,
            sections_space=1,
            center_space_radius=40,
            expand=True,
        )

        categories_stats = {
            "Браузер": {"seconds": 0, "apps": []},
            "Соцсети": {"seconds": 0, "apps": []},
            "Работа": {"seconds": 0, "apps": []},
            "Медиа": {"seconds": 0, "apps": []},
            "Другие": {"seconds": 0, "apps": []},
        }

        for app in app_data:
            app_lower = app['app_name'].lower()
            category = "Другие"
            if any(browser in app_lower for browser in
                   ['chrome', 'firefox', 'safari', 'edge', 'opera', 'brave', 'yandex']):
                category = "Браузер"
            elif any(social in app_lower for social in
                     ['telegram', 'whatsapp', 'vk', 'discord', 'instagram', 'facebook', 'twitter']):
                category = "Соцсети"
            elif any(work in app_lower for work in ['vscode', 'pycharm', 'word', 'excel', 'powerpoint', 'notion']):
                category = "Работа"
            elif any(media in app_lower for media in ['spotify', 'youtube', 'netflix', 'twitch', 'tiktok']):
                category = "Медиа"

            categories_stats[category]["seconds"] += app['seconds']
            categories_stats[category]["apps"].append(app['app_name'])

        categories_display = []
        for category, stats in categories_stats.items():
            if stats["seconds"] > 0:
                percentage = (stats["seconds"] / total_seconds) * 100
                categories_display.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Text(category, size=12, color="#000000", width=80),
                            ft.ProgressBar(
                                value=percentage / 100,
                                color=colors[0],
                                bgcolor="#E0E0E0",
                                height=8,
                                width=150,
                            ),
                            ft.Text(f"{percentage:.1f}%", size=12, color="#333333", width=50),
                            ft.Text(format_time_minutes(stats["seconds"]), size=12, color="#333333"),
                        ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        padding=ft.padding.symmetric(vertical=6, horizontal=10),
                        bgcolor="#FFFFFF",
                        border=ft.border.all(1, "#E0E0E0"),
                        border_radius=6,
                        margin=ft.margin.only(bottom=4),
                    )
                )

        return ft.Container(
            content=ft.Column([
                ft.Text(f"📊 Распределение времени {period_text}", size=16, color="#000000"),
                ft.Divider(height=10, color="#E0E0E0"),
                # Диаграмма посередине
                ft.Container(
                    content=chart,
                    width=300,
                    height=300,
                    alignment=ft.alignment.center,
                    padding=20,
                ),
                ft.Divider(height=10, color="#E0E0E0"),
                # Легенда под диаграммой (ИСПРАВЛЕНО: убрали max_height)
                ft.Container(
                    content=ft.Column(
                        controls=legend_items,
                        spacing=2,
                        scroll=ft.ScrollMode.AUTO,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    width=500,
                    height=200,  # Исправлено: вместо max_height используем height
                    padding=10,
                    bgcolor="#FFFFFF",
                    border_radius=10,
                    border=ft.border.all(1, "#E0E0E0"),
                    alignment=ft.alignment.center,
                ),
                ft.Divider(height=10, color="#E0E0E0"),
                ft.Text("📈 Статистика по типам приложений", size=14, color="#000000"),
                ft.Column(categories_display, spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=20,
            bgcolor="#FFFFFF",
            border_radius=15,
            border=ft.border.all(1, "#E0E0E0"),
        )

    # --- Функция для обновления отображения ---
    def update_display(e=None):
        deleted_count = cleanup_old_records()

        if deleted_count > 0:
            page.snack_bar = ft.SnackBar(
                ft.Text(f"Автоматически удалено {deleted_count} записей старше 31 дня",
                        color="#FFFFFF"),
                bgcolor="#4A90E2",
                duration=3000
            )
            page.snack_bar.open = True

        period = period_dropdown.value
        app_data, total_hours, total_seconds, period_text = fetch_data(period)

        if total_hours > 0:
            summary_text.value = f"📊 Общая активность: {total_hours} часов ({format_time_detailed(total_seconds)}) {period_text}"
        else:
            summary_text.value = f"ℹ️ Нет данных {period_text}"

        if not app_data:
            data_container.content = ft.Column([
                ft.Icon(ft.Icons.BAR_CHART, size=64, color="#95A5A6"),
                ft.Text(f"Нет данных {period_text}", size=20, color="#000000"),
                ft.Text("Начните использовать приложения для сбора статистики",
                        size=14, color="#333333"),
                ft.Container(height=20),
                ft.Text("Пример того, что вы увидите:", size=16, color="#000000"),
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Text("🌐 Браузеры", size=14, color="#000000", expand=True),
                            ft.Text("30 мин", size=14, color="#000000"),
                        ]),
                        ft.Row([
                            ft.Text("📱 TikTok/Instagram", size=14, color="#000000", expand=True),
                            ft.Text("20 мин", size=14, color="#000000"),
                        ]),
                        ft.Row([
                            ft.Text("💼 Рабочие приложения", size=14, color="#000000", expand=True),
                            ft.Text("15 мин", size=14, color="#000000"),
                        ]),
                        ft.Row([
                            ft.Text("🎵 Медиа", size=14, color="#000000", expand=True),
                            ft.Text("10 мин", size=14, color="#000000"),
                        ]),
                        ft.Row([
                            ft.Text("📞 Другие приложения", size=14, color="#333333", expand=True),
                            ft.Text("5 мин", size=14, color="#333333"),
                        ]),
                    ], spacing=8),
                    padding=20,
                    bgcolor="#FFFFFF",
                    border_radius=10,
                    border=ft.border.all(1, "#E0E0E0"),
                    width=400,
                ),
            ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=15)

            chart_container.content = create_chart([], 0, period_text)
        else:
            app_items = []

            for i, app in enumerate(app_data[:10]):
                percentage = (app['seconds'] / total_seconds) * 100 if total_seconds > 0 else 0

                icon = ft.Icons.APPS
                app_lower = app['app_name'].lower()
                if any(browser in app_lower for browser in ['chrome', 'firefox', 'safari', 'edge', 'opera']):
                    icon = ft.Icons.WEB
                elif any(social in app_lower for social in ['telegram', 'whatsapp', 'vk', 'discord']):
                    icon = ft.Icons.CHAT_BUBBLE
                elif 'tiktok' in app_lower or 'instagram' in app_lower:
                    icon = ft.Icons.VIDEO_LIBRARY
                elif 'spotify' in app_lower or 'youtube' in app_lower:
                    icon = ft.Icons.MUSIC_NOTE
                elif any(work in app_lower for work in ['vscode', 'pycharm', 'word', 'excel']):
                    icon = ft.Icons.WORK

                app_items.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(icon, size=20, color="#4A90E2"),
                            ft.Text(f"{i + 1}.", size=16, color="#333333", width=30),
                            ft.Text(
                                app['app_name'][:25] + "..." if len(app['app_name']) > 25 else app['app_name'],
                                size=16,
                                color="#000000",
                                expand=True,
                                tooltip=app['app_name']
                            ),
                            ft.Text(
                                format_time(app['seconds']),
                                size=16,
                                color="#4A90E2",
                                tooltip=format_time_detailed(app['seconds'])
                            ),
                            ft.Container(
                                content=ft.Text(f"{percentage:.1f}%", size=14, color="#333333"),
                                width=60,
                                alignment=ft.alignment.center_right,
                            ),
                        ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        padding=ft.padding.symmetric(vertical=12, horizontal=15),
                        bgcolor="#FFFFFF" if i % 2 == 0 else "#F7F7F7",
                        border=ft.border.all(1, "#E0E0E0"),
                        border_radius=10,
                        margin=ft.margin.only(bottom=5),
                    )
                )

            data_container.content = ft.Container(
                content=ft.Column([
                    ft.Text(f"📱 Топ приложений по времени {period_text}", size=18, color="#000000"),
                    ft.Divider(height=10, color="#E0E0E0"),
                    ft.Column(
                        controls=app_items,
                        spacing=2,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=20,
                bgcolor="#FFFFFF",
                border_radius=15,
                border=ft.border.all(1, "#E0E0E0"),
            )

            chart_container.content = create_chart(app_data, total_seconds, period_text)

        page.update()

    period_dropdown.on_change = update_display

    # --- Создание интерфейса ---
    # Контейнер с белым фоном для контента
    content_container = ft.Container(
        content=ft.Column([
            # Заголовок
            ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.IconButton(
                            icon=ft.Icons.ARROW_BACK,
                            icon_color="#000000",
                            on_click=lambda e: page.go("/schedule"),
                            tooltip="Назад к расписанию"
                        ),
                        ft.Container(expand=True),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Container(
                        content=ft.Column([
                            ft.Text("📊 Детализация активности",
                                    size=28, weight=ft.FontWeight.BOLD, color="#000000"),
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=5),
                        alignment=ft.alignment.center,
                    ),
                ]),
                padding=15,
                bgcolor="#FFFFFF",
                border=ft.border.only(bottom=ft.border.BorderSide(1, "#E0E0E0")),
            ),

            # Период выбора
            ft.Container(
                content=ft.Column([
                    ft.Text("📅 Выберите период для анализа:",
                            size=16, color="#000000"),
                    ft.Row([
                        period_dropdown,
                        ft.IconButton(
                            icon=ft.Icons.REFRESH,
                            icon_color="#4A90E2",
                            on_click=update_display,
                            tooltip="Обновить данные"
                        ),
                    ], alignment=ft.MainAxisAlignment.CENTER, spacing=10)
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                padding=10,
                bgcolor="#FFFFFF",
            ),

            # Сводка и информация
            ft.Container(
                content=ft.Column([
                    ft.Container(
                        content=summary_text,
                        alignment=ft.alignment.center,
                    ),
                    ft.Container(
                        content=debug_text,
                        alignment=ft.alignment.center,
                    ),
                    ft.Container(
                        content=date_info_text,
                        alignment=ft.alignment.center,
                    ),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=10,
                bgcolor="#FFFFFF",
            ),

            # Диаграмма
            ft.Container(
                content=chart_container,
                padding=10,
                alignment=ft.alignment.center,
                bgcolor="#FFFFFF",
            ),

            # Данные
            ft.Container(
                content=data_container,
                padding=10,
                expand=True,
                alignment=ft.alignment.center,
                bgcolor="#FFFFFF",
            ),
        ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        expand=True,
        bgcolor="#FFFFFF",
        margin=20,
        border_radius=15,
    )

    # Собираем все вместе
    main_content = ft.Container(
        content=content_container,
        expand=True,
        gradient=ft.LinearGradient(
            begin=ft.alignment.top_center,
            end=ft.alignment.bottom_center,
            colors=["#E7FFF0", "#8EE1AF"],
        ),
        padding=0,
        margin=0,
    )

    def on_load(e):
        update_display()

    page.on_load = on_load

    view = ft.View(
        controls=[main_content],
        scroll=ft.ScrollMode.AUTO,
        padding=0,
        spacing=0,
        bgcolor="#8EE1AF",
    )

    return view