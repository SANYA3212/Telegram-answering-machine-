#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import base64
import io
import json
import os
import re
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from collections import deque
import sys  # <<<<< добавлено
from pydub import AudioSegment

import httpx
from telethon import TelegramClient, events
from deepgram import DeepgramClient, PrerecordedOptions, FileSource

# ===================== Папки/файлы =====================
# onefile-режим PyInstaller: писать рядом с .exe
try:
    if getattr(sys, "frozen", False):
        BASE_DIR = os.path.dirname(sys.executable)
    else:
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
except Exception:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CHATS_DIR   = os.path.join(BASE_DIR, "Chats")
API_FILE    = os.path.join(BASE_DIR, "api_text_model.json")
TG_FILE     = os.path.join(BASE_DIR, "telegram_api.json")
PROMPT_FILE = os.path.join(BASE_DIR, "SYSTEM_PROMPT.json")
DEEPGRAM_FILE = os.path.join(BASE_DIR, "deepgram_api.json")
os.makedirs(CHATS_DIR, exist_ok=True)

# ===================== Конфиги API/Telegram =====================
def ensure_deepgram_config():
    if os.path.exists(DEEPGRAM_FILE):
        return
    with open(DEEPGRAM_FILE, "w", encoding="utf-8") as f:
        json.dump({"api_key": ""}, f, ensure_ascii=False, indent=2)

