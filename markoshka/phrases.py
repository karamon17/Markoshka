"""Sample phrase catalogue for Markoshka display program."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class Category:
    """Represents a category of phrases."""

    name: str
    phrases: List[str]


PHRASE_CATALOGUE: Dict[str, Category] = {
    "Поддержка": Category(
        name="Поддержка",
        phrases=[
            "Ты справишься!",
            "Дыши глубже, все ок",
        ],
    ),
    "Вдохновение": Category(
        name="Вдохновение",
        phrases=[
            "Ты как лучик света",
            "Сегодня твой день",
        ],
    ),
    "Юмор": Category(
        name="Юмор",
        phrases=[
            "Кофе уже в пути",
        ],
    ),
    "Напоминания": Category(
        name="Напоминания",
        phrases=[
            "Вода? Пора глоток",
            "Спинка прямая",
        ],
    ),
    "Отдых": Category(
        name="Отдых",
        phrases=[
            "Микро-перерыв?",
        ],
    ),
    "Цели": Category(
        name="Цели",
        phrases=[
            "Шаг за шагом",
        ],
    ),
    "Похвала": Category(
        name="Похвала",
        phrases=[
            "Я горжусь тобой",
        ],
    ),
    "Дружба": Category(
        name="Дружба",
        phrases=[
            "Я рядом, Марго",
        ],
    ),
    "Энергия": Category(
        name="Энергия",
        phrases=[
            "Зажигаем день!",
        ],
    ),
}
"""
There are only ten phrases here for testing. Replace phrases in
``PHRASE_CATALOGUE`` with the full list when it is available.
"""
