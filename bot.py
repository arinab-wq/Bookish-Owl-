import os
import asyncio
import logging
import random
import re
import httpx
from urllib.parse import urlparse
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from ddgs import DDGS
from rapidfuzz import process, fuzz

logging.basicConfig(level=logging.INFO)
load_dotenv()
TOKEN = os.getenv("BOOKISH_OWL_TOKEN")
if not TOKEN: raise ValueError("Токен не найден!")

bot = Bot(token=TOKEN)
dp = Dispatcher()

user_history, user_settings, user_age_group, user_language, user_search_type = {}, {}, {}, {}, {}

SAFE_DOMAINS = ["litres.ru", "flibusta.is", "fictionbook.ru", "libking.ru", "royallib.com", "litmir.me", "avidreaders.ru", "bookz.ru", "wikipedia.org", "openlibrary.org", "google.com", "books.google.com", "archive.org", "gutenberg.org", "labirint.ru", "ozon.ru", "peopletalk.ru", "litportal.ru", "doi.org", "openalex.org"]

def is_safe_domain(url: str) -> bool:
    try:
        domain = urlparse(url).netloc.lower()
        return any(safe in domain for safe in SAFE_DOMAINS) or "google" in domain or "yandex" in domain
    except: return False

ART_COMPANIONS = {
    "гарри поттер": {
        "painting_name": "Замок на скале", "painting_author": "Каспар Давид Фридрих", "painting_year": "1822", "painting_file": "castle.jpg",
        "music": "«Сюита №3» Иоганна Себастьяна Баха (1720-е)",
        "fun_fact": "🖼️ Совиная тайна:\n\nВ кабинете Дамблдора висят портреты реальных людей! В фильме они стилизованы под Хогвартс.\n\nНажми кнопку ниже, чтобы увидеть коллаж!",
        "secret_paintings": [{"file": "grozny.jpg", "name": "Портрет Ивана Грозного", "author": "Виктор Васнецов", "year": "1897"}],
        "bear_advice": "🐻 «Эту книгу хорошо читать под шум дождя и треск дров в печи.»"
    },
    "мастер и маргарита": {
        "painting_name": "Демон сидящий", "painting_author": "Михаил Врубель", "painting_year": "1890", "painting_file": "demon.jpg",
        "music": "«Лунная соната» Людвига ван Бетховена (1801)",
        "fun_fact": "🖼️ Совиная тайна:\n\nБулгаков писал роман в тяжелые годы. Сцена с балом навеяна его размышлениями о Москве.",
        "secret_paintings": [{"file": "demon_sitting.jpg", "name": "Демон сидящий", "author": "Михаил Врубель", "year": "1890"}],
        "bear_advice": "🐻 «А эту историю лучше читать при свечах.»"
    }
}

AUTHORS_AND_TITLES = ["пушкин", "гарри поттер", "толстой", "достоевский", "шестерка воронов", "эрагон", "хроники нарнии", "перси джексон", "властелин колец", "мастер и маргарита"]

def correct_typos(text: str) -> str:
    words = text.split()
    corrected_words = []
    for word in words:
        clean_word = re.sub(r'[^\w\s]', '', word)
        if not clean_word: corrected_words.append(word); continue
        match, score, _ = process.extractOne(clean_word.lower(), AUTHORS_AND_TITLES, scorer=fuzz.ratio)
        corrected_words.append(word.replace(clean_word, match) if score > 80 else word)
    return " ".join(corrected_words)

HARD_FORBIDDEN = ["терроризм", "экстремизм", "наркотики", "оружие", "взрывчатка", "суицид", "убийство", "нацизм", "фашизм", "педофилия"]
ADULT_MARKERS = ["18+", "эротика", "эротический", "хоррор", "ужасы", "взрослый", "секс", "порно", "порнография", "интим", "для взрослых", "хентай"]
BAD_WORDS_REGEX = re.compile(r'\b(хуй|хуя|хуе|пизд|бляд|ебан|ебал|ебл|заеб|мраз|гандон|долбо)[а-я]*\b', re.IGNORECASE)
SAFE_CHILDREN_WORDS = ["детск", "сказк", "для детей", "малыш", "дошкольн", "гарри поттер", "хроники нарнии", "перси джексон"]
LITERARY_CONTEXT = ["литература", "история", "психология", "роман", "исследование", "анализ", "книга", "учебник", "статья", "наука", "культура", "искусство"]

