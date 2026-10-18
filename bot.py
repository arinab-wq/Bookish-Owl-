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
    raise ValueError("Токен не найден! Добавьте BOOKISH_OWL_TOKEN в .env или GitHub Secrets.")

bot = Bot(token=TOKEN)
dp = Dispatcher()

user_history = {}
user_settings = {}
user_art_notified = {}
user_age_group = {}
user_current_book_key = {}
user_language = {}

# --- БЕЛЫЙ СПИСОК ДОМЕНОВ (Только открытые и безопасные) ---
SAFE_DOMAINS = [
    "litres.ru", "flibusta.is", "fictionbook.ru", "libking.ru", 
    "royallib.com", "litmir.me", "avidreaders.ru", "bookz.ru",
    "wikipedia.org", "openlibrary.org", "google.com", "books.google.com",
    "archive.org", "gutenberg.org", "labirint.ru", "ozon.ru", "peopletalk.ru"
]

def is_safe_domain(url: str) -> bool:
    try:
        domain = urlparse(url).netloc.lower()
        # Если домен содержит запрещенные слова или не входит в список - отсекаем
        for safe in SAFE_DOMAINS:
            if safe in domain:
                return True
        # Если это Google, Литрес или Википедия - пропускаем, остальные проверяем строже
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
    },
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
    
    welcome_text += "\n\n💡 Совет: ты можешь настроить картины и музыку командой /settings, сменить язык кнопкой «🌐 Язык поиска», а также начать заново командой /reset."
    await message.answer(welcome_text, reply_markup=get_main_keyboard())

@dp.message(Command("reset"))
async def cmd_reset(message: types.Message):
    user_id = message.from_user.id
    if user_id in user_history:
        del user_history[user_id]
    user_settings[user_id] = {'paintings': True, 'music': True}
    user_language[user_id] = "🇷🇺 Русский"
    if user_id in user_art_notified:
        del user_art_notified[user_id]
        
    await message.answer(
        "🦉🐻 Сова и Медведь перелистнули страницу...\n\n"
        "Мы начали нашу Книгу с чистого листа! Все настройки и язык вернулись к волшебным стандартам.\n\n"
        "Напиши /start, чтобы начать путешествие заново."
    )

@dp.message(F.text == "🌐 Язык поиска")
async def change_language(message: types.Message):
    await message.answer("Выбери язык, на котором хочешь искать книги:", reply_markup=get_language_keyboard())

@dp.message(F.text.in_({"🇷🇺 Русский", "🇬🇧 English", "🇪🇸 Español"}))
async def set_language(message: types.Message):
    user_id = message.from_user.id
    user_language[user_id] = message.text
    await message.answer(f"Отлично! Теперь я буду искать книги на языке: {message.text}.", reply_markup=get_main_keyboard())

@dp.message(F.text == "⬅️ Назад в меню")
async def back_to_menu(message: types.Message):
    await message.answer("Возвращаемся в главное меню, странник.", reply_markup=get_main_keyboard())

@dp.message(Command("settings"))
async def cmd_settings(message: types.Message):
    text = (
        "⚙️ Настройки твоего путешествия\n\n"
        "Выбери, что бы ты хотел видеть в дополнение к книгам.\n"
        "Мы не навязываем, решать тебе:"
    )
    await message.answer(text, reply_markup=get_settings_keyboard(message.from_user.id))

