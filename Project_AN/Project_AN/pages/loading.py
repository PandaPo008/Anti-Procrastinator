import flet as ft
from flet_route import Params, Basket


def Loading_page(page: ft.Page, params: Params, basket: Basket):
    page.title = "Тест Стартового Экрана"
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.window.full_screen = True
    page.theme_mode = ft.ThemeMode.LIGHT

    return ft.View(
        route="/loading",
        controls=[
            ft.Container(
                expand=True,
                on_click=lambda _: page.go("/home"),
                content=ft.Column(
                    [
                        ft.Text(
                            "АНТИ-ПРОКРАСТИНАТОР",
                            size=30,
                            weight=ft.FontWeight.BOLD,
                            color=ft.Colors.PURPLE_700,
                        ),
                        ft.Container(height=20),
                        ft.Text("🏃...", size=40),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )
        ]
    )