def has_hard_forbidden(text: str) -> bool: return any(word in text.lower() for word in HARD_FORBIDDEN)
def has_bad_language(text: str) -> bool: return bool(BAD_WORDS_REGEX.search(text))
def is_adult_query(query: str) -> bool:
    text_lower = query.lower()
    if any(safe_word in text_lower for safe_word in SAFE_CHILDREN_WORDS): return False
    if not any(marker in text_lower for marker in ADULT_MARKERS): return False
    if any(ctx in text_lower for ctx in LITERARY_CONTEXT): return False
    return True
def has_emoji_or_stickers(message: types.Message) -> bool:
    return bool(message.sticker or message.animation or (message.text and re.search(r'[\U00010000-\U0010ffff]', message.text)))

def get_main_keyboard(): return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="✍️ Автор"), KeyboardButton(text="📖 Книга")], [KeyboardButton(text="🎭 Жанр"), KeyboardButton(text="🔬 Наука")], [KeyboardButton(text="🌐 Язык поиска")]], resize_keyboard=True)
def get_language_keyboard(): return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🇷🇺 Русский"), KeyboardButton(text="🇬🇧 English")], [KeyboardButton(text="🇪🇸 Español"), KeyboardButton(text="⬅️ Назад в меню")]], resize_keyboard=True)
def get_age_keyboard(): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Да, мне есть 18", callback_data="age_yes")], [InlineKeyboardButton(text="❌ Нет, я младше", callback_data="age_no")]])
def get_age_category_keyboard(): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🧸 Мне от 6 до 12", callback_data="rec_kids")], [InlineKeyboardButton(text="🌱 Мне 13 и больше", callback_data="rec_teens")]])

def get_settings_keyboard(user_id):
    settings = user_settings.get(user_id, {'paintings': True, 'music': True})
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"🖼️ Картины: {'✅ Вкл' if settings['paintings'] else '❌ Выкл'}", callback_data="toggle_paint")], [InlineKeyboardButton(text=f"🎵 Музыка: {'✅ Вкл' if settings['music'] else '❌ Выкл'}", callback_data="toggle_music")], [InlineKeyboardButton(text="🔇 Отключить всё", callback_data="toggle_all")]])

def get_art_keyboard(book_key):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎨 Посмотреть картину", callback_data=f"art_paint_{book_key}")], [InlineKeyboardButton(text="🎵 Услышать музыку", callback_data=f"art_music_{book_key}")], [InlineKeyboardButton(text="🖼️ Совиная тайна", callback_data=f"art_fact_{book_key}")], [InlineKeyboardButton(text="🐻 В гостях у Медведя", callback_data=f"art_bear_{book_key}")], [InlineKeyboardButton(text="🔇 Только книга", callback_data=f"art_none_{book_key}")]])

def get_format_keyboard(query): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📥 Скачать EPUB", callback_data=f"fmt_epub_{query}")], [InlineKeyboardButton(text="📥 Скачать PDF", callback_data=f"fmt_pdf_{query}")], [InlineKeyboardButton(text="📖 Читать онлайн", callback_data=f"fmt_online_{query}")]])
def get_fun_fact_keyboard(): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔗 Посмотреть коллаж (PeopleTalk)", url="https://peopletalk.ru/article/iskusstvo-v-garri-pottere-7-realnyh-kartin-kotorye-ty-tochno-ne-zamechal-na-stenah-hogvartsa/")]])

