# -*- coding: utf-8 -*-
# meta developer: @ST_Modules
# meta pic: https://img.icons8.com/fluency/48/000000/reminder.png
# meta banner: https://i.imgur.com/abcdefg.jpg

import asyncio
import datetime
import re
import time
from typing import Union

from telethon.tl.types import Message

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
        "invalid_time": "🚫 <b>Неверный формат времени!</b>\nИспользуйте: 30s, 10m, 2h, 1d или 22:00",
        "remind_arrived": "⏰ <b>Напоминание!</b>\n📝 {}",
        "timer_arrived": "⏰ <b>Таймер сработал!</b>\n📝 {}",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "max_reminders",
                50,
                "Максимальное количество активных напоминаний",
                validator=loader.validators.Integer(minimum=1, maximum=1000)
            )
        )
        self.reminders = {}

    async def client_ready(self, client, db):
        self._db = db
        self._client = client
        # Восстанавливаем активные напоминания при перезагрузке
        await self._restore_reminders()

    async def _restore_reminders(self):
        """Восстановление напоминаний после перезагрузки"""
        try:
            reminders = self._db.get(__name__, "active_reminders", {})
            current_time = time.time()
            
            for remind_id, remind_data in reminders.items():
                # Проверяем, не истекло ли уже напоминание
                if remind_data["end_time"] > current_time:
                    remaining_time = remind_data["end_time"] - current_time
                    asyncio.create_task(
                        self._wait_and_remind(remind_id, remind_data, remaining_time)
                    )
                    self.reminders[remind_id] = remind_data
                else:
                    # Если напоминание истекло, отправляем его сразу
                    try:
                        await self._client.send_message(
                            remind_data["chat_id"],
                            self.strings["remind_arrived"].format(remind_data["text"])
                        )
                    except:
                        pass
            
            # Очищаем старые напоминания
            self._db.set(__name__, "active_reminders", self.reminders)
            
        except Exception as e:
            print(f"Error restoring reminders: {e}")
            self._db.set(__name__, "active_reminders", {})

    def _parse_time(self, time_str: str) -> Union[int, None]:
        """Парсит время из строки в секунды"""
        time_str = time_str.lower().strip()
        
        # Проверяем форматы с суффиксами
        if re.match(r"^\d+[smhd]$", time_str):
            value = int(time_str[:-1])
            unit = time_str[-1]
            multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
            return value * multipliers[unit]

        # Проверяем формат времени HH:MM
        if re.match(r"^\d{1,2}:\d{2}$", time_str):
            try:
                hours, minutes = map(int, time_str.split(':'))
                if 0 <= hours <= 23 and 0 <= minutes <= 59:
                    now = datetime.datetime.now()
                    target_time = now.replace(
                        hour=hours, 
                        minute=minutes, 
                        second=0, 
                        microsecond=0
                    )
                    
                    # Если указанное время уже прошло сегодня, переносим на завтра
                    if target_time <= now:
                        target_time += datetime.timedelta(days=1)
                    
                    return int((target_time - now).total_seconds())
            except:
                return None

        return None

    async def _wait_and_remind(self, remind_id: str, remind_data: dict, delay: float):
        """Ожидание и отправка напоминания"""
        try:
            await asyncio.sleep(delay)
            
            # Отправляем напоминание
            await self._client.send_message(
                remind_data["chat_id"],
                self.strings["remind_arrived"].format(remind_data["text"])
            )
            
            # Удаляем из активных напоминаний
            if remind_id in self.reminders:
                del self.reminders[remind_id]
                self._db.set(__name__, "active_reminders", self.reminders)
            
        except Exception as e:
            print(f"Error in reminder {remind_id}: {e}")
            # При ошибке очищаем все напоминания чтобы избежать проблем
            if remind_id in self.reminders:
                del self.reminders[remind_id]
                self._db.set(__name__, "active_reminders", self.reminders)

    @loader.command()
    async def remind(self, message: Message):
        """Установить напоминание - .remind <время> <текст>"""
        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, self.strings["remind_usage"])
            return

        # Проверяем максимальное количество напоминаний
        if len(self.reminders) >= self.config["max_reminders"]:
            await utils.answer(
                message, 
                f"🚫 <b>Достигнут лимит напоминаний!</b>\nМаксимум: {self.config['max_reminders']}"
            )
            return

        # Парсим время и текст
        parts = args.split(" ", 1)
        if len(parts) < 2:
            await utils.answer(message, self.strings["remind_usage"])
            return

        time_str, text = parts
        delay = self._parse_time(time_str)

        if delay is None or delay <= 0:
            await utils.answer(message, self.strings["invalid_time"])
            return

        # Создаем напоминание
        remind_id = f"remind_{int(time.time() * 1000)}"
        remind_data = {
            "delay": delay,
            "text": text,
            "chat_id": message.chat_id,
            "message_id": message.id,
            "end_time": time.time() + delay,
            "created": time.time()
        }

        # Сохраняем в память и базу данных
        self.reminders[remind_id] = remind_data
        self._db.set(__name__, "active_reminders", self.reminders)

        # Запускаем таймер
        asyncio.create_task(self._wait_and_remind(remind_id, remind_data, delay))

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

        # Проверяем максимальное количество напоминаний
        if len(self.reminders) >= self.config["max_reminders"]:
            await utils.answer(
                message, 
                f"🚫 <b>Достигнут лимит напоминаний!</b>\nМаксимум: {self.config['max_reminders']}"
            )
            return

        # Парсим время и текст
        parts = args.split(" ", 1)
        if len(parts) < 2:
            await utils.answer(message, self.strings["timer_usage"])
            return

        time_str, text = parts
        delay = self._parse_time(time_str)

        if delay is None or delay <= 0:
            await utils.answer(message, self.strings["invalid_time"])
            return

        # Создаем таймер
        timer_id = f"timer_{int(time.time() * 1000)}"
        timer_data = {
            "delay": delay,
            "text": text,
            "chat_id": message.chat_id,
            "message_id": message.id,
            "end_time": time.time() + delay,
            "created": time.time()
        }

        # Сохраняем в память и базу данных
        self.reminders[timer_id] = timer_data
        self._db.set(__name__, "active_reminders", self.reminders)

        # Запускаем таймер
        asyncio.create_task(self._wait_and_remind(timer_id, timer_data, delay))

        # Получаем время срабатывания
        trigger_time = datetime.datetime.now() + datetime.timedelta(seconds=delay)
        time_formatted = trigger_time.strftime("%H:%M")
        
        await utils.answer(
            message,
            self.strings["timer_set"].format(time_formatted, text)
        )

    @loader.command()
    async def reminders(self, message: Message):
        """Показать активные напоминания"""
        if not self.reminders:
            await utils.answer(message, "📝 <b>Активных напоминаний нет</b>")
            return

        text = "⏰ <b>Активные напоминания:</b>\n\n"
        for i, (remind_id, remind_data) in enumerate(self.reminders.items(), 1):
            remaining = int(remind_data["end_time"] - time.time())
            if remaining <= 0:
                continue
                
            time_left = self._format_time(remaining)
            text += f"{i}. {time_left} - {remind_data['text']}\n"

        await utils.answer(message, text)

    def _format_time(self, seconds: int) -> str:
        """Форматирует время в читаемый вид"""
        if seconds < 60:
            return f"{seconds} сек"
        elif seconds < 3600:
            return f"{seconds // 60} мин"
        elif seconds < 86400:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}ч {minutes}м"
        else:
            days = seconds // 86400
            hours = (seconds % 86400) // 3600
            return f"{days}д {hours}ч"

    async def on_unload(self):
        """Очистка при выгрузке модуля"""
        self._db.set(__name__, "active_reminders", self.reminders)
