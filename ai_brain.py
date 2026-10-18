import os
import logging
import httpx

async def smart_search(query: str, search_type: str) -> str:
    GROQ_KEY = os.getenv("GROQ_API_KEY")
    if not GROQ_KEY:
        logging.warning("Ключ Groq не найден. Работаем без ИИ.")
        return query

    model = "llama-3.3-70b-versatile"
    system_prompt = "Ты — библиотекарь. Твоя задача — превратить запрос пользователя в точный поисковый запрос для DuckDuckGo. Если пользователь ищет книгу, добавь 'книга скачать EPUB PDF'. Если ищет жанр, добавь 'лучшие книги в жанре'. Отвечай ТОЛЬКО поисковым запросом."
    if search_type == "article":
        system_prompt = "Ты — научный ассистент. Переформулируй запрос для поиска научных статей. Отвечай только запросом."

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": f"Запрос: {query}"}], "max_tokens": 50, "temperature": 0.1},
                timeout=15.0
            )
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logging.error(f"Ошибка Groq: {e}")
    return query
