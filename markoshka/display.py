"""Display formatting helpers for 20x2 LCD output."""

from __future__ import annotations

from dataclasses import dataclass
from textwrap import wrap
from time import sleep
from typing import Iterable, List


DISPLAY_WIDTH = 20
DISPLAY_HEIGHT = 2


@dataclass
class DisplayFrame:
    """Represents two lines of text ready for the LCD."""

    lines: List[str]


class DisplayDriver:
    """Basic interface for the LCD driver.

    Replace ``ConsoleDisplayDriver`` with a hardware-specific
    implementation (e.g. hd44780) on the Raspberry Pi. The driver only
    needs to expose a :py:meth:`write` method that receives two formatted
    strings.
    """

    def write(self, lines: List[str]) -> None:
        raise NotImplementedError


class ConsoleDisplayDriver(DisplayDriver):
    """Fallback driver that prints frames to the console."""

    def write(self, lines: List[str]) -> None:  # pragma: no cover - console output
        divider = "-" * (DISPLAY_WIDTH + 2)
        formatted_lines = [line.ljust(DISPLAY_WIDTH)[:DISPLAY_WIDTH] for line in lines]
        print(divider)
        for line in formatted_lines:
            print(f"|{line}|")
        print(divider)


def _flatten_message(message: str) -> str:
    # Collapse whitespace for scrolling readability.
    return " ".join(message.split())


def vertical_scrolling_frames(message: str) -> Iterable[DisplayFrame]:
    """Yield frames that scroll the message **вверх** построчно.

    Подход использует обе строки дисплея (20x2), прокручивая набор
    строк шириной 20 символов так, чтобы они поднимались вверх.
    """

    flat = _flatten_message(message)
    lines = wrap(flat, DISPLAY_WIDTH)

    # Пустая строка в начале и конце даёт «заезд» и «выезд» текста.
    padded_lines = [""] + lines + [""]
    for idx in range(len(padded_lines) - 1):
        first_line = padded_lines[idx].ljust(DISPLAY_WIDTH)
        second_line = padded_lines[idx + 1].ljust(DISPLAY_WIDTH)
        yield DisplayFrame([first_line, second_line])


def static_frame(message: str) -> DisplayFrame:
    """Format a short message into two lines without scrolling."""

    text = _flatten_message(message)
    first_line = text[:DISPLAY_WIDTH].ljust(DISPLAY_WIDTH)
    second_line = text[DISPLAY_WIDTH : DISPLAY_WIDTH * DISPLAY_HEIGHT].ljust(
        DISPLAY_WIDTH
    )
    return DisplayFrame([first_line, second_line])


def show_scrolling_message(
    driver: DisplayDriver, message: str, delay: float = 0.8
) -> None:
    """Animate a **vertical** scrolling message using the given driver."""

    for frame in vertical_scrolling_frames(message):
        driver.write(frame.lines)
        sleep(delay)


def show_static_message(driver: DisplayDriver, message: str) -> None:
    frame = static_frame(message)
    driver.write(frame.lines)
