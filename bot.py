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

if not TOKEN:
    raise ValueError("Токен не найден!")

bot = Bot(token=TOKEN)
dp = Dispatcher()

user_history = {}
user_settings = {}
user_art_notified = {}
user_age_group = {}
user_current_book_key = {}
user_language = {}

SAFE_DOMAINS = [
    "litres.ru", "flibusta.is", "fictionbook.ru", "libking.ru", 
    "royallib.com", "litmir.me", "avidreaders.ru", "bookz.ru",
    "wikipedia.org", "openlibrary.org", "google.com", "books.google.com",
    "archive.org", "gutenberg.org", "labirint.ru", "ozon.ru", "peopletalk.ru"
]

def is_safe_domain(url: str) -> bool:
    try:
        domain = urlparse(url).netloc.lower()
        for safe in SAFE_DOMAINS:
            if safe in domain:
                return True
        if "google" in domain or "yandex" in domain:
            return True
        return False
    except:
        return False

ART_COMPANIONS = {
    "гарри поттер": {
        "painting_name": "Замок на скале",
        "painting_author": "Каспар Давид Фридрих",
        "painting_year": "1822",
        "painting_file": "castle.jpg",
        "music": "«Сюита №3» Иоганна Себастьяна Баха (1720-е)",
        "fun_fact": (
            "🖼️ Совиная тайна (из мира кино):\n\n"
            "Оказывается, в кабинете Дамблдора висят портреты реальных людей! Например, Портрет Ивана Грозного кисти Виктора Васнецова и Портрет Нестора Кукольника Карла Брюллова.\n\n"
            "В фильме эти шедевры стилизованы под волшебный мир Хогвартса — художники добавили персонажам магические шляпы.\n\n"
            "Нажми на кнопку ниже, чтобы увидеть этот коллаж своими глазами!"
        ),
        "secret_paintings": [
            {"file": "grozny.jpg", "name": "Портрет Ивана Грозного", "author": "Виктор Васнецов", "year": "1897"},
            {"file": "kukolnik.jpg", "name": "Портрет Нестора Кукольника", "author": "Карл Брюллов", "year": "1836"},
            {"file": "repina.jpg", "name": "Отдых. Портрет В.А. Репиной", "author": "Илья Репин", "year": "1882"}
        ],
        "bear_advice": "🐻 «Странник, эту книгу особенно хорошо читать, когда за окном шумит дождь, а в печи потрескивают дрова. Налей чаю и укройся пледом.»"
    }, #
    "мастер и маргарита": {
        "painting_name": "Демон сидящий",
        "painting_author": "Михаил Врубель",
        "painting_year": "1890",
        "painting_file": "demon.jpg",
        "music": "«Лунная соната» Людвига ван Бетховена (1801)",
        "fun_fact": (
            "🖼️ Совиная тайна:\n\n"
            "Михаил Булгаков писал роман в тяжелые годы, и многие детали его жизни отразились в книге.\n\n"
            "Например, сцена с балом у Сатаны, возможно, навеяна снами и размышлениями автора о мистической Москве."
        ),
        "secret_paintings": [
            {"file": "demon_sitting.jpg", "name": "Демон сидящий", "author": "Михаил Врубель", "year": "1890"}
        ],
        "bear_advice": "🐻 «А эту историю лучше читать при свечах. В ней столько мистики, что обычный свет кажется слишком ярким.»"
    }
}

AUTHORS_AND_TITLES = [
    "пушкин", "гарри поттер", "толстой", "достоевский", "шестерка воронов", 
    "эрагон", "хроники нарнии", "перси джексон", "властелин колец", "мастер и маргарита"
]

def correct_typos(text: str) -> str:
    words = text.split()
    corrected_words = []
    for word in words:
        clean_word = re.sub(r'[^\w\s]', '', word)
        if not clean_word:
            corrected_words.append(word)
            continue
        match, score, _ = process.extractOne(clean_word.lower(), AUTHORS_AND_TITLES, scorer=fuzz.ratio)
        if score > 80:
            corrected_word = word.replace(clean_word, match)
            corrected_words.append(corrected_word)
        else:
            corrected_words.append(word)
    return " ".join(corrected_words)

