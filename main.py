# main.py — Alice LLM Bridge
# FastAPI сервер для интеграции Яндекс Алисы с внешней LLM

from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import httpx
import os
import logging
from datetime import datetime
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# ──────────────────────────────────────────────
# Конфигурация
# ──────────────────────────────────────────────

LLM_API_URL = os.getenv("LLM_API_URL", "https://openrouter.ai/api/v1/chat/completions")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "meta-llama/llama-3.1-8b-instruct:free")
SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "Ты — полезный голосовой ассистент. Отвечай кратко, по-русски, "
    "в разговорном стиле. Без markdown-разметки. Максимум 2-3 предложения."
)
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "300"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.7"))
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "30.0"))

# HTTP клиент (переиспользуем соединения)
http_client: Optional[httpx.AsyncClient] = None

# ──────────────────────────────────────────────
# Логирование
# ──────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("alice-llm-bridge")

# ──────────────────────────────────────────────
# Модели данных ( Алиса API v1.0)
# ──────────────────────────────────────────────

class NLUEntity(BaseModel):
    type: str
    tokens: Dict[str, Any] = Field(default_factory=dict)
    value: Any = None

class NLU(BaseModel):
    tokens: List[str] = Field(default_factory=list)
    entities: List[NLUEntity] = Field(default_factory=list)
    intents: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

class AliceRequestPayload(BaseModel):
    command: str = ""
    original_utterance: str = ""
    type: str = "SimpleUtterance"
    nlu: NLU = Field(default_factory=NLU)
    markup: Dict[str, Any] = Field(default_factory=dict)

class AliceSession(BaseModel):
    session_id: str
    message_id: int
    user_id: str
    skill_id: Optional[str] = None
    new: bool = False
    user: Dict[str, Any] = Field(default_factory=dict)
    application: Dict[str, Any] = Field(default_factory=dict)

class AliceMeta(BaseModel):
    locale: str = "ru-RU"
    timezone: str = "UTC"
    client_id: str = ""
    interfaces: Dict[str, Any] = Field(default_factory=dict)

class AliceRequest(BaseModel):
    meta: AliceMeta
    request: AliceRequestPayload
    session: AliceSession
    version: str = "1.0"

class AliceButton(BaseModel):
    title: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    hide: bool = False

class AliceResponsePayload(BaseModel):
    text: str = ""
    tts: Optional[str] = None
    end_session: bool = False
    buttons: List[AliceButton] = Field(default_factory=list)
    card: Optional[Dict[str, Any]] = None
    directives: Dict[str, Any] = Field(default_factory=dict)

class AliceResponseSession(BaseModel):
    session_id: str
    message_id: int
    user_id: str
    skill_id: Optional[str] = None
    user: Dict[str, Any] = Field(default_factory=dict)

class AliceResponse(BaseModel):
    response: AliceResponsePayload
    session: AliceResponseSession
    version: str = "1.0"

# ──────────────────────────────────────────────
# Lifecycle
# ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    # Startup
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(REQUEST_TIMEOUT),
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
    )
    logger.info("🚀 Server started")
    logger.info(f"LLM: {LLM_MODEL} @ {LLM_API_URL}")
    yield
    # Shutdown
    await http_client.aclose()
    logger.info("👋 Server stopped")

app = FastAPI(
    title="Alice LLM Bridge",
    description="Bridge between Yandex Alice and external LLM",
    version="1.0.0",
    lifespan=lifespan
)

# ──────────────────────────────────────────────
# Логика маршрутизации
# ──────────────────────────────────────────────

# Интенты, которые мы перехватываем для LLM
LLM_INTENTS = {
    "general_question",
    "creative_task",
    "code_help",
}

# Системные интенты Алисы — НЕ перехватываем
SYSTEM_INTENTS = {
    "alarm_clock", "timer", "shopping_list", "music",
    "smart_home", "weather", "news", "recipes",
    "radio", "podcasts", "kinopoisk", "tv", "video",
    "maps", "transport", "taxi", "food", "market",
    "games", "horoscope", "currency", "stocks",
    "translate", "dictionary", "wiki", "calculator",
    "unit_converter", "color_picker", "password_generator",
}

def should_use_llm(request: AliceRequest) -> bool:
    """Определяем, отправлять ли запрос в LLM"""
    intents = request.request.nlu.intents
    
    # 1. Явно наши интенты → LLM
    if any(intent in intents for intent in LLM_INTENTS):
        logger.debug(f"LLM intent detected: {[i for i in intents if i in LLM_INTENTS]}")
        return True
    
    # 2. Нет интентов вообще (Алиса не распознала) → LLM
    if not intents:
        logger.debug("No intents → LLM")
        return True
    
    # 3. Системные интенты Алисы → не трогаем
    matched_system = [i for i in intents if i in SYSTEM_INTENTS]
    if matched_system:
        logger.debug(f"System intent detected: {matched_system} → pass through")
        return False
    
    # 4. Неизвестный интент → пробуем LLM (безопаснее)
    logger.debug(f"Unknown intent: {list(intents.keys())} → LLM")
    return True