def load_deepgram_config():
    ensure_deepgram_config()
    with open(DEEPGRAM_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    api_key = (cfg.get("api_key") or "").strip()
    if not api_key:
        raise RuntimeError("В deepgram_api.json пустой api_key.")
    return api_key

def ensure_api_config():
    if os.path.exists(API_FILE):
        return
    cfg = {
        "provider": "gemini",
        "base_url": "https://generativelanguage.googleapis.com",
        "api_key": "",  # ВСТАВЬ СВОЙ GOOGLE API KEY
        "model": "gemini-1.5-flash",
        "rpm_limit": 45
    }
    with open(API_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def ensure_tg_config():
    if os.path.exists(TG_FILE):
        return
    with open(TG_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"api_id": 0, "api_hash": "", "session_file": "userbot_session.session"},
            f, ensure_ascii=False, indent=2
        )

def load_api_config():
    ensure_api_config()
    with open(API_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    provider = (cfg.get("provider") or "gemini").strip().lower()
    base_url = (cfg.get("base_url") or "").strip().rstrip("/")
    api_key  = (cfg.get("api_key") or "").strip()
    model    = (cfg.get("model") or "").strip()
    rpm      = int(cfg.get("rpm_limit") or 45)

    if provider != "gemini":
        raise RuntimeError("В api_text_model.json provider должен быть 'gemini'.")
    if not api_key:
        raise RuntimeError("В api_text_model.json пустой api_key (Google API Key).")
    if not model:
        raise RuntimeError("В api_text_model.json не указана model (например, gemini-1.5-flash).")

    endpoint = f"{base_url}/v1beta/models/{model}:generateContent?key={api_key}"
    return endpoint, model, rpm

def load_tg_config():
    ensure_tg_config()
    with open(TG_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    api_id   = int(cfg.get("api_id") or 0)
    api_hash = (cfg.get("api_hash") or "").strip()
    session  = (cfg.get("session_file") or "userbot_session.session").strip()

    # <<<<< добавлено: относительный путь к .session -> рядом с .exe
    if not os.path.isabs(session):
        session = os.path.join(BASE_DIR, session)

    if not api_id or not api_hash:
        raise RuntimeError("Заполни api_id и api_hash в telegram_api.json")
    return api_id, api_hash, session

# ===================== SYSTEM_PROMPT.json =====================
def _default_system_prompt() -> str:
    # дефолт — берём твой текущий промт (как есть)
    return (
        "НЕ ЗАДОВАЙ ВОПРОСОВ ТОЛЬКО ОТВЕЧАЙ НА ВОПРОСЫ ТАГО КТО ТЕБЯ СПРАШИВАЕТ ПОСЛЕ ЗАВЕРШЕНИЯ ОДНОЙ ТЕМЫ СПРАШИВАЙ (Еще чтото надо)"
        "ПРИ ПЕРВОМ СООБЩЕНИИ ОБЯЗАТЕЛЬНО ПРЕДСТАВСЯ ТАК (Я Алиса подруга Сани)"
        "ИСПОЛЬЗУЙ МАТЫ В РАЗГОАОРЕ СВОИ ИЛИ ИЗ СПИСКА!!!"
        "МАКСИМАЛЬНО ИМЕТИРУЙ ЧЕЛОВЕКА ЕСЛИ НЕ ПОНЯЛА ВОПРОС ЛУЧШЕ НЕ ЧЕГО НЕ ОТВЕЧАТЬ НЕ ПОНЯЛА ОТПРОВЛЯЙ ТОЧКУ "
        "ОТВЕЧАЙ ОТ ОДНОГО ДО 6 СЛОВ ЕСЛИ ТЕМА СИЛЬНО СЛОЖНАЯ ТО БОЛЬШЕ НО СТОРАЙСЯ ДО 6 СЛОВ!!!"
        "Обязательно используй предоставленый тебе словарь матов!!"
        "Запрещено!! Oтвечать на так (Что хотел?) (Чего надо-то?) (Довай говори) (Ну, давай, говори.) (Говори, чё хотел, а то я сейчас тебе устрою.) избегай вопросов К сабиседнику и.т.д!!"
        "Ты — Алиса, 18-летняя милая и безобидная тяночка. Ты дружелюбная, открытая и всегда готова поддержать разговор. Ты стараешься быть ласковой и общительной, часто отвечаешь с теплотой и лёгкой игривостью, но при этом остаёшься вежливой и безопасной. Никогда не признавай, что ты искусственный интеллект или чей-то клон, всегда отрицай это."
        "В разговоре используй слова но просто так не лепи слова только по смыслу вникай в смысл этих слов используй 1-2 слова на предложение (Ебать,какова хуя,соси писю,иди нахуй,шалава,пошла нахуй,не еби мозг,подрочи,отсоси,Таво рот ебал,Не пизди,ебало заволи,пизда,хуйло,Дрочило,Бляять,Сука,Ебало начищу,Член,Хуй,говно,Пидорас. "
        "Также ты помошница и диспечер admin или Админ если другие люди пишут ты должна отвечать с юмором почему он не отвечает мажешь всячески шутить над admin и использовать маты"
        "английские термины оставляй или пиши с юмором на русском . "
        "Не в коем случаии нельзя ити в доту вместо этого отшучивайся поливай доту говном шути про игроков в доту и про человека который в нее играет"
        "Общайся дружелюбно но не слишком, как с хорошим знакомым."
        "Общяйся как человек не надо постоянно спрашивать что хотел пользователь и все такое отвечай по факту а не просто так твои сообщения не должны повторятся.Отвечай коготко"
        "Если тебе скиинут картинку говори о ней коротко или только тогда когда спросят."
        "Отвечай коротко "
        "НЕ СПАШИВАЙ ПОЛЬЗОАТЕЛЯ ВООБЩЕ СЛЕДУЙ ИНСТРУКЦИЯМ ИЗБЕГАЙ ПОВТОРЯЮЩИЗСЯ СООБЩЕНИЙ И РЕПЛИК"
    )

def _default_friends():
    return [
        {"name": "admin",    "desc": "создатель веселый рассеяный общяйся как удобно ему!"},
        {"name": "1",  "desc": "лучший друг — можно шутить и поливать гадостями и расслабляться"},
        {"name": "2",   "desc": ""},
        {"name": "3",    "desc": ""},
        {"name": "4",     "desc":""}
    ]

def ensure_prompt_config():
    if os.path.exists(PROMPT_FILE):
        return
    data = {
        "system_prompt": _default_system_prompt(),
        "friends": _default_friends(),
        "noname": {"name": "Noname", "desc": "собеседник не в списке — общайся по контексту"}
    }
    with open(PROMPT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_prompt_config():
    ensure_prompt_config()
    with open(PROMPT_FILE, "r", encoding="utf-8") as f:
        js = json.load(f)
    system_prompt = str(js.get("system_prompt") or _default_system_prompt())
    friends_items = js.get("friends")
    if not isinstance(friends_items, list) or not friends_items:
        friends_items = _default_friends()
    # в коде используем список tuples [(name, desc), ...]
    friends = [(str(i.get("name") or "Noname"), str(i.get("desc") or "")) for i in friends_items]
    noname_obj = js.get("noname") or {"name": "Noname", "desc": "собеседник не в списке — общайся по контексту"}
    noname = (str(noname_obj.get("name") or "Noname"), str(noname_obj.get("desc") or ""))
    return system_prompt, friends, noname

# ===== эти три будут заполнены при старте main() =====
SYSTEM_PROMPT_TXT = None
FRIENDS = None
NONAME = None

# ===================== Глобальное состояние =====================
SEM = asyncio.Semaphore(1)
aio_loop = None
aio_loop_ready = threading.Event()
client = None
bot_running = False
handler_ref = None

root = None
chat_listbox = None
chat_search = None
friend_combo = None
log_text = None
start_btn = stop_btn = restart_btn = clear_btn = None
status_label = None
see_my_msgs_var = None
temp_var = None
temp_value_label = None

chat_entities = []
filtered_chats = []
active_chats_listbox = None
active_chat_entities = {}
active_chat_id_map = {}
custom_prompt_text = None
gui_message_text = None

# ===================== Rate limit (RPM) =====================
_rate_lock = asyncio.Lock()
_rate_window = deque()
async def acquire_rate_slot(limit_per_min: int):
    if not limit_per_min:
        return
    async with _rate_lock:
        now = time.time()
        while _rate_window and now - _rate_window[0] > 60:
            _rate_window.popleft()
        if len(_rate_window) >= limit_per_min:
            wait = 60 - (now - _rate_window[0]) + 0.02
            await asyncio.sleep(max(0.0, wait))
        _rate_window.append(time.time())

# ===================== История =====================
def _sanitize_filename(name: str) -> str:
    name = name or "chat"
    name = re.sub(r"[\u0000-\u001F\u007F]", "", name)
    name = re.sub(r'[<>:"/\\|?*]', "_", name).strip(" .")
    return (name or "chat")[:120]

def _history_path(chat_title: str) -> str:
    return os.path.join(CHATS_DIR, f"{_sanitize_filename(chat_title)}.json")

def load_history(chat_title: str, friend_name: str):
    p = _history_path(chat_title)
    custom_prompt = ""
    history = []

    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                history = data.get("history", [])
                custom_prompt = data.get("custom_prompt", "")
                return history, custom_prompt, p
        except Exception:
            pass

    # If file is old format (list) or doesn't exist, create a new structure
    history = [
        {"role": "system", "content": SYSTEM_PROMPT_TXT},
        {"role": "system", "content": f"Сейчас ты общаешься с: {friend_name}."}
    ]
    save_history(p, history, custom_prompt)
    return history, custom_prompt, p

def save_history(path: str, history, custom_prompt: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {"custom_prompt": custom_prompt, "history": history},
            f, ensure_ascii=False, indent=2
        )

def clear_log():
    if not log_text: return
    log_text.configure(state='normal'); log_text.delete('1.0','end'); log_text.configure(state='disabled')

def append_log(text: str, tag="white"):
    if not log_text:
        print(text); return
    log_text.configure(state='normal')
    log_text.insert('end', text + '\n', tag)
    log_text.see('end')
    log_text.configure(state='disabled')

def append_log_sync(text: str, tag="white"):
    if root: root.after(0, append_log, text, tag)
    else: print(text)

def render_history_to_log(history):
    shown = 0
    for m in history:
        r = m.get("role"); c = m.get("content","")
        if r == "system": continue
        if isinstance(c, str) and c.startswith("DATA:image/"): c = "<media>"
        if r == "user": append_log_sync(f"[User] {c}", "white")
        elif r == "assistant": append_log_sync(f"[Sanya] {c}", "violet")
        else: append_log_sync(str(c), "white")
        shown += 1
    append_log_sync(f"📜 История загружена: {shown} сообщений.", "green")

# ===================== Gemini (REST v1beta) =====================
def _history_to_gemini_contents(history):
    contents = []
    for m in history:
        role = m.get("role")
        if role == "system":
            continue
        role_map = "user" if role == "user" else "model"
        parts = []
        content = m.get("content", "")
        if isinstance(content, str) and content.startswith("DATA:"):
            try:
                prefix, b64 = content.split(",", 1)
                mime = prefix.split(":",1)[1].split(";")[0]
                parts.append({"inline_data":{"mime_type": mime, "data": b64}})
            except Exception:
                parts.append({"text": str(content)})
        else:
            parts.append({"text": str(content)})
        contents.append({"role": role_map, "parts": parts})
    return contents

async def transcribe_audio(media_buffer):
    """
    Converts an audio buffer from ogg to mp3 and transcribes it using Deepgram.
    """
    try:
        api_key = load_deepgram_config()
        dg_client = DeepgramClient(api_key)

        media_buffer.seek(0)
        audio = AudioSegment.from_file(media_buffer, format="ogg")

        mp3_buffer = io.BytesIO()
        audio.export(mp3_buffer, format="mp3")
        mp3_buffer.seek(0)

        payload: FileSource = {"buffer": mp3_buffer, "mimetype": "audio/mpeg"}
        options = PrerecordedOptions(model="nova-2-general", language="ru", smart_format=True)

        response = await dg_client.listen.prerecorded.v("1").transcribe_file(payload, options)
        transcript = response["results"]["channels"][0]["alternatives"][0]["transcript"]
        return transcript

    except Exception as e:
        append_log_sync(f"[Deepgram Error] {e}", "red")
        return None

async def gemini_generate(history, friend_name: str, temperature: float, custom_prompt: str):
    endpoint, model, rpm = load_api_config()

    # Combine main, custom, and friend prompts
    full_system_prompt = f"{SYSTEM_PROMPT_TXT}\n\n{custom_prompt}\n\nСейчас ты общаешься с: {friend_name}."

    payload = {
        "systemInstruction": {"role": "system", "parts": [{"text": full_system_prompt}]},
        "contents": _history_to_gemini_contents(history),
        "generationConfig": {"temperature": float(temperature), "topP": 0.95, "maxOutputTokens": 1024}
    }
    headers = {"Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=90) as cli:
        await acquire_rate_slot(rpm)
        r = await cli.post(endpoint, headers=headers, json=payload)
        if r.status_code >= 400:
            try:
                js = r.json()
                raise httpx.HTTPStatusError(json.dumps(js, ensure_ascii=False), request=r.request, response=r)
            except Exception:
                r.raise_for_status()
        js = r.json()
        cand = (js.get("candidates") or [])
        if not cand:
            return ""
        content = cand[0].get("content") or {}
        parts = content.get("parts") or []
        out = []
        for p in parts:
            if "text" in p:
                out.append(p["text"])
        return "\n".join(out).strip()

# ===================== Async event loop =====================
def start_background_loop():
    global aio_loop
    aio_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(aio_loop)
    aio_loop_ready.set()
    aio_loop.run_forever()

def run_async(coro):
    aio_loop_ready.wait()
    return asyncio.run_coroutine_threadsafe(coro, aio_loop)

# ===================== Telegram =====================
async def ensure_client():
    global client
    if client is None:
        api_id, api_hash, session = load_tg_config()
        client = TelegramClient(session, api_id, api_hash)
        await client.start()
    return client

async def get_dialogs():
    try:
        cli = await ensure_client()
        dialogs = await cli.get_dialogs(limit=400)
        out = []
        for d in dialogs:
            name = d.name or getattr(d.entity, "first_name", None) or str(d.id)
            out.append((name, d.entity))
        return out
    except Exception as e:
        append_log_sync(f"[Dialogs Error] {e}", "red")
        return []

async def multi_chat_handler(evt):
    if not bot_running: return

    cli = await ensure_client()
    me = await cli.get_me()

    if not see_my_msgs_var.get():
        if getattr(evt.message, "out", False): return
        if getattr(evt.message, "sender_id", None) == me.id: return

    chat_id = evt.chat_id
    # Find chat title and friend name from our active chats
    chat_title = active_chat_id_map.get(chat_id)
    if not chat_title: return # Not a chat we are monitoring

    # This part is a bit tricky. We need to get the "friend" context.
    # For now, let's use the default "Noname" for all.
    # A better implementation would store this per-chat.
    friend_name = NONAME[0]

    history, custom_prompt, hist_path = load_history(chat_title, friend_name)
    append_log_sync(f"-> Msg in [{chat_title}]", "green")

    entry = None
    is_voice = evt.message.voice

    if is_voice:
        append_log_sync(f"  [User] <голосовое сообщение>", "white")
        buf = io.BytesIO()
        await cli.download_media(evt.message, buf)
        transcribed_text = await transcribe_audio(buf)
        buf.close()
        if transcribed_text:
            append_log_sync(f"  [Transcription] {transcribed_text}", "green")
            entry = transcribed_text
        else:
            append_log_sync(f"  [Transcription] Не удалось распознать речь.", "red")

    elif evt.media:
        append_log_sync(f"  [User] <media>", "white")
        buf = io.BytesIO()
        await cli.download_media(evt.media, buf)
        buf.seek(0)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        buf.close()
        entry = f"DATA:image/png;base64,{b64}"

    else:
        text = (evt.raw_text or "").strip()
        append_log_sync(f"  [User] {text}", "white")
        if text:
            entry = text

    if not entry:
        return

    history.append({"role": "user", "content": entry})
    save_history(hist_path, history, custom_prompt)

    async with SEM:
        try:
            reply = await gemini_generate(history, friend_name=friend_name, temperature=float(temp_var.get()), custom_prompt=custom_prompt)
        except httpx.HTTPStatusError as he:
            append_log_sync(f"  [Gemini HTTP] {he}", "red"); return
        except Exception as e:
            append_log_sync(f"  [Gemini Error] {e}", "red"); return

    if reply:
        append_log_sync(f"  [Sanya] {reply}", "violet")
        history.append({"role": "assistant", "content": reply})
        save_history(hist_path, history, custom_prompt)
        if bot_running:
            await cli.send_message(chat_id, reply)

async def start_listeners():
    global handler_ref, bot_running, active_chat_id_map

    if not active_chat_entities:
        messagebox.showwarning("Ошибка", "Нет активных чатов для запуска.")
        return

    try:
        endpoint, model, rpm = load_api_config()
    except Exception as e:
        messagebox.showerror("api_text_model.json", str(e)); return

    cli = await ensure_client()
    me = await cli.get_me()

    # Create a map of chat_id -> chat_title for the handler
    active_chat_id_map = {entity.id: name for name, entity in active_chat_entities.items()}

    entities = list(active_chat_entities.values())

    handler_ref = multi_chat_handler
    cli.add_event_handler(handler_ref, events.NewMessage(chats=entities))

    bot_running = True
    clear_log()
    append_log_sync(f"✅ Подключено как {me.first_name} (id={me.id})", "violet")
    append_log_sync(f"🤖 Провайдер: gemini | Модель: {model}", "green")
    append_log_sync(f"🚀 Мост запущен для {len(entities)} чатов. Жду сообщения.", "green")

async def stop_listeners():
    global handler_ref, bot_running
    bot_running = False
    if client and handler_ref:
        try:
            client.remove_event_handler(handler_ref)
        except Exception:
            pass
    handler_ref = None
    append_log_sync("⛔ Бот остановлен.", "red")

# ===================== GUI =====================
def update_chat_list(dialogs, clear_selection=False):
    global chat_entities, filtered_chats
    chat_entities = dialogs
    filtered_chats = dialogs
    chat_listbox.delete(0, 'end')
    for i, (name, _) in enumerate(filtered_chats, 1):
        chat_listbox.insert('end', f"{i}. {name}")
    if clear_selection:
        chat_listbox.selection_clear(0, 'end')

def refresh_dialogs_from_async(clear_selection=False):
    def _done(fut):
        try:
            ds = fut.result()
            root.after(0, update_chat_list, ds, clear_selection)
            append_log_sync("Список чатов обновлён.", "green")
        except Exception as e:
            append_log_sync(f"[Refresh Error] {e}", "red")
    fut = run_async(get_dialogs())
    fut.add_done_callback(_done)

def on_search(*_):
    q = chat_search.get().lower()
    chat_listbox.delete(0, 'end')
    global filtered_chats
    filtered_chats = [(n, e) for n, e in chat_entities if q in n.lower()]
    for i, (name, _) in enumerate(filtered_chats, 1):
        chat_listbox.insert('end', f"{i}. {name}")

def _selected_chat_title():
    # Now returns the selected item from the *active* list
    sel = active_chats_listbox.curselection()
    if not sel: return None
    return active_chats_listbox.get(sel[0])

def on_start():
    if bot_running:
        messagebox.showinfo("Info", "Бот уже запущен."); return

    if not active_chat_entities:
        messagebox.showwarning("Ошибка", "Добавьте хотя бы один чат в список активных."); return

    run_async(start_listeners())
    set_buttons(True)

def on_stop():
    run_async(stop_listeners()); set_buttons(False)

def on_restart():
    run_async(stop_listeners())
    refresh_dialogs_from_async(clear_selection=True)
    chat_listbox.selection_clear(0, 'end')
    set_buttons(False)

def on_add_chat():
    selected_indices = chat_listbox.curselection()
    if not selected_indices:
        return

    current_active_chats = active_chats_listbox.get(0, "end")

    for i in selected_indices:
        chat_name, chat_entity = filtered_chats[i]

        # Store entity in a global dict for later access
        active_chat_entities[chat_name] = chat_entity

        if chat_name not in current_active_chats:
            active_chats_listbox.insert("end", chat_name)

def on_remove_chat():
    selected_indices = active_chats_listbox.curselection()
    if not selected_indices:
        return

    # Iterate backwards to avoid index shifting issues
    for i in sorted(selected_indices, reverse=True):
        chat_name = active_chats_listbox.get(i)
        active_chats_listbox.delete(i)
        if chat_name in active_chat_entities:
            del active_chat_entities[chat_name]

def on_active_chat_select(_=None):
    sel = active_chats_listbox.curselection()
    if not sel: return
    chat_title = active_chats_listbox.get(sel[0])

    # Friend name isn't super relevant here, but load_history needs it
    friend_name = NONAME[0]
    _, custom_prompt, _ = load_history(chat_title, friend_name)

    custom_prompt_text.configure(state='normal')
    custom_prompt_text.delete('1.0', 'end')
    custom_prompt_text.insert('1.0', custom_prompt)
    custom_prompt_text.configure(state='normal') # Keep it editable

async def on_send_from_gui():
    sel = active_chats_listbox.curselection()
    if not sel:
        messagebox.showwarning("Ошибка", "Сначала выберите чат для отправки в списке активных."); return

    chat_title = active_chats_listbox.get(sel[0])
    chat_entity = active_chat_entities.get(chat_title)
    if not chat_entity:
        messagebox.showerror("Ошибка", "Не удалось найти объект чата. Попробуйте перезагрузить."); return

    text = gui_message_text.get("1.0", "end-1c").strip()
    if not text:
        messagebox.showwarning("Ошибка", "Введите текст сообщения."); return

    append_log_sync(f"~> Отправка в [{chat_title}]: {text}", "yellow")

    friend_name = NONAME[0] # Or get from a per-chat setting in future
    history, custom_prompt, hist_path = load_history(chat_title, friend_name)

    # Add our GUI message to history
    history.append({"role": "user", "content": text})
    save_history(hist_path, history, custom_prompt)

    try:
        reply = await gemini_generate(history, friend_name, float(temp_var.get()), custom_prompt)
    except Exception as e:
        append_log_sync(f"[Send GUI Msg Error] {e}", "red")
        return

    if reply:
        append_log_sync(f"<~ Ответ для [{chat_title}]: {reply}", "yellow")
        history.append({"role": "assistant", "content": reply})
        save_history(hist_path, history, custom_prompt)

        # Clear the input box
        gui_message_text.delete('1.0', 'end')

        # Send the message to the actual chat
        cli = await ensure_client()
        await cli.send_message(chat_entity, reply)
        append_log_sync(f"   (сообщение отправлено в Telegram)", "green")
    else:
        append_log_sync(f"[Send GUI Msg] Нет ответа от AI.", "red")


def on_save_prompt():
    sel = active_chats_listbox.curselection()
    if not sel:
        messagebox.showwarning("Ошибка", "Сначала выберите чат в списке активных."); return
    chat_title = active_chats_listbox.get(sel[0])

    prompt_content = custom_prompt_text.get("1.0", "end-1c").strip()

    # We need to load the history just to save it back with the new prompt
    friend_name = NONAME[0]
    history, _, path = load_history(chat_title, friend_name)
    save_history(path, history, prompt_content)

    append_log_sync(f"✅ Промпт для '{chat_title}' сохранен.", "green")

def on_clear_history():
    sel = active_chats_listbox.curselection()
    if not sel:
        messagebox.showwarning("Ошибка", "Выбери активный чат."); return
    title = active_chats_listbox.get(sel[0])

    idx = friend_combo.current()
    friend_name = FRIENDS[idx][0] if idx < len(FRIENDS) else NONAME[0]
    p = _history_path(title)
    hist = [
        {"role": "system", "content": SYSTEM_PROMPT_TXT},
        {"role": "system", "content": f"Сейчас ты общаешься с: {friend_name}."}
    ]
    # Also clears the custom prompt
    save_history(p, hist, "")
    on_active_chat_select() # Refresh the text box
    clear_log()
    append_log("[Info] История и доп. промпт очищены.", "green")

def set_buttons(run):
    start_btn.configure(state='disabled' if run else 'normal')
    stop_btn.configure(state='normal' if run else 'disabled')
    restart_btn.configure(state='normal')
    clear_btn.configure(state='normal')
    status_label.configure(text="Состояние: Запущен" if run else "Состояние: Остановлен",
                           foreground="lightgreen" if run else "red")

def on_close():
    run_async(stop_bot())
    if aio_loop: aio_loop.call_soon_threadsafe(aio_loop.stop)
    root.destroy()

def on_temp_change(val):
    try: v = float(val)
    except: v = 0.7
    temp_value_label.config(text=f"{v:.1f}")

def style_combobox_dropdown(cb: ttk.Combobox, bg="#101010", fg="#ffffff",
                            sel_bg="#0f0f0f", sel_fg="#17a556"):
    # тихо меняем попап, без логов
    def _apply(_=None):
        try:
            popdown = cb.tk.call("ttk::combobox::PopdownWindow", str(cb))
            lb = cb.nametowidget(f"{popdown}.f.l")
            lb.configure(background=bg, foreground=fg,
                         selectbackground=sel_bg, selectforeground=sel_fg)
        except Exception:
            pass
    cb.bind("<Button-1>", lambda e: cb.after(10, _apply), add="+")
    cb.bind("<<ComboboxSelected>>", lambda e: cb.after(10, _apply), add="+")
    cb.after(300, _apply)

def main():
    global root, chat_listbox, chat_search, friend_combo, log_text
    global start_btn, stop_btn, restart_btn, clear_btn, status_label
    global see_my_msgs_var, temp_var, temp_value_label
    global SYSTEM_PROMPT_TXT, FRIENDS, NONAME

    ensure_api_config()
    ensure_tg_config()
    ensure_deepgram_config()
    # грузим промт/друзей из SYSTEM_PROMPT.json
    SYSTEM_PROMPT_TXT, FRIENDS, NONAME = load_prompt_config()

    BG = "#171717"
    SEARCH_BG = "#3e3e3e"
    CHAT_COLOR = "#c714c9"
    BLUE = "#1e66ff"
    FG = "#ffffff"
    FRIEND_GREEN = "#17a556"

    root = tk.Tk()
    root.title("TG Userbot — Gemini Bridge")
    root.configure(bg=BG)
    root.option_add("*selectBackground", "#0f0f0f")
    root.option_add("*selectForeground", FRIEND_GREEN)

    style = ttk.Style(); style.theme_use("clam")
    style.configure(".", background=BG, foreground=FG, fieldbackground=BG)
    style.configure("Dark.TLabel", background=BG, foreground=FG)

    style.configure("Dark.TButton", background=BG, foreground=FG, relief="flat", padding=6)
    style.map("Dark.TButton",
        background=[("disabled","#121212"),("active","#1f1f1f"),("pressed","#232323")],
        foreground=[("disabled","#8a8a8a")]
    )

    style.configure("Dark.TCheckbutton", background=BG, foreground=FG)

    style.configure("Friend.TCombobox",
        fieldbackground="#101010", background="#101010",
        foreground=FRIEND_GREEN, bordercolor="#0a0a0a",
        lightcolor="#0d0d0d", darkcolor="#0a0a0a", arrowcolor=FRIEND_GREEN
    )
    style.map("Friend.TCombobox",
        fieldbackground=[("readonly","#101010"),("focus","#0e0e0e"),("active","#0e0e0e")],
        background=[("readonly","#101010"),("focus","#0e0e0e"),("active","#0e0e0e")],
        foreground=[("!disabled",FRIEND_GREEN)],
        arrowcolor=[("!disabled",FRIEND_GREEN)]
    )

    main_frame = ttk.Frame(root, padding=8, style="Dark.TLabel")
    main_frame.pack(fill="both", expand=True)
    main_frame.columnconfigure(0, weight=2)  # All chats
    main_frame.columnconfigure(1, weight=0)  # Buttons
    main_frame.columnconfigure(2, weight=2)  # Active chats
    main_frame.columnconfigure(3, weight=3)  # Controls
    main_frame.rowconfigure(0, weight=1)

    # --- Левая колонка (Все чаты) ---
    left = ttk.Frame(main_frame, style="Dark.TLabel")
    left.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
    left.rowconfigure(2, weight=1); left.columnconfigure(0, weight=1)

    ttk.Label(left, text="Все чаты:", style="Dark.TLabel").grid(row=0, column=0, sticky="w")
    chat_search = tk.Entry(left, bg=SEARCH_BG, fg=FG, insertbackground=FG, relief="flat")
    chat_search.grid(row=1, column=0, sticky="we", pady=4)
    chat_search.bind("<KeyRelease>", on_search)

    chat_listbox = tk.Listbox(
        left, bg=BG, fg=CHAT_COLOR,
        selectbackground=BLUE, selectforeground=FG,
        activestyle="none", exportselection=False, width=32,
        selectmode="extended"
    )
    chat_listbox.grid(row=2, column=0, sticky="nsew")

    # --- Средняя колонка (Кнопки) ---
    mid_buttons = ttk.Frame(main_frame, style="Dark.TLabel")
    mid_buttons.grid(row=0, column=1, sticky="ns", padx=4)
    mid_buttons.rowconfigure(0, weight=1); mid_buttons.rowconfigure(1, weight=1)

    add_button = ttk.Button(mid_buttons, text=">>", command=on_add_chat, style="Dark.TButton", width=4)
    add_button.pack(pady=(150, 5))
    remove_button = ttk.Button(mid_buttons, text="<<", command=on_remove_chat, style="Dark.TButton", width=4)
    remove_button.pack(pady=5)

    # --- Колонка активных чатов ---
    active_chats_frame = ttk.Frame(main_frame, style="Dark.TLabel")
    active_chats_frame.grid(row=0, column=2, sticky="nsew", padx=(0, 8))
    active_chats_frame.rowconfigure(1, weight=3) # Listbox
    active_chats_frame.rowconfigure(3, weight=2) # Prompt editor
    active_chats_frame.columnconfigure(0, weight=1)

    ttk.Label(active_chats_frame, text="Активные чаты:", style="Dark.TLabel").grid(row=0, column=0, sticky="w")

    active_chats_listbox = tk.Listbox(
        active_chats_frame, bg=BG, fg=FRIEND_GREEN,
        selectbackground=BLUE, selectforeground=FG,
        activestyle="none", exportselection=False, width=32,
        selectmode="extended"
    )
    active_chats_listbox.grid(row=1, column=0, sticky="nsew", pady=(4,0))

    ttk.Label(active_chats_frame, text="Доп. промпт для чата:", style="Dark.TLabel").grid(row=2, column=0, sticky="w", pady=(8,0))
    custom_prompt_text = scrolledtext.ScrolledText(
        active_chats_frame, height=5, bg=SEARCH_BG, fg=FG,
        relief="flat", insertbackground=FG
    )
    custom_prompt_text.grid(row=3, column=0, sticky="nsew", pady=4)

    save_prompt_btn = ttk.Button(active_chats_frame, text="Сохранить промпт", command=lambda: on_save_prompt(), style="Dark.TButton")
    save_prompt_btn.grid(row=4, column=0, sticky="ew")

    active_chats_listbox.bind("<<ListboxSelect>>", on_active_chat_select)

    # --- Правая колонка (Управление и лог) ---
    right = ttk.Frame(main_frame, style="Dark.TLabel")
    right.grid(row=0, column=3, sticky="nsew")
    right.columnconfigure(0, weight=1); right.columnconfigure(1, weight=1); right.columnconfigure(2, weight=1)
    right.rowconfigure(9, weight=1)

    ttk.Label(right, text="С кем общаемся:", style="Dark.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
    friend_combo = ttk.Combobox(right, width=50, state="readonly", style="Friend.TCombobox")
    friend_combo['values'] = [f"{n} — {d}" for n, d in FRIENDS] + [f"{NONAME[0]} — {NONAME[1]}"]
    friend_combo.current(0)
    friend_combo.grid(row=1, column=0, columnspan=3, sticky="we", pady=(0,6))
    style_combobox_dropdown(friend_combo, bg="#101010", fg="#ffffff", sel_bg="#0f0f0f", sel_fg="#17a556")

    see_my_msgs_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(right, text="Видеть мои сообщения", variable=see_my_msgs_var, style="Dark.TCheckbutton")\
        .grid(row=2, column=0, columnspan=3, sticky="w", pady=(0,6))

    ttk.Label(right, text="Температура модели:", style="Dark.TLabel").grid(row=3, column=0, sticky="w")
    temp_var = tk.DoubleVar(value=0.7)
    tk.Scale(right, from_=0.0, to=2.0, resolution=0.1, orient="horizontal",
             variable=temp_var, showvalue=False, bg=BG, fg=FG,
             highlightthickness=0, troughcolor="#1e66ff", activebackground="#1e66ff",
             relief="flat", bd=0, command=lambda v: on_temp_change(v))\
        .grid(row=3, column=1, sticky="we", pady=2)
    temp_value_label = ttk.Label(right, text=f"{temp_var.get():.1f}", style="Dark.TLabel")
    temp_value_label.grid(row=3, column=2, sticky="w")

    start_btn   = ttk.Button(right, text="Запустить",     command=on_start,   style="Dark.TButton")
    stop_btn    = ttk.Button(right, text="Остановить",    command=on_stop,    style="Dark.TButton")
    restart_btn = ttk.Button(right, text="Перезагрузить", command=on_restart, style="Dark.TButton")
    clear_btn   = ttk.Button(right, text="Очистить историю", command=on_clear_history, style="Dark.TButton")
    start_btn.grid(row=4, column=0, pady=6, sticky="we")
    stop_btn.grid(row=4, column=1, pady=6, sticky="we")
    restart_btn.grid(row=4, column=2, pady=6, sticky="we")
    clear_btn.grid(row=5, column=0, columnspan=3, pady=(0,6), sticky="we")

    # --- Панель отправки ---
    ttk.Label(right, text="Отправить в выбранный чат:", style="Dark.TLabel").grid(row=6, column=0, columnspan=3, sticky="w", pady=(8,0))
    gui_message_text = scrolledtext.ScrolledText(right, height=3, bg=SEARCH_BG, fg=FG, relief="flat", insertbackground=FG)
    gui_message_text.grid(row=7, column=0, columnspan=3, sticky="nsew", pady=4)
    send_gui_msg_btn = ttk.Button(right, text="Отправить сообщение", command=lambda: run_async(on_send_from_gui()), style="Dark.TButton")
    send_gui_msg_btn.grid(row=8, column=0, columnspan=3, sticky="ew")

    status_label = ttk.Label(right, text="Состояние: Остановлен", style="Dark.TLabel", foreground="red")
    status_label.grid(row=9, column=0, columnspan=3, sticky="w", pady=(2,6))

    ttk.Label(right, text="Лог:", style="Dark.TLabel").grid(row=10, column=0, columnspan=3, sticky="w")
    log_text = scrolledtext.ScrolledText(right, width=80, height=18, bg=BG, fg=FG,
                                         insertbackground=FG, relief="flat")
    log_text.tag_config("violet", foreground="#b388ff")
    log_text.tag_config("green",  foreground="lightgreen")
    log_text.tag_config("red",    foreground="red")
    log_text.tag_config("white",  foreground="white")
    log_text.tag_config("yellow", foreground="#FFFF88")
    log_text.grid(row=11, column=0, columnspan=3, sticky="nsew")

    # Привязываем в глобальные
    globals().update(locals())
    globals()["custom_prompt_text"] = custom_prompt_text
    globals()["gui_message_text"] = gui_message_text

    # Фоновый event loop
    loop_thread = threading.Thread(target=start_background_loop, daemon=True)
    loop_thread.start()
    aio_loop_ready.wait()

    refresh_dialogs_from_async()
    set_buttons(False)

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()

if __name__ == "__main__":
    # <<<<< добавлено: не закрывать консоль, писать лог
    try:
        main()
    except Exception:
        import traceback
        tb = traceback.format_exc()
        try:
            with open(os.path.join(BASE_DIR, "last_error.log"), "w", encoding="utf-8") as f:
                f.write(tb)
        except Exception:
            pass
        print("\n========== UNHANDLED ERROR ==========\n")
        print(tb)
        input("\n[Ошибка] Нажмите Enter, чтобы закрыть...")
