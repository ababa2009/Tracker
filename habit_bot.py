import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

logging.basicConfig(level=logging.INFO)

TOKEN = "8411884620:AAG4khGULyAUpAQQrBFBffrLmeYEa5x6xBE"  # Вставьте свой токен
bot = Bot(token=TOKEN)
dp = Dispatcher()

DB_FILE = "habits.db"
user_states = {}  # для хранения состояния пользователя


# ===== Инициализация базы данных =====
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Таблица привычек
    c.execute('''
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            times TEXT,
            UNIQUE(user_id, name)
        )
    ''')
    # Таблица выполнений привычек
    c.execute('''
        CREATE TABLE IF NOT EXISTS completions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id INTEGER,
            date TEXT
        )
    ''')
    conn.commit()
    conn.close()


# ===== Функции работы с базой =====
def add_habit(user_id, name):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO habits (user_id, name, times) VALUES (?, ?, ?)", (user_id, name, ""))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return False
    conn.close()
    return True


def set_habit_times(user_id, name, times):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE habits SET times=? WHERE user_id=? AND name=?", (",".join(times), user_id, name))
    conn.commit()
    conn.close()


def get_habits(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT name, times FROM habits WHERE user_id=?", (user_id,))
    data = c.fetchall()
    conn.close()
    return data


def get_habit_id(user_id, habit_name):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id FROM habits WHERE user_id=? AND name=?", (user_id, habit_name))
    habit = c.fetchone()
    conn.close()
    return habit[0] if habit else None


def mark_done(user_id, habit_name):
    habit_id = get_habit_id(user_id, habit_name)
    if not habit_id:
        return False
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("SELECT id FROM completions WHERE habit_id=? AND date=?", (habit_id, today))
    if c.fetchone():
        conn.close()
        return False  # Уже отмечено
    c.execute("INSERT INTO completions (habit_id, date) VALUES (?, ?)", (habit_id, today))
    conn.commit()
    conn.close()
    return True


def mark_not_done(user_id, habit_name):
    habit_id = get_habit_id(user_id, habit_name)
    if not habit_id:
        return False
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("DELETE FROM completions WHERE habit_id=? AND date=?", (habit_id, today))
    conn.commit()
    conn.close()
    return True


def delete_habit(user_id, habit_name):
    habit_id = get_habit_id(user_id, habit_name)
    if not habit_id:
        return False
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM completions WHERE habit_id=?", (habit_id,))
    c.execute("DELETE FROM habits WHERE id=?", (habit_id,))
    conn.commit()
    conn.close()
    return True


def get_completions(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT h.name, c.date
        FROM completions c
        JOIN habits h ON c.habit_id = h.id
        WHERE h.user_id=?
    """, (user_id,))
    data = c.fetchall()
    conn.close()
    return data


# ===== Клавиатуры =====
def main_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить привычку", callback_data="add")],
            [InlineKeyboardButton(text="📋 Мои привычки", callback_data="list")],
            [InlineKeyboardButton(text="📈 Статистика", callback_data="stats")]
        ]
    )


def habits_keyboard(habits):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=f"✔ {h[0]}", callback_data=f"done:{h[0]}"),
                InlineKeyboardButton(text="⏰ Время", callback_data=f"time:{h[0]}"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete:{h[0]}")
            ] for h in habits
        ]
    )


def reminder_keyboard(habit_name):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Выполнено", callback_data=f"done:{habit_name}"),
                InlineKeyboardButton(text="❌ Не выполнено", callback_data=f"notdone:{habit_name}")
            ]
        ]
    )


# ===== Команда /start =====
@dp.message(Command("start"))
async def start(msg: Message):
    await msg.answer(
        "🔥 <b>Привет! Это трекер привычек с реальной базой данных SQLite.</b>\nВыбирай действие 👇",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )


# ===== Добавление привычки =====
@dp.callback_query(F.data == "add")
async def ask_habit(cb: CallbackQuery):
    user_states[cb.from_user.id] = "waiting_habit"
    await cb.message.answer("Напиши название новой привычки:")
    await cb.answer()


@dp.message()
async def handle_message(msg: Message):
    user = msg.from_user.id
    state = user_states.get(user)

    # Название привычки
    if state == "waiting_habit":
        habit = msg.text.strip()
        if not habit:
            await msg.answer("⚠ Название привычки не может быть пустым. Попробуй снова:")
            return
        if not add_habit(user, habit):
            await msg.answer("⚠ Такая привычка уже есть! Введи другое название:")
            return
        user_states[user] = f"waiting_time:{habit}"
        await msg.answer("Отлично! Введи время напоминания в формате HH:MM, можно несколько через запятую")
        return

    # Время напоминания
    if state and state.startswith("waiting_time:"):
        habit = state.split(":")[1]
        times = [t.strip() for t in msg.text.split(",")]
        valid_times = []
        invalid_times = []
        for t in times:
            try:
                datetime.strptime(t, "%H:%M")
                valid_times.append(t)
            except:
                invalid_times.append(t)
        if not valid_times:
            await msg.answer("⛔ Все введённые времена неверны. Попробуй ещё раз.")
            return
        if invalid_times:
            await msg.answer(f"⚠ Некорректные времена проигнорированы: {', '.join(invalid_times)}")
        set_habit_times(user, habit, valid_times)
        user_states[user] = None
        await msg.answer(f"✅ Напоминания для <b>{habit}</b> установлены: {', '.join(valid_times)}", parse_mode="HTML")


# ===== Список привычек =====
@dp.callback_query(F.data == "list")
async def list_habits(cb: CallbackQuery):
    habits = get_habits(cb.from_user.id)
    if not habits:
        await cb.message.answer("😕 У тебя пока нет привычек.")
        return await cb.answer()
    await cb.message.answer("📋 Выбери привычку:", reply_markup=habits_keyboard(habits))
    await cb.answer()


# ===== Отметка выполнения =====
@dp.callback_query(F.data.startswith("done:"))
async def done(cb: CallbackQuery):
    habit_name = cb.data.split(":")[1]
    if mark_done(cb.from_user.id, habit_name):
        await cb.message.answer(f"🎉 Отлично! Ты выполнил привычку <b>{habit_name}</b>!", parse_mode="HTML")
    else:
        await cb.message.answer(f"⚠ Сегодня привычка <b>{habit_name}</b> уже выполнена!", parse_mode="HTML")
    await cb.answer()


@dp.callback_query(F.data.startswith("notdone:"))
async def not_done(cb: CallbackQuery):
    habit_name = cb.data.split(":")[1]
    if mark_not_done(cb.from_user.id, habit_name):
        await cb.message.answer(f"❌ Привычка <b>{habit_name}</b> помечена как не выполненная сегодня.", parse_mode="HTML")
    else:
        await cb.message.answer(f"⚠ Привычка <b>{habit_name}</b> ещё не была выполнена.", parse_mode="HTML")
    await cb.answer()


# ===== Удаление привычки =====
@dp.callback_query(F.data.startswith("delete:"))
async def delete(cb: CallbackQuery):
    habit_name = cb.data.split(":")[1]
    if delete_habit(cb.from_user.id, habit_name):
        await cb.message.answer(f"🗑 Привычка <b>{habit_name}</b> удалена.", parse_mode="HTML")
    else:
        await cb.message.answer(f"⚠ Привычка <b>{habit_name}</b> не найдена.", parse_mode="HTML")
    await cb.answer()


# ===== Статистика =====
@dp.callback_query(F.data == "stats")
async def stats(cb: CallbackQuery):
    habits = get_habits(cb.from_user.id)
    completions = get_completions(cb.from_user.id)
    if not habits:
        await cb.message.answer("Нет привычек для статистики.")
        return await cb.answer()

    text = "📈 <b>Статистика:</b>\n\n"
    for habit, times in habits:
        streak = 0
        today = datetime.now()
        habit_dates = [c[1] for c in completions if c[0] == habit]
        # Считаем серию подряд
        while True:
            day_str = (today - timedelta(days=streak)).strftime("%Y-%m-%d")
            if day_str in habit_dates:
                streak += 1
            else:
                break
        next_time = "—"
        for t in times.split(","):
            if datetime.strptime(t, "%H:%M") >= datetime.now():
                next_time = t
                break
        text += f"• {habit}: streak {streak}, следующее напоминание: {next_time}\n"
    await cb.message.answer(text, parse_mode="HTML")
    await cb.answer()


# ===== Фоновая задача напоминаний с кнопками =====
async def reminders():
    while True:
        now = datetime.now().strftime("%H:%M")
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT user_id, name, times FROM habits")
        data = c.fetchall()
        conn.close()
        for user_id, name, times in data:
            if not times:
                continue
            if now in times.split(","):
                try:
                    await bot.send_message(
                        user_id,
                        f"🔔 Напоминание! Выполни привычку: <b>{name}</b>",
                        reply_markup=reminder_keyboard(name),
                        parse_mode="HTML"
                    )
                except:
                    pass
        await asyncio.sleep(60)


# ===== Запуск бота =====
async def main():
    init_db()
    asyncio.create_task(reminders())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

