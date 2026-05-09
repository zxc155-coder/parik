# zabolot-bot 🤖

Telegram-бот с нейросетью **MiniMax M2.5** (через Canopy Wave) с четырьмя режимами:

| Режим | Описание | Модель |
| ----- | -------- | ------ |
| 💬 Личный чат | Просто пишешь боту в личку — он отвечает | `minimax/minimax-m2.5` |
| 🖼 Распознавание фото | Шлёшь фото (с caption или без) — бот его описывает / отвечает на вопросы | `zai/glm-5.1` (любой OpenAI-совместимый vision endpoint) |
| 🌐 Inline | `@your_bot вопрос` в любом чате → ответ появляется прямо там | `minimax/minimax-m2.5` |
| 🚀 Web App | Полноценный чат-интерфейс прямо в Telegram (вкл. прикрепление фото) | оба |

## Структура

```
app/
  ai_client.py      # клиент Canopy Wave OpenAI-совместимого API
  config.py         # настройки из .env
  main.py           # запуск бота + веб-сервера
  bot/handlers.py   # хендлеры aiogram (текст / фото / inline / /start /help /reset)
  webapp/
    auth.py         # валидация Telegram WebApp initData
    server.py       # FastAPI: /api/chat, статика
webapp_static/      # фронтенд Web App (HTML/CSS/JS)
```

## Установка

```bash
git clone https://github.com/<owner>/zabolot-bot.git
cd zabolot-bot
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env
# отредактируй .env: BOT_TOKEN, CANOPYWAVE_API_KEY, WEBAPP_URL
```

## Запуск

```bash
python -m app.main
```

Эта команда поднимает одновременно:
- Telegram-бота (long-polling)
- HTTP-сервер на `:8000` (отдаёт `webapp_static/` и `/api/chat`)

Можно запускать раздельно:

```bash
python -m app.main --no-web   # только бот
python -m app.main --no-bot   # только веб-сервер (для деплоя фронта)
```

## Настройка через @BotFather

1. **Создать бота** (если ещё нет): `/newbot`, скопировать токен в `BOT_TOKEN`.
2. **Включить inline-режим**: `/mybots` → бот → `Bot Settings` → `Inline Mode` → `Turn on`. Опционально задать `Inline Placeholder` (например `Спросить zabolotAI…`).
3. **Web App**:
   - Задеплой `webapp_static/` куда-нибудь по HTTPS (или используй встроенный сервер за HTTPS-прокси).
   - В `/mybots` → бот → `Bot Settings` → `Menu Button` → задай текст и URL → этот же URL впиши в `.env` как `WEBAPP_URL`. После рестарта в `/start` появится кнопка «🚀 Открыть веб-приложение».

## Переменные окружения

| Переменная | Описание |
| ---------- | -------- |
| `BOT_TOKEN` | Токен от @BotFather |
| `CANOPYWAVE_API_KEY` | Ключ из https://cloud.canopywave.io |
| `CANOPYWAVE_BASE_URL` | По умолчанию `https://api.canopywave.io/v1` |
| `TEXT_MODEL` | По умолчанию `minimax/minimax-m2.5` |
| `VISION_MODEL` | По умолчанию `zai/glm-5.1` |
| `VISION_API_KEY` | (опц.) ключ отдельного vision-провайдера (например OpenRouter). Если пусто — используется `CANOPYWAVE_API_KEY` |
| `VISION_BASE_URL` | (опц.) base URL отдельного vision-провайдера, например `https://openrouter.ai/api/v1` |
| `WEBAPP_URL` | Публичный HTTPS-URL Web App (для кнопки в `/start`) |
| `HOST` / `PORT` | Биндинг веб-сервера (по умолчанию `0.0.0.0:8000`) |
| `ALLOWED_USER_IDS` | Список разрешённых Telegram user id через запятую (пусто = все) |

## Безопасность Web App

`/api/chat` валидирует `initData` от Telegram по [официальной схеме HMAC](https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app), используя `BOT_TOKEN`. Запросы без подписи (или с просроченной — старше 24ч) отбрасываются с `401`.

## Команды бота

- `/start` — приветствие + кнопка Web App
- `/help` — справка
- `/reset` — очистить контекст разговора (диалог хранится в памяти процесса, до `~12` сообщений на чат)

## Локальное тестирование без Telegram

```bash
python -m app.main --no-bot   # запустит только веб
# открыть http://localhost:8000 — UI будет, но запросы /api/chat будут отбиты 401
# (из браузера это нормально; для отладки временно поставь skip_auth=True в create_app)
```

## Лицензия

MIT.