FIRST_WELCOMES = ["Здравствуй, добрый странник! 🦉🐻\n\nЯ — Сова, хранительница Книги. Скажи, какую дорогу выберем сегодня?", "Приветствую у костра, странник! 🔥🦉\n\nКаждая книга — это вселенная. Какую звезду зажжем сегодня?"]
RETURNING_WELCOMES = ["С возвращением, Странник! 🌌🦉\n\nМожет, отыщем историю о далеких мирах?", "Звезды шепнули мне, что ты вернулся... ✨🐻\n\nС чего начнем?", "С возвращением! 🌊🦉\n\nПоищем историю о морских глубинах?"]

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_settings: user_settings[user_id] = {'paintings': True, 'music': True}
    if user_id not in user_language: user_language[user_id] = "🇷🇺 Русский"
    if user_id not in user_history: user_history[user_id] = 1; welcome = random.choice(FIRST_WELCOMES)
    else: user_history[user_id] += 1; welcome = random.choice(RETURNING_WELCOMES)
    await message.answer(welcome + "\n\n💡 /settings — настройки, /reset — заново.", reply_markup=get_main_keyboard())

@dp.message(Command("reset"))
async def cmd_reset(message: types.Message):
    user_id = message.from_user.id
    if user_id in user_history: del user_history[user_id]
    user_settings[user_id] = {'paintings': True, 'music': True}; user_language[user_id] = "🇷🇺 Русский"
    await message.answer("🦉🐻 Сова и Медведь перелистнули страницу...\n\nНапиши /start, чтобы начать заново.")

@dp.message(F.text == "🌐 Язык поиска")
async def change_language(message: types.Message): await message.answer("Выбери язык для поиска:", reply_markup=get_language_keyboard())

@dp.message(F.text.in_({"🇷🇺 Русский", "🇬🇧 English", "🇪🇸 Español"}))
async def set_language(message: types.Message):
    user_language[message.from_user.id] = message.text
    await message.answer(f"Отлично! Ищем на языке: {message.text}.", reply_markup=get_main_keyboard())

@dp.message(F.text == "⬅️ Назад в меню")
async def back_to_menu(message: types.Message): await message.answer("Возвращаемся в меню.", reply_markup=get_main_keyboard())

@dp.message(Command("settings"))
async def cmd_settings(message: types.Message): await message.answer("⚙️ Настройки путешествия:", reply_markup=get_settings_keyboard(message.from_user.id))

