import os
import logging
import httpx

async def smart_search(query: str, search_type: str) -> str:
    """
    Отправляет запрос пользователя в нейросеть Groq, 
    чтобы она переформулировала его для точного поиска.
    """
    GROQ_KEY = os.getenv("GROQ_API_KEY")
    if not GROQ_KEY:
        logging.warning("Ключ Groq не найден. Работаем без ИИ.")
        return query

    model = "llama-3.3-70b-versatile"
    
    system_prompt = (
        "Ты — библиотекарь. Твоя задача — превратить запрос пользователя в точный поисковый запрос для DuckDuckGo. "
        "Если пользователь ищет книгу, добавь 'книга скачать EPUB PDF'. "
        "Если ищет жанр, добавь 'лучшие книги в жанре'. "
        "Если ищет научную статью, добавь 'научная статья PDF'. "
        "Отвечай ТОЛЬКО поисковым запросом, без лишних слов."
    )
    
    if search_type == "article":
        system_prompt = "Ты — научный ассистент. Переформулируй запрос для поиска научных статей. Отвечай только запросом."

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Запрос: {query}"}
                    ],
                    "max_tokens": 50,
                    "temperature": 0.1
                },
                timeout=15.0
            )
            if response.status_code == 200:
                data = response.json()
                new_query = data["choices"][0]["message"]["content"].strip()
                logging.info(f"Groq переформулировал: '{query}' -> '{new_query}'")
                return new_query
            else:
                logging.error(f"Ошибка Groq API: {response.status_code} - {response.text}")
    except Exception as e:
        logging.error(f"Ошибка при запросе к Groq: {e}")
        
    return query # Если нейросеть упала, используем оригинал
