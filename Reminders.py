# Reminders
Модуль для напоминании
# -*- coding: utf-8 -*-
# meta developer: @ST_Modules
# scope: hikka_only
# scope: hikka_min 1.3.0

import asyncio
import datetime
import re
from typing import Union

from hikkatl.tl.types import Message

from .. import loader, utils


@loader.tds
class RemindersMod(loader.Module):
    """Модуль для напоминаний и отложенных сообщений"""

    strings = {
        "name": "Reminders",
        "remind_usage": "🚫 <b>Использование:</b> <code>.remind <время> <текст></code>\nПример: <code>.remind 30m купить хлеб</code>",
        "timer_usage": "🚫 <b>Использование:</b> <code>.timer <время> <текст></code>\nПример: <code>.timer 22:00 всем спокойной ночи</code>",
        "remind_set": "✅ <b>Напоминание установлено!</b>\n⏰ <b>Через:</b> {}\n📝 <b>Текст:</b> <code>{}</code>",
        "timer_set": "✅ <b>Таймер установлен!</b>\n⏰ <b>Время:</b> {}\n📝 <b>Текст:</b> <code>{}</code>",
        "invalid_time": "🚫 <b>Неверный формат времени!</b>\nИспользуйте: 30s, 10m, 2h, 1d",
        "remind_arrived": "⏰ <b>Напоминание!</b>\n📝 {}",
        "timer_arrived": "⏰ <b>Таймер сработал!</b>\n📝 {}",
    }

    async def client_ready(self, client, db):
        self._db = db
        self._client = client
        # Восстанавливаем активные напоминания при перезагрузке
        await self._restore_reminders()

    async def _restore_reminders(self):
        """Восстановление напоминаний после перезагрузки"""
        reminders = self._db.get(__name__, "active_reminders", {})
        for remind_id, remind_data in reminders.items():
            asyncio.create_task(self._wait_and_remind(remind_id, remind_data))

    def _parse_time(self, time_str: str) -> Union[int, None]:
        """Парсит время из строки в секунды"""
        time_str = time_str.lower()
        patterns = {
            "s": r"(\d+)s",  # секунды
            "m": r"(\d+)m",  # минуты
            "h": r"(\d+)h",  # часы
            "d": r"(\d+)d",  # дни
            "time": r"(\d{1,2}):(\d{2})",  # время HH:MM
        }

        # Проверяем форматы с суффиксами
        for unit, pattern in patterns.items():
            if unit == "time":
                continue
            match = re.match(pattern, time_str)
            if match:
                value = int(match.group(1))
                multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
                return value * multipliers[unit]

        # Проверяем формат времени HH:MM
        time_match = re.match(patterns["time"], time_str)
        if time_match:
            hours = int(time_match.group(1))
            minutes = int(time_match.group(2))
            
            now = datetime.datetime.now()
            target_time = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
            
            # Если указанное время уже прошло сегодня, переносим на завтра
            if target_time <= now:
                target_time += datetime.timedelta(days=1)
            
            return int((target_time - now).total_seconds())

        return None

    async def _wait_and_remind(self, remind_id: str, remind_data: dict):
        """Ожидание и отправка напоминания"""
        try:
            await asyncio.sleep(remind_data["delay"])
            
            # Отправляем напоминание
            await self._client.send_message(
                remind_data["chat_id"],
                self.strings["remind_arrived"].format(remind_data["text"])
            )
            
            # Удаляем из активных напоминаний
            reminders = self._db.get(__name__, "active_reminders", {})
            reminders.pop(remind_id, None)
            self._db.set(__name__, "active_reminders", reminders)
            
        except Exception as e:
            self._db.set(__name__, "active_reminders", {})
            raise e

    @loader.command()
    async def remind(self, message: Message):
        """Установить напоминание - .remind <время> <текст>"""
        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, self.strings["remind_usage"])
            return

        # Парсим время и текст
        parts = args.split(" ", 1)
        if len(parts) < 2:
            await utils.answer(message, self.strings["remind_usage"])
            return

        time_str, text = parts
        delay = self._parse_time(time_str)

        if delay is None:
            await utils.answer(message, self.strings["invalid_time"])
            return

        # Сохраняем напоминание
        remind_id = f"remind_{datetime.datetime.now().timestamp()}"
        remind_data = {
            "delay": delay,
            "text": text,
            "chat_id": message.chat_id,
            "message_id": message.id,
        }

        reminders = self._db.get(__name__, "active_reminders", {})
        reminders[remind_id] = remind_data
        self._db.set(__name__, "active_reminders", reminders)

        # Запускаем таймер
        asyncio.create_task(self._wait_and_remind(remind_id, remind_data))

        # Форматируем время для ответа
        time_formatted = self._format_time(delay)
        await utils.answer(
            message,
            self.strings["remind_set"].format(time_formatted, text)
        )

    @loader.command()
    async def timer(self, message: Message):
        """Установить таймер на конкретное время - .timer <время> <текст>"""
        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, self.strings["timer_usage"])
            return

        # Парсим время и текст
        parts = args.split(" ", 1)
        if len(parts) < 2:
            await utils.answer(message, self.strings["timer_usage"])
            return

        time_str, text = parts
        delay = self._parse_time(time_str)

        if delay is None:
            await utils.answer(message, self.strings["invalid_time"])
            return

        # Сохраняем таймер
        timer_id = f"timer_{datetime.datetime.now().timestamp()}"
        timer_data = {
            "delay": delay,
            "text": text,
            "chat_id": message.chat_id,
            "message_id": message.id,
        }

        reminders = self._db.get(__name__, "active_reminders", {})
        reminders[timer_id] = timer_data
        self._db.set(__name__, "active_reminders", reminders)

        # Запускаем таймер
        asyncio.create_task(self._wait_and_remind(timer_id, timer_data))

        # Получаем время срабатывания
        trigger_time = datetime.datetime.now() + datetime.timedelta(seconds=delay)
        time_formatted = trigger_time.strftime("%H:%M")
        
        await utils.answer(
            message,
            self.strings["timer_set"].format(time_formatted, text)
        )

    def _format_time(self, seconds: int) -> str:
        """Форматирует время в читаемый вид"""
        if seconds < 60:
            return f"{seconds} сек"
        elif seconds < 3600:
            return f"{seconds // 60} мин"
        elif seconds < 86400:
            return f"{seconds // 3600} час"
        else:
            return f"{seconds // 86400} дн"

    async def on_unload(self):
        """Очистка при выгрузке модуля"""
        self._db.set(__name__, "active_reminders", {})
