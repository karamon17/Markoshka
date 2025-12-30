from __future__ import annotations

import importlib.util
import os
import random
import signal
import time
from datetime import datetime
import requests
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

from markoshka.display import (
    ConsoleDisplayDriver,
    DisplayDriver,
    PD2800DisplayDriver,
    PD2800SerialDisplayDriver,
    show_message,
    show_static_message,
)
from markoshka.phrases import Category, PHRASE_CATALOGUE
from config import PORT, BAUD

MODE_DISPLAY_NAMES = {
    "sequential": "Режим: подряд",
    "random": "Режим: рандом",
    "category": "Режим: по разделу",
}


class Mode(str, Enum):
    SEQUENTIAL = "sequential"
    RANDOM = "random"
    CATEGORY_SEQUENCE = "category"
    WEATHER = "weather"


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
        self._prev_mode: Optional[Mode] = None
        # Cache for weather data to avoid repeating API calls more than once per day
        self._weather_cache: Optional[dict] = None

        # Primary button (GPIO17) — existing behavior
        self.mode_button = ButtonManager(
            short_press=self.toggle_mode,
            long_press=self.cycle_category,
            gpio_pin=int(os.getenv("MARKOSHKALCD_BUTTON_PIN", "17")),
        )
        # Second button (GPIO27) — toggle between phrases and weather
        weather_pin = int(os.getenv("MARKOSHKALCD_WEATHER_PIN", "27"))
        self.weather_button = ButtonManager(
            short_press=self.toggle_weather,
            long_press=lambda: None,
            gpio_pin=weather_pin,
        )

    def _default_driver(self) -> DisplayDriver:
        transport = os.getenv("MARKOSHKALCD_TRANSPORT", "serial").lower()
        if transport == "serial":
            port = os.getenv("MARKOSHKALCD_PORT", PORT)
            baud_env = os.getenv("MARKOSHKALCD_BAUD")
            baudrate = int(baud_env) if baud_env else BAUD
            try:
                return PD2800SerialDisplayDriver(port=port, baudrate=baudrate)
            except Exception as exc:
                print(f"PD2800 serial driver unavailable, trying I2C: {exc}")
                transport = "i2c"

        if transport == "i2c":
            address_env = os.getenv("MARKOSHKALCD_ADDR")
            lcd_address = int(address_env, 0) if address_env else 0x27
            try:
                return PD2800DisplayDriver(address=lcd_address)
            except Exception as exc:
                print(f"PD2800 I2C driver unavailable, falling back to console: {exc}")

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

    def toggle_weather(self) -> None:
        """Toggle weather display mode on/off using second button."""
        if self.mode == Mode.WEATHER:
            # restore previous mode
            self.mode = self._prev_mode or Mode.SEQUENTIAL
            self._prev_mode = None
            # show overlay for restored mode
            self.pending_overlay = MODE_DISPLAY_NAMES.get(self.mode.value, "Режим: фразы")
        else:
            # enter weather mode, remember previous
            self._prev_mode = self.mode
            self.mode = Mode.WEATHER
            self.pending_overlay = "Режим: погода"

    def fetch_weather(self) -> Optional[dict]:
        """Fetch weather data. Try OpenWeatherMap if API key provided, otherwise Open-Meteo fallback.

        Environment variables:
        - OPENWEATHER_API_KEY (optional) and WEATHER_CITY (optional)
        - or WEATHER_LAT and WEATHER_LON for Open-Meteo
        """
        # Return cached data if fetched within last 24 hours
        try:
            if self._weather_cache:
                fetched_at = self._weather_cache.get("fetched_at")
                if fetched_at and (time.time() - fetched_at) < 24 * 3600:
                    return self._weather_cache.get("data")

            api_key = os.getenv("OPENWEATHER_API_KEY")
            if api_key:
                city = os.getenv("WEATHER_CITY", "Moscow")
                params = {"q": city, "appid": api_key, "units": "metric", "lang": "ru"}
                resp = requests.get("https://api.openweathermap.org/data/2.5/weather", params=params, timeout=5.0)
                resp.raise_for_status()
                data = resp.json()
                result = {
                    "temp": round(data["main"]["temp"]),
                    "humidity": data["main"].get("humidity"),
                    "wind": round(data.get("wind", {}).get("speed", 0), 1),
                    "city": data.get("name"),
                }
                # cache and return
                self._weather_cache = {"data": result, "fetched_at": time.time()}
                return result

            # Fallback to Open-Meteo (requires lat/lon)
            # Use defaults (Rostov-on-Don) if env not provided
            lat = "47.2357"
            lon = "39.7015"
            if lat and lon:
                params = {
                    "latitude": lat,
                    "longitude": lon,
                    "current_weather": "true",
                    "timezone": "UTC",
                }
                resp = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=5.0)
                resp.raise_for_status()
                data = resp.json()
                current = data.get("current_weather", {})
                # humidity not provided in current_weather — try hourly relativehumidity_2m at current hour
                humidity = None
                try:
                    # best-effort: fetch hourly humidity for the current day/time
                    params_h = {
                        "latitude": lat,
                        "longitude": lon,
                        "hourly": "relativehumidity_2m",
                        "timezone": "UTC",
                    }
                    rh = requests.get("https://api.open-meteo.com/v1/forecast", params=params_h, timeout=5.0)
                    rh.raise_for_status()
                    rhj = rh.json()
                    humidity_values = rhj.get("hourly", {}).get("relativehumidity_2m", [])
                    humidity = humidity_values[0] if humidity_values else None
                except Exception:
                    humidity = None

                result = {
                    "temp": round(current.get("temperature")) if current.get("temperature") is not None else None,
                    "humidity": humidity,
                    "wind": round(current.get("windspeed", 0), 1),
                    "city": None,
                }
                # cache and return
                self._weather_cache = {"data": result, "fetched_at": time.time()}
                return result

            return None
        except Exception:
            return None

    def display_weather(self) -> None:
        data = self.fetch_weather()
        if not data:
            show_static_message(self.driver, "Погода недоступна")
            return
        # First line: time, date, weekday
        now = datetime.now()
        time_str = now.strftime("%H:%M")
        date_str = now.strftime("%d.%m")
        weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        weekday = weekdays[now.isoweekday() - 1]
        first_line = f"{time_str} {date_str} {weekday}"

        # Second line: temp, humidity, wind (concise)
        temp = f"{data.get('temp')}°" if data.get("temp") is not None else "?"
        humidity = f"{data.get('humidity')}%" if data.get("humidity") is not None else "?"
        wind = f"{data.get('wind')}" if data.get("wind") is not None else "?"
        second_line = f"Темп:{temp} Вл:{humidity} Вет:{wind}м/с"

        # Show statically to avoid vertical scrolling; display driver will
        # truncate/pad lines to DISPLAY_WIDTH.
        show_static_message(self.driver, f"{first_line}\n{second_line}")

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
                if self.mode == Mode.WEATHER:
                    # show weather summary
                    self.display_weather()
                    self.last_category_shown = None
                    next_tick = time.monotonic() + UPDATE_PERIOD_SECONDS
                else:
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
