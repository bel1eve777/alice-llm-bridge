# Alice LLM Bridge — Бесплатная интеграция Яндекс Алисы с LLM

Готовый к деплою сервер для подключения любой LLM (OpenRouter, GigaChat, Groq, локальные) к Яндекс Алисе через приватный навык.

## ✨ Возможности

- 🎯 **Умная маршрутизация**: системные команды (умный дом, таймеры, покупки) остаются у Алисы, вопросы уходят в LLM
- 🆓 **Полностью бесплатно**: Render.com + OpenRouter (бесплатные модели)
- 🔧 **Простая настройка**: 3 переменные окружения
- 🐳 **Docker-ready**: деплой за 1 клик
- 🇷🇺 **Русский язык из коробки**

## 🚀 Быстрый старт (5 минут)

### 1. Получите ключ OpenRouter
- Зарегистрируйтесь на [openrouter.ai](https://openrouter.ai)
- Создайте API Key
- Скопируйте ключ (начинается на `sk-or-v1-...`)

### 2. Форкните и задеплойте на Render
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/ВАШ_ЮЗЕРНЕЙМ/alice-llm-bridge)

Или вручную:
1. Fork этот репозиторий
2. В Render: **New → Web Service** → Подключите ваш форк
3. Environment Variables:
   ```
   LLM_API_URL = https://openrouter.ai/api/v1/chat/completions
   LLM_API_KEY = ваш_ключ_openrouter
   LLM_MODEL = meta-llama/llama-3.1-8b-instruct:free
   ```
4. Deploy → получите `https://your-app.onrender.com`

### 3. Настройте Яндекс Диалоги
1. [dialogs.yandex.ru](https://dialogs.yandex.ru) → **Создать навык** → **Чат-бот**
2. Backend: **HTTPS Webhook**
3. URL: `https://your-app.onrender.com/alice/webhook`
4. Добавьте интенты (см. ниже)
5. Опубликуйте → «Приватный навык» → добавьте себя в тестеры

### 4. Интенты для навыка (скопируйте в консоль Диалогов)

| Имя интента | Примеры фраз |
|-------------|--------------|
| `general_question` | расскажи про, как сделать, что такое, объясни, почему, зачем, сколько, кто такой |
| `creative_task` | напиши стихотворение, придумай историю, сгенерируй идеи, напиши текст, придумай название |
| `code_help` | напиши код, исправь ошибку, объясни функцию, как написать, код на python, код на javascript |

**НЕ добавляйте** интенты для: умный дом, таймеры, будильники, список покупок, музыка, погода, новости — Алиса обработает их сама.

## ⚙️ Конфигурация

| Переменная | Обязательна | По умолчанию | Описание |
|------------|-------------|--------------|----------|
| `LLM_API_URL` | ✅ | — | Эндпоинт LLM API (OpenAI-совместимый) |
| `LLM_API_KEY` | ✅ | — | API ключ |
| `LLM_MODEL` | ✅ | — | Название модели |
| `SYSTEM_PROMPT` | ❌ | встроенный | Системный промпт для LLM |
| `MAX_TOKENS` | ❌ | `300` | Макс. токенов в ответе |
| `TEMPERATURE` | ❌ | `0.7` | Креативность (0-1) |
| `REQUEST_TIMEOUT` | ❌ | `30` | Таймаут запроса к LLM (сек) |

### Популярные бесплатные модели (OpenRouter)

```bash
# Быстрые и качественные
meta-llama/llama-3.1-8b-instruct:free
google/gemma-2-9b-it:free
microsoft/phi-3-mini-128k-instruct:free
qwen/qwen-2.5-72b-instruct:free
nvidia/nemotron-3-ultra:free

# Для кода
qwen/qwen-2.5-coder-32b-instruct:free
```

### Другие провайдеры (замените URL и ключ)

| Провайдер | LLM_API_URL | Модели |
|-----------|-------------|--------|
| **Groq** | `https://api.groq.com/openai/v1/chat/completions` | `llama-3.1-70b-versatile`, `llama-3.1-8b-instant` |
| **Together AI** | `https://api.together.xyz/v1/chat/completions` | `meta-llama/Llama-3.1-70B-Instruct-Turbo` |
| **GigaChat** | `https://gigachat.devices.sberbank.ru/api/v1/chat/completions` | `GigaChat-Pro` (требует OAuth токен) |

## 🏠 Локальная разработка

```bash
# Клонируйте
git clone https://github.com/ВАШ_ЮЗЕРНЕЙМ/alice-llm-bridge.git
cd alice-llm-bridge

# Создайте .env
cp .env.example .env
# Отредактируйте .env

# Запустите
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Для тестов с Алисой (в другом терминале)
ngrok http 8000
# Используйте https://xxxx.ngrok-free.app/alice/webhook
```

## 📁 Структура проекта

```
alice-llm-bridge/
├── main.py              # FastAPI приложение
├── requirements.txt     # Зависимости Python
├── Dockerfile           # Для Render/Fly.io/Railway
├── .env.example         # Пример конфигурации
├── .dockerignore        # Игнорируемые файлы
├── .gitignore
└── README.md
```

## 🔧 Как работает маршрутизация

```python
def should_use_llm(request) -> bool:
    intents = request.nlu.intents
    
    # 1. Наши интенты → точно в LLM
    if any(intent in intents for intent in ["general_question", "creative_task", "code_help"]):
        return True
    
    # 2. Нет интентов (Алиса не поняла) → в LLM
    if not intents:
        return True
    
    # 3. Системные интенты Алисы → НЕ трогаем
    system_intents = {"alarm_clock", "timer", "shopping_list", "music", 
                      "smart_home", "weather", "news", "recipes"}
    if any(intent in intents for intent in system_intents):
        return False
    
    # 4. По умолчанию → в LLM
    return True
```

## 📝 Логи и отладка

```bash
# Логи Render: Dashboard → Logs
# Логи локально: терминал с uvicorn

# Тест webhook вручную:
curl -X POST https://your-app.onrender.com/alice/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "meta": {"locale": "ru-RU", "timezone": "UTC", "client_id": "test"},
    "request": {"command": "что такое квантовая физика", "original_utterance": "что такое квантовая физика", "type": "SimpleUtterance", "nlu": {"tokens": ["что", "такое", "квантовая", "физика"], "entities": [], "intents": {"general_question": {}}}},
    "session": {"session_id": "test", "message_id": 1, "user_id": "test", "new": false},
    "version": "1.0"
  }'
```

## ❓ Частые проблемы

| Проблема | Решение |
|----------|---------|
| «Навык не отвечает» | Проверьте логи Render. Ответ должен быть < 1.5 сек. Увеличьте таймаут или уменьшите `MAX_TOKENS` |
| Системные команды уходят в LLM | Добавьте интент в `system_intents` в `main.py` |
| Ошибка 403/401 | Проверьте `LLM_API_KEY` и `LLM_API_URL` |
| Render спит | На бесплатном плане спит через 15 мин. Первый запрос после сна ~30 сек. Или перейдите на Railway ($5/мес = всегда онлайн) |
| Длинные ответы | Уменьшите `MAX_TOKENS` до 150-200, добавьте в `SYSTEM_PROMPT`: «Отвечай максимально кратко, 1-2 предложения» |

## 📄 Лицензия

MIT — используйте как хотите.

---

**Сделано для сообщества. Если помогло — поставьте ⭐ на GitHub!**