# Couple Bot

Telegram-бот с общими задачами, списками, фильмами, путешествиями, желаниями и
заметками для двух участников пары.

## Локальный запуск на Windows

Нужен Python 3.12 или новее. Docker и отдельный PostgreSQL для локального запуска
не требуются: по умолчанию используется SQLite, а файл `couple_bot.db` создаётся
автоматически.

1. Создайте Telegram-бота через `@BotFather` и скопируйте токен.
2. В PowerShell из каталога проекта выполните:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

3. Откройте `.env` и укажите токен:

```dotenv
BOT_TOKEN=ваш_токен_от_BotFather
DATABASE_URL=sqlite+aiosqlite:///./couple_bot.db
DEFAULT_TIMEZONE=Europe/Moscow
LOG_LEVEL=INFO
```

4. Запустите бота:

```powershell
python -m app.main
```

Остановить его можно сочетанием `Ctrl+C`. Для полного сброса локальных данных
остановите бота и удалите `couple_bot.db`.

## Первый вход

Отправьте боту `/start`, нажмите «Создать пару» и передайте появившийся код
второму участнику. Второй участник присоединяется командой `/join КОД`.

## Проверки

```powershell
python -m compileall -q app
python -m ruff check app --select E9
python -m pytest -q
```

Для PostgreSQL можно явно задать `DATABASE_URL` вида
`postgresql+asyncpg://user:password@localhost:5432/couple_bot` и применить
миграции командой `alembic upgrade head`.
