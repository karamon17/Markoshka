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


def _wrap_message_lines(message: str) -> List[str]:
    """Normalize whitespace, honor explicit newlines, wrap without breaking words."""

    lines: List[str] = []
    for segment in message.split("\n"):
        normalized = " ".join(segment.split())
        if not normalized:
            lines.append("")
            continue
        wrapped = wrap(
            normalized,
            DISPLAY_WIDTH,
            break_long_words=False,
            break_on_hyphens=False,
        )
        lines.extend(wrapped)

    return lines or [""]


def vertical_scrolling_frames(message: str) -> Iterable[DisplayFrame]:
    """Yield frames that scroll the message **вверх** построчно.

    Подход использует обе строки дисплея (20x2), прокручивая набор
    строк шириной 20 символов так, чтобы они поднимались вверх.
    """

    lines = _wrap_message_lines(message)

    # Показываем сразу первые две строки, затем сдвигаем окно вверх.
    for idx in range(len(lines) - 1):
        first_line = lines[idx][:DISPLAY_WIDTH].ljust(DISPLAY_WIDTH)
        second_line = lines[idx + 1][:DISPLAY_WIDTH].ljust(DISPLAY_WIDTH)
        yield DisplayFrame([first_line, second_line])


def static_frame(message: str) -> DisplayFrame:
    """Format a short message into two lines without scrolling."""

    lines = _wrap_message_lines(message)
    first_line = lines[0][:DISPLAY_WIDTH].ljust(DISPLAY_WIDTH)
    second_line = (
        lines[1][:DISPLAY_WIDTH].ljust(DISPLAY_WIDTH) if len(lines) > 1 else " " * DISPLAY_WIDTH
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


def show_message(driver: DisplayDriver, message: str, delay: float = 3.0) -> None:
    """Display a message statically if it fits, otherwise scroll it."""

    lines = _wrap_message_lines(message)
    if len(lines) <= DISPLAY_HEIGHT:
        show_static_message(driver, message)
    else:
        show_scrolling_message(driver, message, delay=delay)
