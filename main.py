import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
import sqlite3
import time
from logging.handlers import RotatingFileHandler
from typing import List, Optional

import bcrypt
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel

load_dotenv()

LOG_FILE = os.getenv("LOG_FILE", "app.log")
logger = logging.getLogger("taskmaster")
logger.setLevel(logging.INFO)
logger.propagate = False

if not logger.handlers:
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

app = FastAPI(
    title="TaskMaster API",
    description="Сервис управления задачами с регистрацией и аутентификацией",
    version="1.0.0"
)

DATABASE = os.getenv("DATABASE_PATH", "taskmaster.db")
ACCESS_TOKEN_TTL_SECONDS = 60 * 60


def _get_token_secret() -> bytes:
    secret = os.getenv("AUTH_TOKEN_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError(
            "AUTH_TOKEN_SECRET must be configured with at least 32 characters"
        )
    return secret.encode("utf-8")


def _encode_token_part(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def create_access_token(username: str) -> str:
    payload = json.dumps(
        {
            "sub": username,
            "exp": int(time.time()) + ACCESS_TOKEN_TTL_SECONDS,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    encoded_payload = _encode_token_part(payload)
    signature = hmac.new(
        _get_token_secret(),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{encoded_payload}.{_encode_token_part(signature)}"


def verify_access_token(token: str) -> Optional[str]:
    try:
        encoded_payload, encoded_signature = token.split(".", maxsplit=1)
        supplied_signature = base64.urlsafe_b64decode(
            encoded_signature + "=" * (-len(encoded_signature) % 4)
        )
        expected_signature = hmac.new(
            _get_token_secret(),
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            return None

        payload_bytes = base64.urlsafe_b64decode(
            encoded_payload + "=" * (-len(encoded_payload) % 4)
        )
        payload = json.loads(payload_bytes)
        username = payload["sub"]
        expires_at = payload["exp"]
        if not isinstance(username, str) or not isinstance(expires_at, int):
            return None
        if expires_at <= int(time.time()):
            return None
        return username
    except (
        ValueError,
        TypeError,
        KeyError,
        UnicodeDecodeError,
        binascii.Error,
        json.JSONDecodeError,
    ):
        return None


def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash BLOB NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            completed BOOLEAN DEFAULT 0,
            user_id INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)

    conn.commit()
    conn.close()


init_db()
logger.info("TaskMaster API initialized")


class UserSchema(BaseModel):
    username: str
    password: str


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    completed: Optional[bool] = None


class TaskResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    completed: bool
    user_id: int


def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        logger.warning("Request rejected: missing or invalid bearer authorization")
        raise HTTPException(status_code=401, detail="Отсутствует или неверный токен авторизации")

    username = verify_access_token(authorization.removeprefix("Bearer "))
    if not username:
        logger.warning("Request rejected: invalid or expired bearer token")
        raise HTTPException(status_code=401, detail="Недействительный или просроченный токен")

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, username FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()

    if not user:
        logger.warning("Request rejected: token subject does not exist")
        raise HTTPException(
            status_code=401,
            detail="Недействительный токен / пользователь не найден")

    return {"id": user[0], "username": user[1]}


@app.middleware("http")
async def log_unhandled_exceptions(request, call_next):
    try:
        return await call_next(request)
    except Exception:
        logger.exception(
            "Unhandled error while processing %s %s",
            request.method,
            request.url.path,
        )
        raise


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/register", summary="Регистрация пользователя")
def register(user: UserSchema):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    hashed = bcrypt.hashpw(user.password.encode("utf-8"), bcrypt.gensalt())
    try:
        cursor.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (user.username, hashed),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        logger.warning("Registration rejected: username already exists")
        raise HTTPException(status_code=400, detail="Пользователь с таким именем уже существует")

    conn.close()
    logger.info("User registration succeeded")
    return {"message": "Пользователь успешно зарегистрирован"}


@app.post("/login", summary="Вход пользователя")
def login(user: UserSchema):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash FROM users WHERE username = ?", (user.username,))
    row = cursor.fetchone()
    conn.close()

    if not row or not bcrypt.checkpw(user.password.encode("utf-8"), row[0]):
        logger.warning("Login rejected: invalid credentials")
        raise HTTPException(status_code=401, detail="Неверное имя пользователя или пароль")

    logger.info("User login succeeded")
    return {
        "token": create_access_token(user.username),
        "token_type": "bearer",
    }


@app.get("/tasks", response_model=List[TaskResponse],
         summary="Получить все задачи текущего пользователя")
def get_tasks(current_user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, title, description, completed, user_id FROM tasks WHERE user_id = ?",
        (current_user["id"],),
    )
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": r[0],
            "title": r[1],
            "description": r[2],
            "completed": bool(r[3]),
            "user_id": r[4],
        }
        for r in rows
    ]


@app.post("/tasks", response_model=TaskResponse, summary="Создать новую задачу")
def create_task(task: TaskCreate, current_user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO tasks (title, description, completed, user_id) VALUES (?, ?, 0, ?)",
        (task.title, task.description, current_user["id"]),
    )
    conn.commit()
    task_id = cursor.lastrowid
    conn.close()

    return {
        "id": task_id,
        "title": task.title,
        "description": task.description,
        "completed": False,
        "user_id": current_user["id"],
    }


@app.put("/tasks/{task_id}", response_model=TaskResponse, summary="Обновить задачу")
def update_task(task_id: int, task: TaskUpdate, current_user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, title, description, completed FROM tasks "
        "WHERE id = ? AND user_id = ?",
        (task_id, current_user["id"]),
    )
    existing = cursor.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(
            status_code=404,
            detail="Задача не найдена или принадлежит другому пользователю")

    new_title = task.title if task.title is not None else existing[1]
    new_desc = task.description if task.description is not None else existing[2]
    new_completed = task.completed if task.completed is not None else bool(existing[3])

    cursor.execute(
        "UPDATE tasks SET title = ?, description = ?, completed = ? WHERE id = ? AND user_id = ?",
        (new_title, new_desc, int(new_completed), task_id, current_user["id"])
    )
    conn.commit()
    conn.close()

    return {
        "id": task_id,
        "title": new_title,
        "description": new_desc,
        "completed": new_completed,
        "user_id": current_user["id"],
    }


@app.delete("/tasks/{task_id}", summary="Удалить задачу")
def delete_task(task_id: int, current_user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, current_user["id"]))

    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Задача не найдена")

    conn.commit()
    conn.close()
    return {"message": "Задача успешно удалена"}