@dp.callback_query(F.data.startswith("toggle_"))
async def process_settings(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in user_settings:
        user_settings[user_id] = {'paintings': True, 'music': True}
        
    action = callback.data
    if action == "toggle_paint":
        user_settings[user_id]['paintings'] = not user_settings[user_id]['paintings']
    elif action == "toggle_music":
        user_settings[user_id]['music'] = not user_settings[user_id]['music']
    elif action == "toggle_all":
        state = not (user_settings[user_id]['paintings'] or user_settings[user_id]['music'])
        user_settings[user_id]['paintings'] = state
        user_settings[user_id]['music'] = state

    await callback.message.edit_reply_markup(reply_markup=get_settings_keyboard(user_id))
    await callback.answer("Настройки обновлены!")

@dp.message(F.text.in_({"✍️ Автор", "📖 Книга", "🎭 Жанр", "🔬 Наука"}))
async def ask_category(message: types.Message):
    prompts = {
        "✍️ Автор": "Назови имя автора, и я полечу искать его творения по свету.",
        "📖 Книга": "Скажи название книги, и мы отыщем её на страницах открытого мира.",
        "🎭 Жанр": "Какой жанр тебе по душе? (например: фэнтези, детектив, классика)",
        "🔬 Наука": "О какой научной теме или статье ты хочешь узнать?"
    }
    await message.answer(prompts[message.text])

@dp.callback_query(F.data.startswith("age_"))
async def process_age_choice(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if callback.data == "age_yes":
        user_age_group[user_id] = "adult"
        await callback.message.edit_text(
            "🦉🐻 Благодарю за честность и ответственность, странник! Отправляюсь в этот темный лес...\n\n"
            "Напиши свой запрос еще раз, и мы отправимся в путь."
        )
    else:
        user_age_group[user_id] = "restricted"
        await callback.message.edit_text(
            "🦉🐻 Понимаю тебя, странник! В нашем Царстве есть книги для любого возраста.\n\n"
            "Давай обойдем этот темный лес стороной и выберем что-нибудь увлекательное и доброе!\n\n"
            "Сколько тебе лет, если не секрет?",
            reply_markup=get_age_category_keyboard()
        )
    await callback.answer()

@dp.callback_query(F.data.startswith("rec_"))
async def process_recommendation(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if callback.data == "rec_kids":
        user_age_group[user_id] = "kids"
        title = "🧸 Увлекательнейшее фэнтези для тебя:\n\n"
        books = KIDS_FANTASY
    else:
        user_age_group[user_id] = "teens"
        title = "🌱 Увлекательное подростковое фэнтези:\n\n"
        books = TEEN_FANTASY

    text = title
    for book in books:
        text += f"📚 {book['title']} — {book['author']} ({book['age']})\n"
    
    text += "\n✨ Напиши название любой из этих книг, и я отправлюсь на поиски её страниц!"
    await callback.message.edit_text(text)
    await callback.answer()

@dp.callback_query(F.data.startswith("art_"))
async def process_art_choice(callback: types.CallbackQuery):
    data = callback.data.split("_")
    action = data[1]
    book_key = data[2]
    
    arts = ART_COMPANIONS.get(book_key)
    if not arts:
        await callback.answer("Ой, Сова потеряла эту страницу...")
        return

    if action == "none":
        await callback.message.edit_text("🦉🐻 Сова и Медведь понимающе кивнули. Только книга — так только книга!")
        await callback.answer()
        return

    if action == "paint":
        try:
            photo = FSInputFile(arts['painting_file'])
            caption = (
                f"🎨 {arts['painting_name']}\n"
                f"{arts['painting_author']}, {arts['painting_year']} год.\n\n"
                f"«Странник, эта картина словно шепчет о твоей книге. Взгляни, как мастер поймал свет и тень...»"
            )
            await callback.message.answer_photo(photo=photo, caption=caption)
        except Exception as e:
            await callback.message.answer(f"🦉 Сова тихо шепчет: «Странник, эта история напоминает мне о картине {arts['painting_name']} ({arts['painting_author']}, {arts['painting_year']})...»")

    elif action == "music":
        await callback.message.answer(
            f"🎵 Сова напевает:\n\n"
            f"«А если хочешь добавить волшебства, включи {arts['music']}. Пусть музыка станет мостом между тобой и этой историей»."
        )
        
    elif action == "fact":
        await callback.message.answer(arts['fun_fact'], reply_markup=get_fun_fact_keyboard())
        
        user_id = callback.from_user.id
        if user_settings.get(user_id, {}).get('paintings', True) and 'secret_paintings' in arts:
            for secret in arts['secret_paintings']:
                try:
                    photo = FSInputFile(secret['file'])
                    caption = (
                        f"🖼️ {secret['name']}\n"
                        f"{secret['author']}, {secret['year']} год.\n\n"
                        f"«В фильме этот портрет стилизован под волшебный мир Хогвартса: человек на изображении в мантии и колпаке волшебника, поэтому его могли не заметить. Но в реальности это великий шедевр...»"
                    )
                    await callback.message.answer_photo(photo=photo, caption=caption)
                except Exception as e:
                    await callback.message.answer(f"🦉 Шепот Совы: «А еще там была картина {secret['name']} ({secret['author']}, {secret['year']}), стилизованная под Хогвартс...»")
                    
    elif action == "bear":
        await callback.message.answer(arts['bear_advice'])

    await callback.answer()

@dp.callback_query(F.data.startswith("fmt_"))
async def process_format_choice(callback: types.CallbackQuery):
    parts = callback.data.split("_", 2) 
    if len(parts) < 3:
        await callback.answer("Ой, Сова не разобрала формат...")
        return

    fmt = parts[1]
    book_title = parts[2]

    if fmt == "epub":
        new_query = f"{book_title} epub скачать"
    elif fmt == "pdf":
        new_query = f"{book_title} pdf скачать"
    else:
        new_query = f"{book_title} читать онлайн"

    await callback.message.edit_text(f"🦉 Сова уже летит искать книгу в формате {fmt.upper()}...")
    
    fake_message = types.Message(
        message_id=callback.message.message_id,
        date=callback.message.date,
        chat=callback.message.chat,
        from_user=callback.from_user,
        text=new_query
    )
    
    await handle_search(fake_message)
    await callback.answer()

@dp.message()
async def handle_search(message: types.Message):
    user_id = message.from_user.id
    
    if user_id not in user_settings:
        user_settings[user_id] = {'paintings': True, 'music': True}
    if user_id not in user_language:
        user_language[user_id] = "🇷🇺 Русский"

    if has_emoji_or_stickers(message):
        await message.answer(
            "🦉🐻 Ой, странник!\n\n"
            "В нашей Книге Царства живут только буквы и слова, но зато какие! Ведь самые прекрасные иллюстрации — будь то горные вершины, шум леса, космические дали или тончайшие движения человеческой души — создает наше собственное воображение. ✨\n\n"
            "Напиши свой запрос словами, и я полечу искать, чтобы твое воображение нарисовало целый мир!"
        )
        return

    query = message.text.strip().lower()

    if has_bad_language(query):
        await message.answer(
            "🦉🐻 Эх, странник...\n\n"
            "Мы с Медведем ценим добрые слова. Такие речи не для нашей Книги.\n\n"
            "Давай обойдем эту топь стороной и поищем что-нибудь светлое?"
        )
        return

    if has_hard_forbidden(query):
        await message.answer(
            "🦉🐻 Ох, странник, чует мое сердце беду...\n\n"
            "Перед тобой топь непролазная и тропы запретные. Не пойдем туда!\n\n"
            "Давай обойдем её и начнем путешествие снова."
        )
        return

    if is_adult_query(query):
        if user_age_group.get(user_id) in ["kids", "teens", "restricted"]:
            await message.answer(
                "🦉🐻 Ох, странник! В нашей Книге Царства для тебя есть столько удивительных и добрых историй!\n\n"
                "Давай не будем заходить в этот темный лес, а поищем что-нибудь светлое и волшебное. Что скажешь?"
            )
            return
        else:
            warning_text = (
                "🌲 Тёмный лес на горизонте...\n\n"
                "⚠️ Предупреждение!\n\n"
                "Продолжая поиск данной книги, вы подтверждаете, что вам исполнилось 18 лет. Вы соглашаетесь с тем, что за дальнейшие действия пользователь сам несет ответственность.\n\n"
                "Сова и Медведь не несут ответа за содержимое найденных страниц.\n\n"
                "Готов ли ты войти в этот лес, странник?"
            )
            await message.answer(warning_text, reply_markup=get_age_keyboard())
            return

    if "стих" in query or "поэз" in query:
        poem = random.choice([
            "🌿 «Мороз и солнце; день чудесный! / Еще ты дремлешь, друг прелестный...» — А. С. Пушкин (1829)\n\nСтранник, стихи — это музыка души. Хочешь, я найду для тебя сборник стихов?",
            "🌙 «Выхожу один я на дорогу; / Сквозь туман кремнистый путь блестит...» — М. Ю. Лермонтов (1841)\n\nВ поэзии столько тишины и света. Давай отыщем книгу, которая подарит тебе вдохновение."
        ])
        await message.answer(poem)
        return

    corrected_query = correct_typos(query)
    if corrected_query.lower() != query.lower():
        await message.answer(f"🦉 Шелестят страницы... Кажется, ветер переставил буквы! Я поняла тебя как: {corrected_query}. Отправляюсь на поиски...")
        query_to_search = corrected_query
    else:
        query_to_search = query

    lang = user_language.get(user_id, "🇷🇺 Русский")
    lang_suffix = ""
    if lang == "🇬🇧 English":
        lang_suffix = " english"
    elif lang == "🇪🇸 Español":
        lang_suffix = " español"

    is_article = "наука" in query or "статья" in query
    if is_article:
        search_query = f"{query_to_search}{lang_suffix} научная статья PDF"
    else:
        search_query = f"{query_to_search}{lang_suffix} книга EPUB OR PDF скачать"

    status_msg = await message.answer(
        f"📖 Шелестят страницы...\n\n"
        f"🦉 Сова взмыла к заснеженным вершинам в поисках «{query_to_search}» (Язык: {lang})...\n"
        f"🐻 Медведь улыбается: удача любит отважных!"
    )

    try:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, perform_search, search_query, is_article)

        if not results:
            await status_msg.edit_text(
                "🦉🐻 Странник, я облетела горы и ущелья, но этой истории там пока нет...\n\n"
                "Но не печалься! Попробуй назвать иначе — и удача нам улыбнется! ✨"
            )
            return

        await status_msg.delete()
        await message.answer("✨ Страницы зашелестели, и перед нами открылись чудесные находки:")

        unique_titles = set()
        unique_results = []
        
        for res in results:
            title = res.get("title", "Без названия")
            url = res.get("href", "")
            snippet = res.get("body", "Нет описания.")

            # БЕЗОПАСНЫЙ ИНТЕРНЕТ: проверяем домен
            if not is_safe_domain(url):
                continue

            if has_bad_language(title + snippet) or has_hard_forbidden(title + snippet):
                continue

            title_key = title[:30].lower().strip()
            
            if title_key in unique_titles:
                continue
            
            unique_titles.add(title_key)
            
            if len(snippet) > 150:
                snippet = snippet[:147] + "..."

            unique_results.append((title, url, snippet))

        if not unique_results:
            await message.answer(
                "🦉🐻 Странник, я нашла несколько ссылок, но все они ведут на закрытые или небезопасные площадки. "
                "Наше Царство летает только по светлым и открытым тропам!\n\n"
                "Давай попробуем назвать книгу иначе?"
            )
            return

        for title, url, snippet in unique_results:
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔗 Открыть / Скачать", url=url)]])
            await message.answer(f"📜 {title}\n\n{snippet}", reply_markup=kb, disable_web_page_preview=True)

        if not is_article and query_to_search not in AUTHORS_AND_TITLES:
            await message.answer(
                "🦉🐻 Сова и Медведь переглянулись...\n\n"
                "«Странник, у нас есть кое-что интересное об этой книге. В каком формате тебе удобнее читать?»",
                reply_markup=get_format_keyboard(query_to_search)
            )

        for key, arts in ART_COMPANIONS.items():
            if key in query_to_search:
                user_current_book_key[user_id] = key
                
                if user_settings.get(user_id, {}).get('paintings', True) or user_settings.get(user_id, {}).get('music', True):
                    await message.answer(
                        "🦉🐻 Сова и Медведь переглянулись...\n\n"
                        "«Странник, у нас есть кое-что интересное об этой книге. Что бы ты хотел узнать?»",
                        reply_markup=get_art_keyboard(key)
                    )
                break 

    except Exception as e:
        logging.error(f"Ошибка поиска: {e}")
        await status_msg.edit_text(
            "⚠️ Ветер с гор сорвал страницы, и Сова запуталась в облаках.\n\n"
            "Но не беда! Мы поправим очки и попробуем снова. Подожди чуток и переверни страницу еще раз. 🌟"
        )

def perform_search(search_query, is_article=False):
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(search_query, max_results=5))
            if results:
                return results
    except Exception as e:
        logging.warning(f"ddgs не сработал: {e}. Пробуем запасной вариант.")
    
    if is_article:
        try:
            clean_query = search_query.replace("научная статья PDF", "").strip()
            url = "https://api.openalex.org/works"
            params = {"search": clean_query, "per_page": 5}
            response = httpx.get(url, params=params, timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                results = []
                for item in data.get("results", []):
                    results.append({
                        "title": item.get("title", "Без названия"),
                        "href": item.get("doi") or item.get("id", ""),
                        "body": "Научная статья. Откройте ссылку для подробностей."
                    })
                return results
        except Exception as e:
            logging.error(f"OpenAlex тоже не сработал: {e}")
            
    else:
        try:
            clean_query = search_query.replace("книга EPUB OR PDF скачать", "").strip()
            url = f"https://www.googleapis.com/books/v1/volumes?q={clean_query}&maxResults=5"
            
            response = httpx.get(url, timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                results = []
                for item in data.get("items", []):
                    volume_info = item.get("volumeInfo", {})
                    title = volume_info.get("title", "Без названия")
                    authors = ", ".join(volume_info.get("authors", ["Автор неизвестен"]))
                    preview_link = volume_info.get("previewLink", "")
                    
                    if preview_link:
                        results.append({
                            "title": f"{title} ({authors})",
                            "href": preview_link,
                            "body": "Книга найдена в Google Books. Вы можете прочитать фрагмент или найти её в магазине по ссылке."
                        })
                return results
        except Exception as e:
            logging.error(f"Google Books тоже не сработал: {e}")
    
    return []

async def main():
    print("🦉🐻 Сова и Медведь раскрыли Книгу Царства...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Книга закрылась до следующего рассвета. До встречи!")