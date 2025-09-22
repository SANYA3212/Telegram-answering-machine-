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

import httpx
from telethon import TelegramClient, events

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
os.makedirs(CHATS_DIR, exist_ok=True)

# ===================== Конфиги API/Telegram =====================
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
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data, p
        except Exception:
            pass
    hist = [
        {"role": "system", "content": SYSTEM_PROMPT_TXT},
        {"role": "system", "content": f"Сейчас ты общаешься с: {friend_name}."}
    ]
    with open(p, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=2)
    return hist, p

def save_history(path: str, history):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

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

async def gemini_generate(history, friend_name: str, temperature: float):
    endpoint, model, rpm = load_api_config()
    sys_text = f"{SYSTEM_PROMPT_TXT}\nСейчас ты общаешься с: {friend_name}."
    payload = {
        "systemInstruction": {"role": "system", "parts": [{"text": sys_text}]},
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

async def start_bot(chat_entity, friend_name, chat_title):
    global handler_ref, bot_running
    try:
        endpoint, model, rpm = load_api_config()
    except Exception as e:
        messagebox.showerror("api_text_model.json", str(e)); return

    cli = await ensure_client()
    me = await cli.get_me()
    my_id = me.id
    bot_running = True

    history, hist_path = load_history(chat_title, friend_name)

    clear_log()
    append_log_sync(f"✅ Подключено как {me.first_name} (id={my_id})", "violet")
    append_log_sync(f"🤖 Провайдер: gemini | Модель: {model}", "green")
    append_log_sync(f"🔗 Endpoint: {endpoint}", "green")
    append_log_sync(f"📁 История: {os.path.basename(hist_path)}", "green")
    render_history_to_log(history)

    async def handler(evt):
        if not bot_running:
            return
        if not see_my_msgs_var.get():
            if getattr(evt.message, "out", False):
                return
            if getattr(evt.message, "sender_id", None) == my_id:
                return

        text = (evt.raw_text or "").strip()
        media = evt.media
        append_log_sync(f"[User] {'<media>' if media else text}", "white")

        if media:
            buf = io.BytesIO()
            await cli.download_media(media, buf)
            buf.seek(0)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            buf.close()
            entry = f"DATA:image/png;base64,{b64}"
        else:
            entry = text

        history.append({"role": "user", "content": entry})
        save_history(hist_path, history)

        async with SEM:
            try:
                reply = await gemini_generate(history, friend_name=friend_name, temperature=float(temp_var.get()))
            except httpx.HTTPStatusError as he:
                append_log_sync(f"[Gemini HTTP] {he}", "red"); return
            except Exception as e:
                append_log_sync(f"[Gemini Error] {e}", "red"); return

        if reply:
            append_log_sync(f"[Sanya] {reply}", "violet")
            history.append({"role": "assistant", "content": reply})
            save_history(hist_path, history)
            if bot_running:
                await cli.send_message(chat_entity, reply)

    handler_ref = handler
    cli.add_event_handler(handler_ref, events.NewMessage(chats=chat_entity))
    append_log_sync("🚀 Мост запущен — жду сообщения.", "green")

async def stop_bot():
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
    sel = chat_listbox.curselection()
    if not sel: return None
    return filtered_chats[sel[0]][0]

def on_start():
    if bot_running:
        messagebox.showinfo("Info", "Бот уже запущен."); return
    title = _selected_chat_title()
    if not title:
        messagebox.showwarning("Ошибка", "Выбери чат."); return
    entity = filtered_chats[chat_listbox.curselection()[0]][1]
    idx = friend_combo.current()
    friend_name = FRIENDS[idx][0] if idx < len(FRIENDS) else NONAME[0]
    run_async(start_bot(entity, friend_name, title))
    set_buttons(True)

def on_stop():
    run_async(stop_bot()); set_buttons(False)

def on_restart():
    run_async(stop_bot())
    refresh_dialogs_from_async(clear_selection=True)
    chat_listbox.selection_clear(0, 'end')
    set_buttons(False)

def on_clear_history():
    title = _selected_chat_title()
    if not title:
        messagebox.showwarning("Ошибка", "Выбери чат."); return
    idx = friend_combo.current()
    friend_name = FRIENDS[idx][0] if idx < len(FRIENDS) else NONAME[0]
    p = _history_path(title)
    hist = [
        {"role": "system", "content": SYSTEM_PROMPT_TXT},
        {"role": "system", "content": f"Сейчас ты общаешься с: {friend_name}."}
    ]
    save_history(p, hist)
    clear_log()
    append_log("[Info] История очищена и создана заново.", "green")

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
    main_frame.columnconfigure(0, weight=1)
    main_frame.columnconfigure(1, weight=3)
    main_frame.rowconfigure(0, weight=1)

    # левая колонка
    left = ttk.Frame(main_frame, style="Dark.TLabel")
    left.grid(row=0, column=0, sticky="nsew", padx=(0,8))
    left.rowconfigure(2, weight=1)

    ttk.Label(left, text="Поиск чата:", style="Dark.TLabel").grid(row=0, column=0, sticky="w")
    chat_search = tk.Entry(left, bg=SEARCH_BG, fg=FG, insertbackground=FG, relief="flat")
    chat_search.grid(row=1, column=0, sticky="we", pady=4)
    chat_search.bind("<KeyRelease>", on_search)

    chat_listbox = tk.Listbox(
        left, bg=BG, fg=CHAT_COLOR,
        selectbackground=BLUE, selectforeground=FG,
        activestyle="none", exportselection=False, width=32
    )
    chat_listbox.grid(row=2, column=0, sticky="nsew")

    # правая колонка
    right = ttk.Frame(main_frame, style="Dark.TLabel")
    right.grid(row=0, column=1, sticky="nsew")
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

    status_label = ttk.Label(right, text="Состояние: Остановлен", style="Dark.TLabel", foreground="red")
    status_label.grid(row=6, column=0, columnspan=3, sticky="w", pady=(2,6))

    ttk.Label(right, text="Лог:", style="Dark.TLabel").grid(row=7, column=0, columnspan=3, sticky="w")
    log_text = scrolledtext.ScrolledText(right, width=80, height=18, bg=BG, fg=FG,
                                         insertbackground=FG, relief="flat")
    log_text.tag_config("violet", foreground="#b388ff")
    log_text.tag_config("green",  foreground="lightgreen")
    log_text.tag_config("red",    foreground="red")
    log_text.tag_config("white",  foreground="white")
    log_text.grid(row=8, column=0, columnspan=3, sticky="nsew")

    # Привязываем в глобальные
    globals().update(locals())

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