@dp.callback_query(F.data.startswith("toggle_"))
async def process_settings(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in user_settings: user_settings[user_id] = {'paintings': True, 'music': True}
    if callback.data == "toggle_paint": user_settings[user_id]['paintings'] = not user_settings[user_id]['paintings']
    elif callback.data == "toggle_music": user_settings[user_id]['music'] = not user_settings[user_id]['music']
    elif callback.data == "toggle_all":
        state = not (user_settings[user_id]['paintings'] or user_settings[user_id]['music'])
        user_settings[user_id]['paintings'] = state; user_settings[user_id]['music'] = state
    await callback.message.edit_reply_markup(reply_markup=get_settings_keyboard(user_id)); await callback.answer("Обновлено!")

@dp.message(F.text.in_({"✍️ Автор", "📖 Книга", "🎭 Жанр", "🔬 Наука"}))
async def ask_category(message: types.Message):
    user_id = message.from_user.id
    if "Наука" in message.text: user_search_type[user_id] = "article"; await message.answer("О какой научной теме узнать?")
    else:
        user_search_type[user_id] = "book"
        prompts = {"✍️ Автор": "Имя автора:", "📖 Книга": "Название книги:", "🎭 Жанр": "Жанр:"}
        await message.answer(prompts[message.text])

@dp.callback_query(F.data.startswith("age_"))
async def process_age_choice(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if callback.data == "age_yes": user_age_group[user_id] = "adult"; await callback.message.edit_text("Благодарю! Отправляюсь в лес...\nНапиши запрос еще раз.")
    else: user_age_group[user_id] = "restricted"; await callback.message.edit_text("Понимаю! Сколько тебе лет?", reply_markup=get_age_category_keyboard())
    await callback.answer()

@dp.callback_query(F.data.startswith("rec_"))
async def process_recommendation(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if callback.data == "rec_kids": user_age_group[user_id] = "kids"; books = [{"title": "Гарри Поттер", "author": "Роулинг"}, {"title": "Хроники Нарнии", "author": "Льюис"}]
    else: user_age_group[user_id] = "teens"; books = [{"title": "Шестерка воронов", "author": "Бардуго"}, {"title": "Голодные игры", "author": "Коллинз"}]
    text = "Тебе точно понравится:\n\n" + "\n".join([f"📚 {b['title']} — {b['author']}" for b in books]) + "\n\n✨ Напиши название!"
    await callback.message.edit_text(text); await callback.answer()

@dp.callback_query(F.data.startswith("art_"))
async def process_art_choice(callback: types.CallbackQuery):
    data = callback.data.split("_"); action, book_key = data[1], data[2]
    arts = ART_COMPANIONS.get(book_key)
    if not arts: await callback.answer("Ой, Сова потеряла страницу..."); return
    if action == "none": await callback.message.edit_text("🦉🐻 Только книга — так только книга!"); await callback.answer(); return
    if action == "paint":
        try: await callback.message.answer_photo(photo=FSInputFile(arts['painting_file']), caption=f"🎨 {arts['painting_name']}\n{arts['painting_author']}, {arts['painting_year']} год.\n\n«Картина словно шепчет о книге...»")
        except Exception: await callback.message.answer(f"🦉 Сова шепчет: «Это напоминает мне о {arts['painting_name']}...»")
    elif action == "music": await callback.message.answer(f"🎵 Сова напевает:\n\n«Включи {arts['music']}. Пусть музыка станет мостом...»")
    elif action == "fact":
        await callback.message.answer(arts['fun_fact'], reply_markup=get_fun_fact_keyboard())
        if user_settings.get(callback.from_user.id, {}).get('paintings', True):
            for secret in arts.get('secret_paintings', []):
                try: await callback.message.answer_photo(photo=FSInputFile(secret['file']), caption=f"🖼️ {secret['name']}\n{secret['author']}, {secret['year']} год.")
                except Exception: pass
    elif action == "bear": await callback.message.answer(arts['bear_advice'])
    await callback.answer()

@dp.callback_query(F.data.startswith("fmt_"))
async def process_format_choice(callback: types.CallbackQuery):
    parts = callback.data.split("_", 2)
    if len(parts) < 3: await callback.answer("Ошибка формата"); return
    fmt, book_title = parts[1], parts[2]
    new_query = f"{book_title} {fmt} скачать" if fmt in ["epub", "pdf"] else f"{book_title} читать онлайн"
    await callback.message.edit_text(f"🦉 Сова летит искать {fmt.upper()}...")
    await execute_search(callback.message, new_query, callback.from_user.id, "book")
    await callback.answer()

async def execute_search(message: types.Message, query: str, user_id: int, search_type: str):
    lang = user_language.get(user_id, "🇷🇺 Русский"); lang_suffix = " english" if lang == "🇬🇧 English" else " español" if lang == "🇪🇸 Español" else ""
    status_msg = await message.answer(f"📖 Шелестят страницы...\n\n🦉 Сова ищет «{query}»...")
    try:
        results = await asyncio.get_event_loop().run_in_executor(None, perform_search, query, search_type, lang_suffix)
        if not results: await status_msg.edit_text("🦉🐻 Ничего не нашлось. Попробуй иначе!"); return
        await status_msg.delete(); await message.answer("✨ Страницы зашелестели:")
        unique_titles, unique_results = set(), []
        for res in results:
            title, url, snippet = res.get("title", "Без названия"), res.get("href", ""), res.get("body", "Нет описания.")
            if not is_safe_domain(url) or has_bad_language(title + snippet) or has_hard_forbidden(title + snippet): continue
            if title[:30].lower() in unique_titles: continue
            unique_titles.add(title[:30].lower()); unique_results.append((title, url, snippet[:150] + "..."))
        if not unique_results: await message.answer("🦉🐻 Все ссылки ведут на небезопасные площадки. Попробуем иначе?"); return
        for title, url, snippet in unique_results:
            await message.answer(f"📜 {title}\n\n{snippet}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔗 Открыть", url=url)]]), disable_web_page_preview=True)
        if search_type == "book" and query not in AUTHORS_AND_TITLES:
            await message.answer("🦉🐻 «В каком формате читать?»", reply_markup=get_format_keyboard(query))
        for key, arts in ART_COMPANIONS.items():
            if key in query and (user_settings.get(user_id, {}).get('paintings') or user_settings.get(user_id, {}).get('music')):
                await message.answer("🦉🐻 «У нас есть кое-что интересное!»", reply_markup=get_art_keyboard(key)); break
    except Exception as e: logging.error(f"Ошибка: {e}"); await status_msg.edit_text("⚠️ Ветер сорвал страницы. Попробуй снова.")