HARD_FORBIDDEN = ["терроризм", "экстремизм", "наркотики", "оружие", "взрывчатка", "суицид", "убийство", "нацизм", "фашизм", "педофилия"]
ADULT_MARKERS = ["18+", "эротика", "эротический", "хоррор", "ужасы", "взрослый", "секс", "порно", "порнография", "интим", "для взрослых", "хентай", "эротический роман"]
BAD_WORDS_REGEX = re.compile(r'\b(хуй|хуя|хуе|пизд|бляд|ебан|ебал|ебл|заеб|мраз|гандон|долбо)[а-я]*\b', re.IGNORECASE)

SAFE_CHILDREN_WORDS = ["детск", "сказк", "для детей", "малыш", "дошкольн", "гарри поттер", "хроники нарнии", "перси джексон", "красная шапочка", "колобок", "буратино"]
LITERARY_CONTEXT = ["литература", "история", "психология", "роман", "исследование", "анализ", "книга", "учебник", "статья", "наука", "культура", "искусство", "серебряный век"]

KIDS_FANTASY = [
    {"title": "Гарри Поттер и философский камень", "author": "Дж. К. Роулинг", "age": "6+"},
    {"title": "Хроники Нарнии", "author": "К. С. Льюис", "age": "6+"},
    {"title": "Перси Джексон и похититель молний", "author": "Рик Риордан", "age": "9+"},
    {"title": "Волшебник Земноморья", "author": "Урсула К. Ле Гуин", "age": "10+"},
    {"title": "Крылья Огня (Wings of Fire)", "author": "Туи Т. Сазерленд", "age": "9+"}
]

TEEN_FANTASY = [
    {"title": "Гарри Поттер и философский камень", "author": "Дж. К. Роулинг", "age": "12+"},
    {"title": "Шестерка воронов", "author": "Ли Бардуго", "age": "14+"},
    {"title": "Голодные игры", "author": "Сьюзен Коллинз", "age": "14+"},
    {"title": "Баллада о змеях и певчих птицах", "author": "Сьюзен Коллинз", "age": "14+"},
    {"title": "Эрагон", "author": "Кристофер Паолини", "age": "12+"},
    {"title": "Дом, в котором...", "author": "Мариам Петросян", "age": "16+"},
    {"title": "Академия ведьмочек (Little Witch Academia)", "author": "Ёсинори Ёнэмура (манга)", "age": "12+"},
    {"title": "Тетрадь дружбы Нацумэ", "author": "Юки Мидорикава (манга)", "age": "12+"},
    {"title": "Моя геройская академия (My Hero Academia)", "author": "Кохэй Хорикоси (манга)", "age": "13+"}
]

def has_hard_forbidden(text: str) -> bool:
    return any(word in text.lower() for word in HARD_FORBIDDEN)

def has_bad_language(text: str) -> bool:
    return bool(BAD_WORDS_REGEX.search(text))

def is_adult_query(query: str) -> bool:
    text_lower = query.lower()
    if any(safe_word in text_lower for safe_word in SAFE_CHILDREN_WORDS):
        return False
    has_marker = any(marker in text_lower for marker in ADULT_MARKERS)
    if not has_marker:
        return False
    has_context = any(ctx in text_lower for ctx in LITERARY_CONTEXT)
    if has_context:
        return False
    return True

def has_emoji_or_stickers(message: types.Message) -> bool:
    if message.sticker or message.animation:
        return True
    if message.text and re.search(r'[\U00010000-\U0010ffff]', message.text):
        return True
    return False

