"""Display formatting helpers for 20x2 LCD/VFD output."""

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


class PD2800I2CDisplayDriver(DisplayDriver):
    """HD44780-compatible PD2800 (20x2) via I2C backpack (PCF8574).

    Uses `RPLCD.i2c.CharLCD` under the hood. Adjust `address` if ваш
    адаптер на 0x3F или другом адресе. Требуется включённый I2C на
    Raspberry Pi.
    """

    def __init__(
        self,
        address: int = 0x27,
        port: int = 1,
        backlight_enabled: bool = True,
    ) -> None:
        try:
            from RPLCD.i2c import CharLCD
        except ModuleNotFoundError as exc:  # pragma: no cover - hardware dep
            raise RuntimeError(
                "RPLCD not installed. Install with `pip install RPLCD` on the Pi."
            ) from exc

        self.lcd = CharLCD(
            i2c_expander="PCF8574",
            address=address,
            port=port,
            cols=DISPLAY_WIDTH,
            rows=DISPLAY_HEIGHT,
            charmap="A00",
            auto_linebreaks=False,
            backlight_enabled=backlight_enabled,
        )
        self.clear()

    def clear(self) -> None:
        self.lcd.clear()

    def write(self, lines: List[str]) -> None:  # pragma: no cover - hardware dep
        first_line = lines[0][:DISPLAY_WIDTH].ljust(DISPLAY_WIDTH)
        second_line = (
            lines[1][:DISPLAY_WIDTH].ljust(DISPLAY_WIDTH)
            if len(lines) > 1
            else " " * DISPLAY_WIDTH
        )
        self.lcd.home()
        self.lcd.write_string(first_line + "\n" + second_line)


class PD2800SerialDisplayDriver(DisplayDriver):
    """PD2800 (20x2) через UART (VFD, ESC-команды, кодировка CP866)."""

    def __init__(
        self,
        port: str = "/dev/serial0",
        baudrate: int = 9600,
        timeout: float = 1.0,
        init_delay: float = 0.2,
    ) -> None:
        try:
            import serial  # type: ignore
        except ModuleNotFoundError as exc:  # pragma: no cover - hardware dep
            raise RuntimeError("pyserial not installed. Install with `pip install pyserial`.") from exc

        self.serial = serial.Serial(port=port, baudrate=baudrate, timeout=timeout)
        sleep(0.05)
        self._init_display(init_delay)

    def _init_display(self, init_delay: float) -> None:
        self.serial.write(b"\x1b@")  # init
        sleep(init_delay)

    def clear(self) -> None:
        self.serial.write(b"\x0c")  # clear
        sleep(0.05)

    def _write_line(self, cmd: bytes, text: str) -> None:
        payload = (" " + text.ljust(DISPLAY_WIDTH - 1)[: DISPLAY_WIDTH - 1]).encode(
            "cp866", errors="replace"
        )
        self.serial.write(cmd)
        self.serial.write(payload)

    def write(self, lines: List[str]) -> None:  # pragma: no cover - hardware dep
        line1 = lines[0] if lines else ""
        line2 = lines[1] if len(lines) > 1 else ""
        self.clear()
        self._write_line(b"\x1bQ", line1)
        self._write_line(b"\x1bR", line2)
        self.serial.flush()


# Backward compatibility alias
PD2800DisplayDriver = PD2800I2CDisplayDriver
