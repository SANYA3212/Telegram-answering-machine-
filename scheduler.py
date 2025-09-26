import asyncio
import sqlite3
import os
import time
from datetime import datetime, timedelta

DB_FILE = os.path.join(os.path.dirname(__file__), "scheduler.db")

def init_db():
    """Инициализирует базу данных и создает таблицу, если ее нет."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                addressee_name TEXT NOT NULL,
                task_text TEXT NOT NULL,
                execution_time INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'ожидает'
            )
        """)
        conn.commit()

def add_task(chat_id: int, addressee_name: str, task_text: str, execution_time: int):
    """Добавляет новую задачу в базу данных."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO tasks (chat_id, addressee_name, task_text, execution_time) VALUES (?, ?, ?, ?)",
            (chat_id, addressee_name, task_text, execution_time)
        )
        conn.commit()

def get_due_tasks():
    """Возвращает задачи, время выполнения которых наступило."""
    current_time = int(time.time())
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, chat_id, addressee_name, task_text FROM tasks WHERE execution_time <= ? AND status = 'ожидает'",
            (current_time,)
        )
        return cursor.fetchall()

def mark_task_completed(task_id: int):
    """Помечает задачу как выполненную."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE tasks SET status = 'выполнена' WHERE id = ?", (task_id,))
        conn.commit()

async def scheduler_loop(client, log_callback):
    """
    Основной цикл планировщика. Проверяет наличие задач и отправляет уведомления.
    """
    log_callback("⚙️ Планировщик запущен и готов к работе.", "green")
    while True:
        try:
            due_tasks = get_due_tasks()
            for task_id, chat_id, addressee_name, task_text in due_tasks:
                try:
                    message = f"Напоминание для {addressee_name}: {task_text}"
                    await client.send_message(chat_id, message)
                    mark_task_completed(task_id)
                    log_callback(f"✅ Напоминание отправлено: {addressee_name} -> '{task_text}'", "green")
                except Exception as e:
                    log_callback(f"❌ Ошибка отправки напоминания (ID: {task_id}): {e}", "red")
                    # Возможно, стоит добавить логику повторной попытки или пометить как ошибку
                    mark_task_completed(task_id) # Помечаем как выполненную, чтобы не спамить

            await asyncio.sleep(15)  # Проверять каждые 15 секунд
        except Exception as e:
            log_callback(f"❗️ Критическая ошибка в цикле планировщика: {e}", "red")
            await asyncio.sleep(60) # В случае серьезной ошибки, ждем дольше