# ──────────────────────────────────────────────
# Работа с LLM
# ──────────────────────────────────────────────

async def call_llm(user_text: str, session_id: str) -> str:
    """Вызов внешней LLM API"""
    if not LLM_API_KEY:
        logger.error("LLM_API_KEY not set!")
        return "Сервис временно недоступен. Настройте API ключ."
    
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/alice-llm-bridge",
        "X-Title": "Alice LLM Bridge"
    }
    
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text}
        ],
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
        "stream": False
    }
    
    try:
        logger.info(f"🤖 LLM request: {user_text[:80]}...")
        resp = await http_client.post(LLM_API_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        
        answer = data["choices"][0]["message"]["content"].strip()
        logger.info(f"✅ LLM response: {answer[:80]}...")
        return answer
        
    except httpx.HTTPStatusError as e:
        logger.error(f"LLM HTTP error {e.response.status_code}: {e.response.text[:200]}")
        if e.response.status_code == 401:
            return "Ошибка авторизации LLM. Проверьте API ключ."
        elif e.response.status_code == 429:
            return "Слишком много запросов. Подождите немного."
        return "Ошибка при обращении к ИИ. Попробуйте позже."
        
    except httpx.TimeoutException:
        logger.error("LLM request timeout")
        return "ИИ не успел ответить. Попробуйте короче вопрос."
        
    except Exception as e:
        logger.error(f"LLM error: {type(e).__name__}: {e}")
        return "Произошла ошибка. Попробуйте ещё раз."

# ──────────────────────────────────────────────
# Эндпоинты
# ──────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Health check для Render / мониторинга"""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "model": LLM_MODEL,
        "llm_configured": bool(LLM_API_KEY)
    }

@app.get("/")
async def root():
    return {
        "name": "Alice LLM Bridge",
        "version": "1.0.0",
        "docs": "/docs",
        "webhook": "/alice/webhook",
        "health": "/health"
    }

@app.post("/alice/webhook")
async def alice_webhook(request: AliceRequest):
    """Главный webhook для Яндекс Алисы"""
    
    # Извлекаем данные
    user_text = request.request.command.strip()
    session_id = request.session.session_id
    is_new_session = request.session.new
    message_id = request.session.message_id
    user_id = request.session.user_id
    
    logger.info(f"📥 Session: {session_id} | Msg: {message_id} | New: {is_new_session} | Text: '{user_text}'")
    
    # ──────────────────────────────────────────
    # Новая сессия — приветствие
    # ──────────────────────────────────────────
    if is_new_session:
        return AliceResponse(
            response=AliceResponsePayload(
                text="Привет! Я подключил к себе большую языковую модель. Спрашивай что угодно — от рецептов до кода.",
                end_session=False
            ),
            session=AliceResponseSession(
                session_id=session_id,
                message_id=message_id,
                user_id=user_id
            ),
            version=request.version
        )
    
    # ──────────────────────────────────────────
    # Пустой запрос
    # ──────────────────────────────────────────
    if not user_text:
        return AliceResponse(
            response=AliceResponsePayload(
                text="Не расслышала. Повторите, пожалуйста.",
                end_session=False
            ),
            session=AliceResponseSession(
                session_id=session_id,
                message_id=message_id,
                user_id=user_id
            ),
            version=request.version
        )
    
    # ──────────────────────────────────────────
    # Маршрутизация
    # ──────────────────────────────────────────
    use_llm = should_use_llm(request)
    
    if not use_llm:
        # Системная команда — возвращаем пустой ответ,
        # Алиса сама обработает и озвучит результат
        logger.info("➡️ Pass through to Alice built-in")
        return AliceResponse(
            response=AliceResponsePayload(
                text="",
                end_session=False
            ),
            session=AliceResponseSession(
                session_id=session_id,
                message_id=message_id,
                user_id=user_id
            ),
            version=request.version
        )
    
    # ──────────────────────────────────────────
    # Вызов LLM
    # ──────────────────────────────────────────
    answer = await call_llm(user_text, session_id)
    
    return AliceResponse(
        response=AliceResponsePayload(
            text=answer,
            end_session=False
        ),
        session=AliceResponseSession(
            session_id=session_id,
            message_id=message_id,
            user_id=user_id
        ),
        version=request.version
    )

# ──────────────────────────────────────────────
# Запуск локально: python main.py
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)