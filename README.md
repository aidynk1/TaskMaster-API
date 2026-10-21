# TaskMaster API

Сервис для управления задачами: пользователи регистрируются, создают задачи, обновляют их и отмечают выполнение. Написан на FastAPI + SQLite.

## Возможности
- Регистрация и вход, пароли хранятся в виде bcrypt-хэшей
- Полный CRUD по задачам: создать, посмотреть, изменить, удалить
- Задачи привязаны к пользователю — чужие записи не видны
- Автодокументация Swagger UI на `/docs`

## Стек
Python 3.12 · FastAPI · Uvicorn · SQLite · Pydantic · bcrypt

## Запуск проекта
1. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```

## Запуск в Docker
Выполните команды из корневой папки проекта:

```bash
docker build -t taskmaster-api .
```

Перед запуском создайте локальный `.env` на основе `.env.example` и задайте
случайный `AUTH_TOKEN_SECRET` длиной не менее 32 символов. Сгенерировать значение
можно командой:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

В Windows создайте файл командой `Copy-Item .env.example .env` (в Linux/macOS —
`cp .env.example .env`) и замените значение `AUTH_TOKEN_SECRET` на сгенерированное.
Файл `.env` исключён из Git; не публикуйте его и не добавляйте секрет в исходный код.

Для локальной разработки запустите:

```bash
uvicorn main:app --reload
```

Для запуска контейнера передайте настройки через env-файл и ограничьте публикацию
порта локальным интерфейсом:

```bash
docker run --rm --name taskmaster-api --env-file .env -p 127.0.0.1:8000:8000 taskmaster-api
```

Проверка доступности: `http://localhost:8000/health` возвращает
`{"status":"ok"}`. Прикладные логи INFO и выше выводятся в консоль и в
`app.log`; файл ограничен ротацией.