@dp.message()
async def handle_search(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_settings: user_settings[user_id] = {'paintings': True, 'music': True}
    if user_id not in user_language: user_language[user_id] = "🇷🇺 Русский"
    if has_emoji_or_stickers(message): await message.answer("🦉🐻 В Книге живут только буквы и слова! Напиши запрос текстом."); return
    query = message.text.strip().lower()
    if has_bad_language(query): await message.answer("🦉🐻 Мы ценим добрые слова. Давай обойдем эту топь?"); return
    if has_hard_forbidden(query): await message.answer("🦉🐻 Не пойдем туда! Поищем светлое."); return
    if is_adult_query(query):
        if user_age_group.get(user_id) in ["kids", "teens", "restricted"]: await message.answer("🦉🐻 Для тебя есть много добрых историй! Поищем светлое?"); return
        else: await message.answer("🌲 Тёмный лес...\n\n⚠️ Вам есть 18 лет?", reply_markup=get_age_keyboard()); return
    if "стих" in query: await message.answer("🌿 «Мороз и солнце; день чудесный!...» — А. С. Пушкин.\n\nХочешь сборник?"); return
    corrected_query = correct_typos(query)
    if corrected_query != query: await message.answer(f"🦉 Ветер переставил буквы! Поняла как: {corrected_query}.")
    await execute_search(message, corrected_query, user_id, user_search_type.get(user_id, "book"))

def perform_search(query: str, search_type: str, lang_suffix: str):
    if search_type == "article":
        try:
            r = httpx.get("https://api.openalex.org/works", params={"search": query, "per_page": 5}, timeout=10.0)
            if r.status_code == 200: return [{"title": i.get("title", "Без названия"), "href": i.get("doi") or i.get("id", ""), "body": "Научная статья."} for i in r.json().get("results", [])]
        except: pass
        return []
    else:
        try:
            with DDGS() as ddgs: return list(ddgs.text(f"{query}{lang_suffix} книга EPUB OR PDF скачать", max_results=5))
        except: pass
        try:
            r = httpx.get(f"https://www.googleapis.com/books/v1/volumes?q={query}&maxResults=5", timeout=10.0)
            if r.status_code == 200: return [{"title": f"{v.get('title')} ({', '.join(v.get('authors', ['Автор']))})", "href": v.get("previewLink"), "body": "Google Books."} for v in (i.get("volumeInfo", {}) for i in r.json().get("items", [])) if v.get("previewLink")]
        except: pass
        try:
            r = httpx.get("https://archive.org/advancedsearch.php", params={"q": f'title:("{query}")', "fl[]": ["identifier", "title"], "rows": 3, "output": "json"}, timeout=10.0)
            if r.status_code == 200: return [{"title": f"{d.get('title')} (Archive.org)", "href": f"https://archive.org/details/{d.get('identifier')}", "body": "Archive.org."} for d in r.json().get("response", {}).get("docs", []) if d.get("identifier")]
        except: pass
    return []

async def main():
    print("🦉🐻 Бот запущен...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: print("Бот остановлен.")
