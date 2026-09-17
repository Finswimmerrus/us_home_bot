# Couple Bot — Telegram-бот для пары

## Установка на Linux VPS

### 1. Установка Python 3.12+

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3.12-dev
```

### 2. Установка PostgreSQL

```bash
sudo apt install -y postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

### 3. Создание пользователя и базы данных

```bash
sudo -u postgres psql

CREATE USER couplebot WITH PASSWORD 'secure_password';
CREATE DATABASE couple_bot OWNER couplebot;
ALTER USER couplebot CREATEDB;
\q
```

### 4. Создание Linux-пользователя для бота

```bash
sudo useradd -r -m -s /bin/bash couplebot
sudo su - couplebot
```

### 5. Клонирование проекта

```bash
cd ~
git clone <repo-url> couple-bot
cd couple-bot
```

### 6. Создание virtualenv и установка зависимостей

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -e .
```

### 7. Настройка .env

```bash
cp .env.example .env
nano .env
```

Заполнить BOT_TOKEN и DATABASE_URL.

### 8. Выполнение миграций Alembic

```bash
alembic upgrade head
```

### 9. Запуск через systemd

```bash
sudo cp systemd/couple-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable couple-bot
sudo systemctl start couple-bot
```

### 10. Проверка логов

```bash
sudo journalctl -u couple-bot -f
```

## Резервное копирование

```bash
./scripts/backup_db.sh
```

Для автоматизации добавьте cron или systemd timer:

```bash
crontab -e
# Ежедневно в 3:00:
0 3 * * * /opt/couple-bot/scripts/backup_db.sh
```

## Тесты

```bash
pytest
```
