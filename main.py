from __future__ import annotations

import importlib.util
import os
import random
import signal
import time
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

from markoshka.display import (
    ConsoleDisplayDriver,
    DisplayDriver,
    PD2800DisplayDriver,
    show_message,
    show_static_message,
)
from markoshka.phrases import Category, PHRASE_CATALOGUE

MODE_DISPLAY_NAMES = {
    "sequential": "Режим: подряд",
    "random": "Режим: рандом",
    "category": "Режим: по разделу",
}


class Mode(str, Enum):
    SEQUENTIAL = "sequential"
    RANDOM = "random"
    CATEGORY_SEQUENCE = "category"


class PhraseSequencer:
    """Keeps track of phrase order across different modes."""

    def __init__(self, categories: Dict[str, Category]):
        self.categories: List[Category] = list(categories.values())
        self.category_index: int = 0
        self.phrase_index: int = 0

        # Manual category selection for CATEGORY_SEQUENCE.
    def _advance_indices(self) -> Tuple[Category, str]:
        category = self.categories[self.category_index]
        phrase = category.phrases[self.phrase_index]

        self.phrase_index = (self.phrase_index + 1) % len(category.phrases)
        if self.phrase_index == 0:
            self.category_index = (self.category_index + 1) % len(self.categories)

        return category, phrase

    def next_phrase(self, mode: Mode) -> Tuple[Category, str]:
        if mode == Mode.SEQUENTIAL:
            return self._advance_indices()

        if mode == Mode.RANDOM:
            category = random.choice(self.categories)
            phrase = random.choice(category.phrases)
            return category, phrase

        # CATEGORY_SEQUENCE: run phrases in the selected category, then
        # continue to the next categories sequentially.
        category = self.categories[self.category_index]
        phrase = category.phrases[self.phrase_index]
        self.phrase_index += 1
        if self.phrase_index >= len(category.phrases):
            self.phrase_index = 0
            self.category_index = (self.category_index + 1) % len(self.categories)
        return category, phrase


class ButtonManager:
    """Configure single-button controls using gpiozero when available."""

    def __init__(
        self,
        short_press: Callable[[], None],
        long_press: Callable[[], None],
        hold_time: float = 1.2,
        gpio_pin: int = 17,
    ) -> None:
        self.short_press = short_press
        self.long_press = long_press
        self.button = None

        if importlib.util.find_spec("gpiozero") is None:
            print("gpiozero not installed; button disabled. Use Ctrl+C to exit.")
            return

        from gpiozero import Button  # type: ignore

        self.button = Button(gpio_pin, pull_up=True, hold_time=hold_time)
        self.button.when_released = self._handle_release

    def _handle_release(self) -> None:
        if self.button is None:
            return
        if self.button.is_held:
            self.long_press()
        else:
            self.short_press()

    def close(self) -> None:
        if self.button is not None:
            self.button.close()


UPDATE_PERIOD_SECONDS = 5.0


class MarkoshkaApp:
    def __init__(self, driver: Optional[DisplayDriver] = None) -> None:
        self.driver = driver or self._default_driver()
        self.mode = Mode.SEQUENTIAL
        self.sequencer = PhraseSequencer(PHRASE_CATALOGUE)
        self.running = True
        self.pending_overlay: Optional[str] = None
        self.last_category_shown: Optional[str] = None

        self.button = ButtonManager(
            short_press=self.toggle_mode,
            long_press=self.cycle_category,
        )

    def _default_driver(self) -> DisplayDriver:
        address_env = os.getenv("MARKOSHKALCD_ADDR")
        lcd_address = int(address_env, 0) if address_env else 0x27
        try:
            return PD2800DisplayDriver(address=lcd_address)
        except Exception as exc:
            print(f"PD2800 driver unavailable, falling back to console: {exc}")
            return ConsoleDisplayDriver()

    def toggle_mode(self) -> None:
        next_mode = {
            Mode.SEQUENTIAL: Mode.RANDOM,
            Mode.RANDOM: Mode.CATEGORY_SEQUENCE,
            Mode.CATEGORY_SEQUENCE: Mode.SEQUENTIAL,
        }[self.mode]
        self.mode = next_mode
        self.pending_overlay = MODE_DISPLAY_NAMES[self.mode.value]

    def cycle_category(self) -> None:
        if self.mode != Mode.CATEGORY_SEQUENCE:
            self.mode = Mode.CATEGORY_SEQUENCE
        self.sequencer.category_index = (self.sequencer.category_index + 1) % len(
            self.sequencer.categories
        )
        self.sequencer.phrase_index = 0
        category_name = self.sequencer.categories[self.sequencer.category_index].name
        self.pending_overlay = f"Раздел: {category_name}"

    def _show_overlay(self) -> None:
        if self.pending_overlay:
            show_static_message(self.driver, self.pending_overlay)
            time.sleep(1.5)
            self.pending_overlay = None

    def _simulate_loading(
        self, duration: float = 5.0, interval: float = 0.7, ready_duration: float = 5.0
    ) -> None:
        """Fake loading sequence before the first phrase."""

        start = time.monotonic()
        frame = 0
        while True:
            remaining = duration - (time.monotonic() - start)
            if remaining <= 0:
                break

            dots = "." * ((frame % 3) + 1)
            show_static_message(self.driver, f"Маркошка v1.0\nзагружается{dots}")
            frame += 1
            time.sleep(min(interval, max(remaining, 0)))

        show_static_message(self.driver, "Маркошка готова!\nПоехали!")
        time.sleep(ready_duration)

    def run(self) -> None:
        self._simulate_loading()
        next_tick = time.monotonic()
        self.last_category_shown = None

        while self.running:
            self._show_overlay()

            now = time.monotonic()
            if now >= next_tick:
                category, phrase = self.sequencer.next_phrase(self.mode)
                if self.mode != Mode.RANDOM:
                    if category.name != self.last_category_shown:
                        show_message(self.driver, category.name)
                        time.sleep(5.0)
                        self.last_category_shown = category.name
                else:
                    self.last_category_shown = None

                show_message(self.driver, phrase)
                next_tick = time.monotonic() + UPDATE_PERIOD_SECONDS

            time.sleep(0.1)

    def stop(self) -> None:
        self.running = False
        self.button.close()


def main() -> None:
    app = MarkoshkaApp()

    def _signal_handler(_signo, _frame) -> None:
        app.stop()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        app.run()
    finally:
        app.stop()


if __name__ == "__main__":
    main()