def get_main_keyboard():
    kb = [
        [KeyboardButton(text="✍️ Автор"), KeyboardButton(text="📖 Книга")],
        [KeyboardButton(text="🎭 Жанр"), KeyboardButton(text="🔬 Наука")],
        [KeyboardButton(text="🌐 Язык поиска")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_language_keyboard():
    kb = [
        [KeyboardButton(text="🇷🇺 Русский"), KeyboardButton(text="🇬🇧 English")],
        [KeyboardButton(text="🇪🇸 Español"), KeyboardButton(text="⬅️ Назад в меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_age_keyboard():
    kb = [
        [InlineKeyboardButton(text="✅ Да, мне есть 18. Я согласен", callback_data="age_yes")],
        [InlineKeyboardButton(text="❌ Нет, я младше", callback_data="age_no")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_age_category_keyboard():
    kb = [
        [InlineKeyboardButton(text="🧸 Мне от 6 до 12", callback_data="rec_kids")],
        [InlineKeyboardButton(text="🌱 Мне 13 и больше", callback_data="rec_teens")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_settings_keyboard(user_id):
    settings = user_settings.get(user_id, {'paintings': True, 'music': True})
    paint_status = "✅ Вкл" if settings['paintings'] else "❌ Выкл"
    music_status = "✅ Вкл" if settings['music'] else "❌ Выкл"
    kb = [
        [InlineKeyboardButton(text=f"🖼️ Картины: {paint_status}", callback_data="toggle_paint")],
        [InlineKeyboardButton(text=f"🎵 Музыка: {music_status}", callback_data="toggle_music")],
        [InlineKeyboardButton(text="🔇 Отключить всё (только книги)", callback_data="toggle_all")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_art_keyboard(book_key):
    kb = [
        [InlineKeyboardButton(text="🎨 Посмотреть картину", callback_data=f"art_paint_{book_key}")],
        [InlineKeyboardButton(text="🎵 Услышать музыку", callback_data=f"art_music_{book_key}")],
        [InlineKeyboardButton(text="🖼️ Совиная тайна", callback_data=f"art_fact_{book_key}")],
        [InlineKeyboardButton(text="🐻 В гостях у Медведя", callback_data=f"art_bear_{book_key}")],
        [InlineKeyboardButton(text="🔇 Только книга", callback_data=f"art_none_{book_key}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_format_keyboard(query):
    kb = [
        [InlineKeyboardButton(text="📥 Скачать EPUB", callback_data=f"fmt_epub_{query}")],
        [InlineKeyboardButton(text="📥 Скачать PDF", callback_data=f"fmt_pdf_{query}")],
        [InlineKeyboardButton(text="📖 Читать онлайн", callback_data=f"fmt_online_{query}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_fun_fact_keyboard():
    kb = [
        [InlineKeyboardButton(text="🔗 Посмотреть коллаж (PeopleTalk)", url="https://peopletalk.ru/article/iskusstvo-v-garri-pottere-7-realnyh-kartin-kotorye-ty-tochno-ne-zamechal-na-stenah-hogvartsa/")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

FIRST_WELCOMES = [
    "Здравствуй, добрый странник! 🦉🐻\n\nЯ — Сова, хранительница этой живой Книги. Мой верный друг Медведь уже затопил печь, а я расправила крылья.\n\nНад седыми горами плывут облака, в ущельях вьются туманы, а за морями-океанами дремлют тысячи историй. Скажи, какую дорогу выберем сегодня?",
    "Приветствую тебя у костра, странник! 🔥🦉\n\nЭто я, Сова. Пока Медведь подкидывает дров, я смотрю на звезды.\n\nКаждая книга — это вселенная, а каждая история — созвездие. Какую звезду мы зажжем сегодня?\n\nВыбери свою дорогу:"
]

RETURNING_WELCOMES = [
    "С возвращением, Странник! 🌌🦉\n\nПока тебя не было, я летала к самым далеким звездам. В нашей Книге космос спрятан между страниц.\n\nМожет, отыщем историю о далеких мирах?",
    "Звезды шепнули мне, что ты вернулся... ✨🐻\n\nМедведь разжег костер, и искры взлетели к небесам. Вселенная огромна, но в нашей Книге найдется место для любой тайны.\n\nС чего начнем?",
    "С возвращением, Странник! 🌊🦉\n\nСегодня ветер пахнет солью и приключениями. Я пролетала над океаном и видела прекрасных русалок.\n\nПоищем историю о морских глубинах?"
]

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_settings:
        user_settings[user_id] = {'paintings': True, 'music': True}
    if user_id not in user_language:
        user_language[user_id] = "🇷🇺 Русский"
    if user_id not in user_history:
        user_history[user_id] = 1
        welcome_text = random.choice(FIRST_WELCOMES)
    else:
        user_history[user_id] += 1
        welcome_text = random.choice(RETURNING_WELCOMES)
    welcome_text += "\n\n💡 Совет: /settings — настройки, /reset — начать заново."
    await message.answer(welcome_text, reply_markup=get_main_keyboard())

@dp.message(Command("reset"))
async def cmd_reset(message: types.Message):
    user_id = message.from_user.id
    if user_id in user_history: del user_history[user_id]
    user_settings[user_id] = {'paintings': True, 'music': True}
    user_language[user_id] = "🇷🇺 Русский"
    if user_id in user_art_notified: del user_art_notified[user_id]
    await message.answer("🦉🐻 Сова и Медведь перелистнули страницу...\n\nВсе настройки вернулись к волшебным стандартам.\n\nНапиши /start, чтобы начать заново.")

@dp.message(F.text == "🌐 Язык поиска")
async def change_language(message: types.Message):
    await message.answer("Выбери язык для поиска:", reply_markup=get_language_keyboard())

@dp.message(F.text.in_({"🇷🇺 Русский", "🇬🇧 English", "🇪🇸 Español"}))
async def set_language(message: types.Message):
    user_language[message.from_user.id] = message.text
    await message.answer(f"Отлично! Ищем на языке: {message.text}.", reply_markup=get_main_keyboard())

@dp.message(F.text == "⬅️ Назад в меню")
async def back_to_menu(message: types.Message):
    await message.answer("Возвращаемся в меню.", reply_markup=get_main_keyboard())

@dp.message(Command("settings"))
async def cmd_settings(message: types.Message):
    await message.answer("⚙️ Настройки путешествия:", reply_markup=get_settings_keyboard(message.from_user.id))

@dp.callback_query(F.data.startswith("toggle_"))
async def process_settings(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in user_settings: user_settings[user_id] = {'paintings': True, 'music': True}
    action = callback.data
    if action == "toggle_paint": user_settings[user_id]['paintings'] = not user_settings[user_id]['paintings']
    elif action == "toggle_music": user_settings[user_id]['music'] = not user_settings[user_id]['music']
    elif action == "toggle_all":
        state = not (user_settings[user_id]['paintings'] or user_settings[user_id]['music'])
        user_settings[user_id]['paintings'] = state; user_settings[user_id]['music'] = state
    await callback.message.edit_reply_markup(reply_markup=get_settings_keyboard(user_id))
    await callback.answer("Обновлено!")

@dp.message(F.text.in_({"✍️ Автор", "📖 Книга", "🎭 Жанр", "🔬 Наука"}))
async def ask_category(message: types.Message):
    prompts = {"✍️ Автор": "Назови имя автора:", "📖 Книга": "Название книги:", "🎭 Жанр": "Какой жанр?", "🔬 Наука": "Тема статьи?"}
    await message.answer(prompts[message.text])

@dp.callback_query(F.data.startswith("age_"))
async def process_age_choice(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if callback.data == "age_yes":
        user_age_group[user_id] = "adult"
        await callback.message.edit_text("🦉🐻 Благодарю за честность! Отправляюсь в этот темный лес...\n\nНапиши запрос еще раз.")
    else:
        user_age_group[user_id] = "restricted"
        await callback.message.edit_text("🦉🐻 Понимаю! В нашем Царстве есть книги для любого возраста.\n\nСколько тебе лет?", reply_markup=get_age_category_keyboard())
    await callback.answer()

@dp.callback_query(F.data.startswith("rec_"))
async def process_recommendation(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if callback.data == "rec_kids":
        user_age_group[user_id] = "kids"
        title, books = "🧸 Увлекательнейшее фэнтези:", KIDS_FANTASY
    else:
        user_age_group[user_id] = "teens"
        title, books = "🌱 Подростковое фэнтези:", TEEN_FANTASY
    text = title + "\n\n"
    for book in books: text += f"📚 {book['title']} — {book['author']} ({book['age']})\n"
    text += "\n✨ Напиши название, и я найду её!"
    await callback.message.edit_text(text)
    await callback.answer()

@dp.callback_query(F.data.startswith("art_"))
async def process_art_choice(callback: types.CallbackQuery):
    data = callback.data.split("_"); action, book_key = data[1], data[2]
    arts = ART_COMPANIONS.get(book_key)
    if not arts: await callback.answer("Ой, Сова потеряла страницу..."); return
    if action == "none":
        await callback.message.edit_text("🦉🐻 Только книга — так только книга!"); await callback.answer(); return
    if action == "paint":
        try:
            photo = FSInputFile(arts['painting_file'])
            await callback.message.answer_photo(photo=photo, caption=f"🎨 {arts['painting_name']}\n{arts['painting_author']}, {arts['painting_year']} год.\n\n«Странник, эта картина словно шепчет о твоей книге...»")
        except Exception: await callback.message.answer(f"🦉 Сова шепчет: «Эта история напоминает мне о картине {arts['painting_name']}...»")
    elif action == "music":
        await callback.message.answer(f"🎵 Сова напевает:\n\n«А если хочешь добавить волшебства, включи {arts['music']}. Пусть музыка станет мостом...»")
    elif action == "fact":
        await callback.message.answer(arts['fun_fact'], reply_markup=get_fun_fact_keyboard())
        user_id = callback.from_user.id
        if user_settings.get(user_id, {}).get('paintings', True) and 'secret_paintings' in arts:
            for secret in arts['secret_paintings']:
                try:
                    photo = FSInputFile(secret['file'])
                    await callback.message.answer_photo(photo=photo, caption=f"🖼️ {secret['name']}\n{secret['author']}, {secret['year']} год.\n\n«В фильме этот портрет стилизован под Хогвартс...»")
                except Exception: pass
    elif action == "bear":
        await callback.message.answer(arts['bear_advice'])
    await callback.answer()

@dp.callback_query(F.data.startswith("fmt_"))
async def process_format_choice(callback: types.CallbackQuery):
    parts = callback.data.split("_", 2)
    if len(parts) < 3: await callback.answer("Ой, Сова не разобрала формат..."); return
    fmt, book_title = parts[1], parts[2]
    new_query = f"{book_title} epub скачать" if fmt == "epub" else f"{book_title} pdf скачать" if fmt == "pdf" else f"{book_title} читать онлайн"
    await callback.message.edit_text(f"🦉 Сова уже летит искать книгу в формате {fmt.upper()}...")
    await handle_search(types.Message(message_id=callback.message.message_id, date=callback.message.date, chat=callback.message.chat, from_user=callback.from_user, text=new_query))
    await callback.answer()

@dp.message()
async def handle_search(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_settings: user_settings[user_id] = {'paintings': True, 'music': True}
    if user_id not in user_language: user_language[user_id] = "🇷🇺 Русский"
    if has_emoji_or_stickers(message):
        await message.answer("🦉🐻 Ой, странник! В нашей Книге живут только буквы и слова, но зато какие! Ведь самые прекрасные иллюстрации — будь то горные вершины, шум леса или тончайшие движения человеческой души — создает наше собственное воображение. ✨\n\nНапиши свой запрос словами, и я полечу искать!")
        return
    query = message.text.strip().lower()
    if has_bad_language(query):
        await message.answer("🦉🐻 Эх, странник... Мы с Медведем ценим добрые слова. Такие речи не для нашей Книги. Давай обойдем эту топь стороной?")
        return
    if has_hard_forbidden(query):
        await message.answer("🦉🐻 Ох, странник, чует мое сердце беду... Перед тобой топь непролазная и тропы запретные. Не пойдем туда! Давай обойдем её.")
        return
    if is_adult_query(query):
        if user_age_group.get(user_id) in ["kids", "teens", "restricted"]:
            await message.answer("🦉🐻 Ох, странник! В нашей Книге Царства для тебя есть столько удивительных и добрых историй! Давай не будем заходить в этот темный лес, а поищем что-нибудь светлое?")
            return
        else:
            await message.answer("🌲 Тёмный лес на горизонте...\n\n⚠️ Предупреждение!\n\nПродолжая поиск, вы подтверждаете, что вам есть 18 лет. Вы соглашаетесь, что за дальнейшие действия пользователь сам несет ответственность.\n\nСова и Медведь не несут ответа за содержимое найденных страниц.\n\nГотов ли ты войти, странник?", reply_markup=get_age_keyboard())
            return
    if "стих" in query or "поэз" in query:
        await message.answer(random.choice(["🌿 «Мороз и солнце; день чудесный!...» — А. С. Пушкин (1829)\n\nСтранник, стихи — это музыка души. Хочешь, я найду сборник?", "🌙 «Выхожу один я на дорогу...» — М. Ю. Лермонтов (1841)\n\nВ поэзии столько тишины и света. Давай отыщем книгу!"]))
        return
    corrected_query = correct_typos(query)
    if corrected_query.lower() != query.lower():
        await message.answer(f"🦉 Шелестят страницы... Кажется, ветер переставил буквы! Я поняла тебя как: {corrected_query}.")
        query_to_search = corrected_query
    else: query_to_search = query
    lang = user_language.get(user_id, "🇷🇺 Русский")
    lang_suffix = " english" if lang == "🇬🇧 English" else " español" if lang == "🇪🇸 Español" else ""
    is_article = "наука" in query or "статья" in query
    search_query = f"{query_to_search}{lang_suffix} научная статья PDF" if is_article else f"{query_to_search}{lang_suffix} книга EPUB OR PDF скачать"
    status_msg = await message.answer(f"📖 Шелестят страницы...\n\n🦉 Сова взмыла к вершинам в поисках «{query_to_search}» (Язык: {lang})...\n🐻 Медведь улыбается: удача любит отважных!")
    try:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, perform_search, search_query, is_article)
        if not results:
            await status_msg.edit_text("🦉🐻 Странник, я облетела горы и ущелья, но этой истории там пока нет... Попробуй назвать иначе!")
            return
        await status_msg.delete()
        await message.answer("✨ Страницы зашелестели, и перед нами открылись чудесные находки:")
        unique_titles = set(); unique_results = []
        for res in results:
            title, url, snippet = res.get("title", "Без названия"), res.get("href", ""), res.get("body", "Нет описания.")
            if not is_safe_domain(url) or has_bad_language(title + snippet) or has_hard_forbidden(title + snippet): continue
            title_key = title[:30].lower().strip()
            if title_key in unique_titles: continue
            unique_titles.add(title_key); unique_results.append((title, url, snippet[:150] + "..."))
        if not unique_results:
            await message.answer("🦉🐻 Странник, я нашла ссылки, но все они ведут на закрытые или небезопасные площадки. Наше Царство летает только по светлым тропам! Давай попробуем иначе?")
            return
        for title, url, snippet in unique_results:
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔗 Открыть / Скачать", url=url)]])
            await message.answer(f"📜 {title}\n\n{snippet}", reply_markup=kb, disable_web_page_preview=True)
        if not is_article and query_to_search not in AUTHORS_AND_TITLES:
            await message.answer("🦉🐻 Сова и Медведь переглянулись...\n\n«Странник, в каком формате тебе удобнее читать?»", reply_markup=get_format_keyboard(query_to_search))
        for key, arts in ART_COMPANIONS.items():
            if key in query_to_search:
                user_current_book_key[user_id] = key
                if user_settings.get(user_id, {}).get('paintings', True) or user_settings.get(user_id, {}).get('music', True):
                    await message.answer("🦉🐻 Сова и Медведь переглянулись...\n\n«Странник, у нас есть кое-что интересное об этой книге. Что бы ты хотел узнать?»", reply_markup=get_art_keyboard(key))
                break
    except Exception as e:
        logging.error(f"Ошибка поиска: {e}")
        await status_msg.edit_text("⚠️ Ветер с гор сорвал страницы, и Сова запуталась в облаках. Но не беда! Попробуй снова.")

def perform_search(search_query, is_article=False):
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(search_query, max_results=5))
            if results: return results
    except Exception as e: logging.warning(f"ddgs не сработал: {e}. Пробуем запасной вариант.")
    if is_article:
        try:
            clean_query = search_query.replace("научная статья PDF", "").strip()
            response = httpx.get("https://api.openalex.org/works", params={"search": clean_query, "per_page": 5}, timeout=10.0)
            if response.status_code == 200:
                return [{"title": item.get("title", "Без названия"), "href": item.get("doi") or item.get("id", ""), "body": "Научная статья. Откройте ссылку."} for item in response.json().get("results", [])]
        except Exception as e: logging.error(f"OpenAlex не сработал: {e}")
    else:
        try:
            clean_query = search_query.replace("книга EPUB OR PDF скачать", "").strip()
            response = httpx.get(f"https://www.googleapis.com/books/v1/volumes?q={clean_query}&maxResults=5", timeout=10.0)
            if response.status_code == 200:
                results = []
                for item in response.json().get("items", []):
                    vol = item.get("volumeInfo", {}); link = vol.get("previewLink", "")
                    if link: results.append({"title": f"{vol.get('title', 'Без названия')} ({', '.join(vol.get('authors', ['Автор неизвестен']))})", "href": link, "body": "Книга найдена в Google Books."})
                return results
        except Exception as e: logging.error(f"Google Books не сработал: {e}")
    return []

async def main():
    print("🦉🐻 Сова и Медведь раскрыли Книгу Царства...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: print("Книга закрылась до следующего рассвета. До встречи!")
