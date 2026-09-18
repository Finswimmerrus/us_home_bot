# Инфраструктура и продолжение разработки

## Цель

Продолжить разработку Telegram-бота для пары из каталога `C:\opt\couple-bot` на другом компьютере. Проект использует Python 3.12, Aiogram 3.7, SQLAlchemy 2, asyncpg, Alembic и PostgreSQL 16.

## Текущее состояние

- Локальный Git-репозиторий создан в этом каталоге; текущие наработки зафиксированы локальным коммитом.
- Docker Desktop 4.91.0 установлен в пользовательский профиль Windows, но Linux engine на этой машине не запустился: backend WSL2 сообщил `No virtualization available`.
- Docker Compose конфигурация присутствует и проходит `docker compose config`.
- Python 3.12.10 установлен в пользовательский профиль, создан `.venv`, зависимости проекта установлены.
- `compileall` проходит.
- В проекте пока нет тестов: `pytest` завершается без найденных тестов.
- Полная интеграционная проверка PostgreSQL и запуск бота ещё не выполнены.

## Инфраструктура

### Рекомендуемый вариант: Docker Compose

Файлы:

- `Dockerfile`
- `docker-compose.yml`
- `.dockerignore`
- `.env.example`

Compose поднимает:

- `db` — PostgreSQL 16 с постоянным volume `postgres_data`;
- `migrate` — одноразовый сервис `alembic upgrade head`;
- `bot` — `python -m app.main`, стартует после успешной миграции.

На машине с работающим Docker:

```powershell
Copy-Item .env.example .env
# заполнить BOT_TOKEN и DATABASE_URL в .env
docker compose up --build
```

Для однократной миграции:

```powershell
docker compose run --rm migrate
```

Не хранить `.env` в Git. Пароль из `docker-compose.yml` (`couplebot`) подходит только для локальной разработки; для продакшена заменить через `.env`.

### Вариант без Docker

На Windows, Linux или macOS:

1. Установить Python 3.12+.
2. Создать PostgreSQL 16 и базу `couple_bot`.
3. Создать пользователя БД и задать пароль.
4. Создать `.env` по образцу `.env.example`.
5. Установить зависимости:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

На Linux/macOS использовать `source .venv/bin/activate`.

Проверить миграции:

```powershell
alembic upgrade head
```

Запустить бота:

```powershell
python -m app.main
```

Для Windows может понадобиться пакет `tzdata`, чтобы `zoneinfo` находил `Europe/Moscow`:

```powershell
python -m pip install tzdata
```

## Что уже сделано

- Синхронизированы модели, репозитории и миграция `0001_initial.py`; проверена структура 13 таблиц.
- Исправлены `app/database.py`, `app/db_init.py`, `migrations/env.py`: устранены устаревшие импорты и несогласованные настройки DATABASE_URL.
- Добавлены server default для полей, где они требуются PostgreSQL.
- Исправлен composite foreign key `list_items` и порядок downgrade в миграции.
- Добавлен `app/handlers/sections.py`, чтобы `app/main.py` не падал на отсутствующем импорте.
- Синхронизированы `trip_service.py` и `wishlist_service.py` с текущими моделями и репозиториями.
- Исправлена сессионная фабрика в `app/middleware/session_mw.py`.
- Исправлена невалидная таблица `mypy.overrides` в `pyproject.toml`.
- Добавлены Dockerfile и Docker Compose.
- Добавлен `.dockerignore`.
- Установлены локальные инструменты: Python 3.12.10, Docker Desktop 4.91.0, зависимости `.venv`.

## Известные проблемы перед следующим запуском

1. На текущей Windows Docker engine не работает из-за WSL2/виртуализации. На другом компьютере сначала проверить:
   - включена ли виртуализация в BIOS/UEFI;
   - включены ли `Microsoft-Windows-Subsystem-Linux` и `VirtualMachinePlatform`;
   - работает ли `wsl --status` и `wsl --list --verbose`;
   - запускается ли `docker info`.
2. Если Docker использует WSL2, но WSL недоступен, попробовать Docker VMM в настройках Docker Desktop или обычный Linux/WSL2. Не менять системные настройки без понимания последствий.
3. В проекте отсутствуют тесты. Перед релизом добавить unit-тесты сервисов и integration-тесты репозиториев с отдельной тестовой PostgreSQL.
4. После завершения фонового исправления кода нужно повторить:
   - `python -m compileall -q app migrations`;
   - `ruff check app migrations`;
   - `mypy app`;
   - `pytest -q`;
   - `docker compose config`;
   - `docker compose up --build` при работающем Docker;
   - `alembic upgrade head` и проверку таблиц PostgreSQL.
5. Проверить `app/handlers/start.py` на обработку `callback.message is None` и `InaccessibleMessage`; это влияет на стабильность при обновлениях Telegram.
6. Проверить все сервисы через реальные CRUD-сценарии, особенно задачи, списки, путешествия и вишлист.
7. Для продакшена добавить настоящий `.env`, секреты, health checks, логирование, backup и systemd/другой supervisor; текущий README содержит черновой Linux/systemd-план, но соответствующие файлы могут отсутствовать.

## Архитектура

- `app/main.py` — точка входа Aiogram.
- `app/handlers/` — команды, FSM и маршруты разделов.
- `app/services/` — доменная логика и проверки доступа.
- `app/repositories/` — SQLAlchemy-доступ к PostgreSQL.
- `app/models/` — ORM-модели.
- `migrations/` — Alembic.
- `app/middleware/` — контекст пользователя, сессия БД и обработка ошибок.
- `app/utils/` — контекст, коды приглашений, БД и логирование.

## Продолжение для ИИ

Начать с чтения этого файла, `README.md`, `pyproject.toml`, `docker-compose.yml`, `app/main.py` и последних изменений Git. Не считать Docker установленным работоспособным только по наличию Docker Desktop. Сначала выполнить проверки `wsl`/`docker info`. Не коммитить `.env`, `.venv`, `__pycache__`, кэши и локальные backup-файлы. Не выкладывать токены и пароли в Git.
