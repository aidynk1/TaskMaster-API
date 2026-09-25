import sqlite3
import bcrypt
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel

app = FastAPI(
    title="TaskMaster API",
    description="Сервис управления задачами с регистрацией и аутентификацией",
    version="1.0.0"
)

DATABASE = "taskmaster.db"


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
        raise HTTPException(status_code=401, detail="Отсутствует или неверный токен авторизации")
    
    token = authorization.replace("Bearer ", "")
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, username FROM users WHERE username = ?", (token,))
    user = cursor.fetchone()
    conn.close()

    if not user:
        raise HTTPException(status_code=401, detail="Недействительный токен / пользователь не найден")
    
    return {"id": user[0], "username": user[1]}



@app.post("/register", summary="Регистрация пользователя")
def register(user: UserSchema):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    hashed = bcrypt.hashpw(user.password.encode("utf-8"), bcrypt.gensalt())
    try:
        cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (user.username, hashed))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Пользователь с таким именем уже существует")
    
    conn.close()
    return {"message": "Пользователь успешно зарегистрирован"}

@app.post("/login", summary="Вход пользователя")
def login(user: UserSchema):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash FROM users WHERE username = ?", (user.username,))
    row = cursor.fetchone()
    conn.close()

    if not row or not bcrypt.checkpw(user.password.encode("utf-8"), row[0]):
        raise HTTPException(status_code=401, detail="Неверное имя пользователя или пароль")

    
    return {"token": f"Bearer {user.username}", "token_type": "bearer"}



@app.get("/tasks", response_model=List[TaskResponse], summary="Получить все задачи текущего пользователя")
def get_tasks(current_user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, description, completed, user_id FROM tasks WHERE user_id = ?", (current_user["id"],))
    rows = cursor.fetchall()
    conn.close()

    return [
        {"id": r[0], "title": r[1], "description": r[2], "completed": bool(r[3]), "user_id": r[4]} 
        for r in rows
    ]

@app.post("/tasks", response_model=TaskResponse, summary="Создать новую задачу")
def create_task(task: TaskCreate, current_user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO tasks (title, description, completed, user_id) VALUES (?, ?, 0, ?)",
        (task.title, task.description, current_user["id"])
    )
    conn.commit()
    task_id = cursor.lastrowid
    conn.close()

    return {"id": task_id, "title": task.title, "description": task.description, "completed": False, "user_id": current_user["id"]}

@app.put("/tasks/{task_id}", response_model=TaskResponse, summary="Обновить задачу")
def update_task(task_id: int, task: TaskUpdate, current_user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    
    cursor.execute("SELECT id, title, description, completed FROM tasks WHERE id = ? AND user_id = ?", (task_id, current_user["id"]))
    existing = cursor.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Задача не найдена или принадлежит другому пользователю")

    new_title = task.title if task.title is not None else existing[1]
    new_desc = task.description if task.description is not None else existing[2]
    new_completed = task.completed if task.completed is not None else bool(existing[3])

    cursor.execute(
        "UPDATE tasks SET title = ?, description = ?, completed = ? WHERE id = ? AND user_id = ?",
        (new_title, new_desc, int(new_completed), task_id, current_user["id"])
    )
    conn.commit()
    conn.close()

    return {"id": task_id, "title": new_title, "description": new_desc, "completed": new_completed, "user_id": current_user["id"]}

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