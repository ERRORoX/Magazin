"""
Упрощенная база данных для бота

Структура:
- users: пользователи (ID, имя, возраст, страна, город)
- materials: материалы/уроки (ID, title, text_content)
- questions: вопросы (ID, material_id, question_text)
- answers: варианты ответов (ID, question_id, answer_text, is_correct)
- user_progress: прогресс изучения (user_id, material_id, studied_at)
- test_results: результаты тестов (user_id, material_id, correct, total, percentage, completed_at)
- ratings: рейтинг пользователей (user_id, total_score, rank)
"""
import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config import APP_ROOT

# Путь к файлу базы данных
DB_PATH = APP_ROOT / "данные" / "bot.db"
DB_PATH.parent.mkdir(exist_ok=True)


class Database:
    """Класс для работы с упрощенной SQLite базой данных"""
    
    def __init__(self, db_path: Path = DB_PATH):
        """Инициализация подключения к базе данных"""
        self.db_path = db_path
        self._init_database()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Создаёт и возвращает подключение к базе данных"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # Гарантируем работу внешних ключей для всех клиентов
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn
    
    def _init_database(self) -> None:
        """Создаёт таблицы, если их нет"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Таблица пользователей
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    age INTEGER,
                    country TEXT,
                    city TEXT,
                    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Таблица материалов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS materials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    text_content TEXT NOT NULL,
                    level TEXT NOT NULL DEFAULT 'базовый',
                    video_file_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Добавляем поле video_file_id если его нет (для существующих БД)
            try:
                cursor.execute("ALTER TABLE materials ADD COLUMN video_file_id TEXT")
            except sqlite3.OperationalError:
                # Колонка уже существует
                pass
            
            # Таблица вопросов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    material_id INTEGER NOT NULL,
                    question_text TEXT NOT NULL,
                    FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE
                )
            """)
            
            # Таблица ответов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS answers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_id INTEGER NOT NULL,
                    answer_text TEXT NOT NULL,
                    is_correct INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
                )
            """)
            
            # Таблица прогресса изучения
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_progress (
                    user_id INTEGER NOT NULL,
                    material_id INTEGER NOT NULL,
                    studied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, material_id),
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE
                )
            """)
            
            # Таблица результатов тестов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS test_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    material_id INTEGER NOT NULL,
                    correct INTEGER NOT NULL,
                    total INTEGER NOT NULL,
                    percentage REAL NOT NULL,
                    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE
                )
            """)
            
            # Таблица рейтингов (обновляется автоматически)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ratings (
                    user_id INTEGER PRIMARY KEY,
                    total_score REAL DEFAULT 0,
                    rank INTEGER,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
            """)
            
            # Индексы
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_questions_material ON questions(material_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_answers_question ON answers(question_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_progress_user ON user_progress(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_test_results_user ON test_results(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ratings_score ON ratings(total_score DESC)")

            # История обращений к ИИ
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL, -- user|assistant|system
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_history_user ON ai_history(user_id, created_at DESC)")

            # Краткие summary по пользователю
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_summaries (
                    user_id INTEGER PRIMARY KEY,
                    summary_text TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
            """)
            
            conn.commit()
            logging.info("Database initialized successfully")
    
    # ===== МЕТОДЫ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ =====
    
    def register_user(self, user_id: int, name: str, age: Optional[int] = None, 
                     country: Optional[str] = None, city: Optional[str] = None) -> bool:
        """Регистрирует нового пользователя"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO users (user_id, name, age, country, city, registered_at, last_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, name, age, country, city, datetime.now().isoformat(), datetime.now().isoformat()))
            conn.commit()
            return True
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        """Получает информацию о пользователе"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
    
    def is_user_registered(self, user_id: int) -> bool:
        """Проверяет, зарегистрирован ли пользователь"""
        return self.get_user(user_id) is not None
    
    def update_user_activity(self, user_id: int) -> None:
        """Обновляет время последней активности"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users SET last_active = ? WHERE user_id = ?
            """, (datetime.now().isoformat(), user_id))
            conn.commit()
    
    # ===== МЕТОДЫ ДЛЯ МАТЕРИАЛОВ =====
    
    def add_material(self, title: str, text_content: str, level: str = "базовый", video_file_id: Optional[str] = None) -> int:
        """Добавляет материал и возвращает его ID
        
        Args:
            title: Название материала
            text_content: Текст материала
            level: Уровень сложности (базовый, средний, продвинутый)
            video_file_id: ID видео файла в Telegram (опционально)
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO materials (title, text_content, level, video_file_id, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (title, text_content, level, video_file_id, datetime.now().isoformat()))
            conn.commit()
            return cursor.lastrowid
    
    def get_material(self, material_id: int) -> Optional[Dict]:
        """Получает материал по ID"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM materials WHERE id = ?", (material_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
    
    def get_all_materials(self, level: Optional[str] = None) -> List[Dict]:
        """Получает все материалы, опционально фильтруя по уровню
        
        Args:
            level: Уровень сложности для фильтрации (базовый, средний, продвинутый)
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if level:
                cursor.execute("SELECT * FROM materials WHERE level = ? ORDER BY id", (level,))
            else:
                cursor.execute("SELECT * FROM materials ORDER BY level, id")
            return [dict(row) for row in cursor.fetchall()]
    
    def delete_material(self, material_id: int) -> bool:
        """Удаляет материал и все связанные вопросы/ответы
        
        Returns:
            True если материал удален, False если не найден
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Проверяем существование
            cursor.execute("SELECT 1 FROM materials WHERE id = ?", (material_id,))
            if not cursor.fetchone():
                return False
            # Удаляем (каскадное удаление через FOREIGN KEY)
            cursor.execute("DELETE FROM materials WHERE id = ?", (material_id,))
            conn.commit()
            return True
    
    def update_material(self, material_id: int, title: Optional[str] = None, 
                       text_content: Optional[str] = None, level: Optional[str] = None,
                       video_file_id: Optional[str] = None) -> bool:
        """Обновляет материал
        
        Returns:
            True если материал обновлен, False если не найден
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Проверяем существование
            cursor.execute("SELECT 1 FROM materials WHERE id = ?", (material_id,))
            if not cursor.fetchone():
                return False
            
            # Формируем запрос обновления
            updates = []
            params = []
            
            if title is not None:
                updates.append("title = ?")
                params.append(title)
            if text_content is not None:
                updates.append("text_content = ?")
                params.append(text_content)
            if level is not None:
                updates.append("level = ?")
                params.append(level)
            if video_file_id is not None:
                updates.append("video_file_id = ?")
                params.append(video_file_id)
            
            if not updates:
                return False
            
            params.append(material_id)
            cursor.execute(f"""
                UPDATE materials 
                SET {', '.join(updates)}
                WHERE id = ?
            """, params)
            conn.commit()
            return cursor.rowcount > 0
    
    def append_to_material(self, material_id: int, additional_text: str) -> bool:
        """Добавляет текст к существующему материалу
        
        Args:
            material_id: ID материала
            additional_text: Текст для добавления
        
        Returns:
            True если текст добавлен, False если материал не найден
        """
        material = self.get_material(material_id)
        if not material:
            return False
        
        current_text = material.get('text_content', '')
        new_text = current_text + "\n\n" + additional_text
        return self.update_material(material_id, text_content=new_text)
    
    # ===== МЕТОДЫ ДЛЯ ВОПРОСОВ И ОТВЕТОВ =====
    
    def add_question(self, material_id: int, question_text: str) -> int:
        """Добавляет вопрос и возвращает его ID"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO questions (material_id, question_text)
                VALUES (?, ?)
            """, (material_id, question_text))
            conn.commit()
            return cursor.lastrowid
    
    def add_answer(self, question_id: int, answer_text: str, is_correct: bool) -> int:
        """Добавляет вариант ответа"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO answers (question_id, answer_text, is_correct)
                VALUES (?, ?, ?)
            """, (question_id, answer_text, 1 if is_correct else 0))
            conn.commit()
            return cursor.lastrowid
    
    def get_questions_for_material(self, material_id: int) -> List[Dict]:
        """Получает все вопросы для материала с ответами"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT q.id, q.question_text, q.material_id
                FROM questions q
                WHERE q.material_id = ?
                ORDER BY q.id
            """, (material_id,))
            questions = []
            for q_row in cursor.fetchall():
                question = dict(q_row)
                # Получаем ответы для вопроса
                cursor.execute("""
                    SELECT id, answer_text, is_correct
                    FROM answers
                    WHERE question_id = ?
                    ORDER BY id
                """, (question['id'],))
                question['answers'] = [dict(row) for row in cursor.fetchall()]
                questions.append(question)
            return questions
    
    # ===== МЕТОДЫ ДЛЯ ПРОГРЕССА =====
    
    def mark_material_studied(self, user_id: int, material_id: int) -> None:
        """Отмечает материал как изученный"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO user_progress (user_id, material_id, studied_at)
                VALUES (?, ?, ?)
            """, (user_id, material_id, datetime.now().isoformat()))
            conn.commit()
    
    def is_material_studied(self, user_id: int, material_id: int) -> bool:
        """Проверяет, изучен ли материал"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1 FROM user_progress
                WHERE user_id = ? AND material_id = ?
            """, (user_id, material_id))
            return cursor.fetchone() is not None
    
    def get_user_progress(self, user_id: int) -> List[int]:
        """Возвращает список ID изученных материалов"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT material_id FROM user_progress WHERE user_id = ?", (user_id,))
            return [row[0] for row in cursor.fetchall()]
    
    # ===== МЕТОДЫ ДЛЯ ТЕСТОВ =====
    
    def save_test_result(self, user_id: int, material_id: int, correct: int, 
                        total: int, percentage: float) -> None:
        """Сохраняет результат теста"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO test_results (user_id, material_id, correct, total, percentage, completed_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, material_id, correct, total, percentage, datetime.now().isoformat()))
            conn.commit()
            # Обновляем рейтинг
            self._update_rating(user_id)
    
    def get_test_result(self, user_id: int, material_id: int) -> Optional[Dict]:
        """Получает последний результат теста"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT correct, total, percentage, completed_at
                FROM test_results
                WHERE user_id = ? AND material_id = ?
                ORDER BY completed_at DESC
                LIMIT 1
            """, (user_id, material_id))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
    
    # ===== МЕТОДЫ ДЛЯ РЕЙТИНГА =====
    
    def _update_rating(self, user_id: int) -> None:
        """Обновляет рейтинг пользователя"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Подсчитываем общий балл: изученные материалы + результаты тестов
            cursor.execute("""
                SELECT 
                    COALESCE(COUNT(DISTINCT up.material_id), 0) * 10 +
                    COALESCE(SUM(tr.percentage) * 0.1, 0) as total_score
                FROM users u
                LEFT JOIN user_progress up ON u.user_id = up.user_id
                LEFT JOIN test_results tr ON u.user_id = tr.user_id
                WHERE u.user_id = ?
                GROUP BY u.user_id
            """, (user_id,))
            row = cursor.fetchone()
            total_score = row[0] if row else 0.0
            
            cursor.execute("""
                INSERT OR REPLACE INTO ratings (user_id, total_score, updated_at)
                VALUES (?, ?, ?)
            """, (user_id, total_score, datetime.now().isoformat()))
            conn.commit()
            # Обновляем ранги всех пользователей
            self._update_all_ranks()
    
    def update_all_ratings(self) -> None:
        """Обновляет рейтинги всех пользователей (вызывается при необходимости)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Получаем всех пользователей
            cursor.execute("SELECT user_id FROM users")
            users = cursor.fetchall()
            
            if not users:
                # Нет пользователей - просто обновляем ранги (они будут пустыми)
                self._update_all_ranks()
                return
            
            for (user_id,) in users:
                # Подсчитываем балл для каждого пользователя
                cursor.execute("""
                    SELECT 
                        COALESCE(COUNT(DISTINCT up.material_id), 0) * 10 +
                        COALESCE(SUM(tr.percentage) * 0.1, 0) as total_score
                    FROM users u
                    LEFT JOIN user_progress up ON u.user_id = up.user_id
                    LEFT JOIN test_results tr ON u.user_id = tr.user_id
                    WHERE u.user_id = ?
                    GROUP BY u.user_id
                """, (user_id,))
                row = cursor.fetchone()
                total_score = row[0] if row else 0.0
                
                cursor.execute("""
                    INSERT OR REPLACE INTO ratings (user_id, total_score, updated_at)
                    VALUES (?, ?, ?)
                """, (user_id, total_score, datetime.now().isoformat()))
            
            conn.commit()
            # Обновляем ранги
            self._update_all_ranks()
    
    def _update_all_ranks(self) -> None:
        """Обновляет ранги всех пользователей"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id, total_score
                FROM ratings
                ORDER BY total_score DESC
            """)
            users = cursor.fetchall()
            for rank, (user_id, _) in enumerate(users, 1):
                cursor.execute("""
                    UPDATE ratings SET rank = ? WHERE user_id = ?
                """, (rank, user_id))
            conn.commit()
    
    def get_leaderboard(self, limit: int = 10) -> List[Dict]:
        """Возвращает рейтинг пользователей"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    u.user_id,
                    u.name,
                    u.age,
                    u.country,
                    u.city,
                    r.total_score,
                    r.rank,
                    COUNT(DISTINCT up.material_id) as materials_studied,
                    COUNT(DISTINCT tr.id) as tests_completed
                FROM users u
                LEFT JOIN ratings r ON u.user_id = r.user_id
                LEFT JOIN user_progress up ON u.user_id = up.user_id
                LEFT JOIN test_results tr ON u.user_id = tr.user_id
                WHERE r.rank IS NOT NULL
                GROUP BY u.user_id, u.name, u.age, u.country, u.city, r.total_score, r.rank
                ORDER BY r.rank
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [
                {
                    'user_id': row[0],
                    'name': row[1],
                    'age': row[2],
                    'country': row[3],
                    'city': row[4],
                    'total_score': row[5],
                    'rank': row[6],
                    'materials_studied': row[7],
                    'tests_completed': row[8]
                }
                for row in rows
            ]
    
    def get_user_rank(self, user_id: int) -> Optional[Dict]:
        """Возвращает место пользователя в рейтинге"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    u.user_id,
                    u.name,
                    r.rank,
                    r.total_score,
                    COUNT(DISTINCT up.material_id) as materials_studied,
                    COUNT(DISTINCT tr.id) as tests_completed
                FROM users u
                LEFT JOIN ratings r ON u.user_id = r.user_id
                LEFT JOIN user_progress up ON u.user_id = up.user_id
                LEFT JOIN test_results tr ON u.user_id = tr.user_id
                WHERE u.user_id = ?
                GROUP BY u.user_id, u.name, r.rank, r.total_score
            """, (user_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    # ===== ПАМЯТЬ И ИСТОРИЯ ИИ =====

    def log_ai_message(self, user_id: int, role: str, content: str) -> None:
        """Сохраняет сообщение (user/assistant/system) в историю ИИ."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ai_history (user_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
            """, (user_id, role, content, datetime.now().isoformat()))
            conn.commit()

    def get_ai_history(self, user_id: int, limit: int = 6) -> List[Dict]:
        """Возвращает последние сообщения ИИ/пользователя для контекста."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT role, content, created_at
                FROM ai_history
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (user_id, limit))
            rows = cursor.fetchall()
            return [dict(row) for row in reversed(rows)]  # старые вперёд

    def upsert_ai_summary(self, user_id: int, summary_text: str) -> None:
        """Сохраняет краткое summary по пользователю."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ai_summaries (user_id, summary_text, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET summary_text = excluded.summary_text,
                                                updated_at = excluded.updated_at
            """, (user_id, summary_text, datetime.now().isoformat()))
            conn.commit()

    def get_ai_summary(self, user_id: int) -> Optional[str]:
        """Возвращает сохранённое summary пользователя."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT summary_text FROM ai_summaries WHERE user_id = ?
            """, (user_id,))
            row = cursor.fetchone()
            return row[0] if row else None

    # ===== Снимки прогресса для ИИ =====

    def get_user_snapshot(self, user_id: int) -> Dict:
        """Краткий профиль пользователя для контекста ИИ."""
        user = self.get_user(user_id) or {}
        progress_ids = self.get_user_progress(user_id)
        studied_count = len(progress_ids)

        last_materials = self.get_recent_materials_for_user(user_id, limit=3)
        recent_tests = self.get_recent_tests(user_id, limit=3)

        return {
            "user": user,
            "studied_count": studied_count,
            "last_materials": last_materials,
            "recent_tests": recent_tests,
        }

    def get_recent_materials_for_user(self, user_id: int, limit: int = 3) -> List[Dict]:
        """Последние изученные материалы пользователя (title, level, studied_at)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT m.id, m.title, m.level, up.studied_at
                FROM user_progress up
                JOIN materials m ON m.id = up.material_id
                WHERE up.user_id = ?
                ORDER BY up.studied_at DESC
                LIMIT ?
            """, (user_id, limit))
            return [dict(row) for row in cursor.fetchall()]

    def get_recent_tests(self, user_id: int, limit: int = 3) -> List[Dict]:
        """Последние результаты тестов пользователя."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT tr.material_id, tr.correct, tr.total, tr.percentage, tr.completed_at, m.title
                FROM test_results tr
                LEFT JOIN materials m ON m.id = tr.material_id
                WHERE tr.user_id = ?
                ORDER BY tr.completed_at DESC
                LIMIT ?
            """, (user_id, limit))
            return [dict(row) for row in cursor.fetchall()]

    # ===== СИДЫ МАТЕРИАЛОВ =====

    def _material_exists(self, title: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM materials WHERE title = ? LIMIT 1", (title,))
            return cursor.fetchone() is not None

    def seed_default_content(self) -> None:
        """Добавляет базовый набор материалов и тестов, если их нет."""
        default_materials = [
            {
                "title": "Базовый: Командная строка и навигация",
                "level": "базовый",
                "text": (
                    "Основы работы в терминале:\n"
                    "- ls, cd, pwd — навигация по файловой системе\n"
                    "- cp, mv, rm, mkdir — операции с файлами и папками\n"
                    "- cat, less, tail -f — просмотр файлов\n"
                    "- grep — поиск по тексту\n"
                    "- chmod, chown — права доступа\n"
                    "Практика: перемещайтесь по каталогам, создайте/удалите файлы, найдите строки с grep."
                ),
                "questions": [
                    {
                        "q": "Какой командой посмотреть текущий каталог?",
                        "answers": [("pwd", True), ("ls", False), ("cd ..", False)],
                    },
                    {
                        "q": "Что делает tail -f?",
                        "answers": [
                            ("Показывает новые строки файла в реальном времени", True),
                            ("Удаляет последние строки", False),
                            ("Меняет права файла", False),
                        ],
                    },
                ],
            },
            {
                "title": "Базовый: Пакеты и обновления",
                "level": "базовый",
                "text": (
                    "Управление пакетами в Debian/Kali:\n"
                    "- apt update / apt upgrade — обновление\n"
                    "- apt install <pkg> — установка\n"
                    "- apt remove / purge — удаление\n"
                    "- apt-cache search — поиск пакетов\n"
                    "- systemctl status/start/stop — управление службами\n"
                    "Практика: обновите индексы, поставьте утилиту и проверьте сервис."
                ),
                "questions": [
                    {
                        "q": "Какая команда обновляет список пакетов?",
                        "answers": [("apt update", True), ("apt upgrade", False), ("apt install", False)],
                    },
                    {
                        "q": "Чем отличается remove от purge?",
                        "answers": [
                            ("purge удаляет и конфиги", True),
                            ("remove удаляет и конфиги", False),
                            ("отличий нет", False),
                        ],
                    },
                ],
            },
            {
                "title": "Средний: Сеть и диагностика",
                "level": "средний",
                "text": (
                    "Инструменты сетевой диагностики:\n"
                    "- ip a, ip r — интерфейсы и маршруты\n"
                    "- ping, traceroute — проверка доступности и маршрута\n"
                    "- netstat/ss -lntp — сокеты и процессы\n"
                    "- nmap -sV -sC — базовое сканирование сервисов\n"
                    "- tcpdump -i eth0 port 80 — захват трафика\n"
                    "Практика: просканируйте хост, посмотрите открытые порты и трафик."
                ),
                "questions": [
                    {
                        "q": "Как показать маршруты по умолчанию?",
                        "answers": [("ip r", True), ("ip a", False), ("ss -lntp", False)],
                    },
                    {
                        "q": "Какая опция nmap определяет версии сервисов?",
                        "answers": [
                            ("-sV", True),
                            ("-sP", False),
                            ("-O", False),
                        ],
                    },
                ],
            },
            {
                "title": "Средний: Bash-скрипты и автоматизация",
                "level": "средний",
                "text": (
                    "Базовые конструкции Bash:\n"
                    "- shebang, chmod +x script.sh\n"
                    "- переменные, параметры $1, $@\n"
                    "- if/elif/else, case\n"
                    "- циклы for/while\n"
                    "- функции и exit codes\n"
                    "Практика: напишите скрипт, который пингует список хостов и пишет лог."
                ),
                "questions": [
                    {
                        "q": "Как сделать скрипт исполняемым?",
                        "answers": [("chmod +x script.sh", True), ("bash script.sh", False), ("source script.sh", False)],
                    },
                    {
                        "q": "Что содержит переменная $@?",
                        "answers": [
                            ("Все аргументы скрипта", True),
                            ("Только первый аргумент", False),
                            ("Код возврата", False),
                        ],
                    },
                ],
            },
            {
                "title": "Продвинутый: Реверс и бинарная безопасность",
                "level": "продвинутый",
                "text": (
                    "Основы реверса:\n"
                    "- file/strings/ldd — базовый анализ\n"
                    "- gdb/gef/pwndbg — отладка\n"
                    "- objdump -d, radare2 — дизассемблирование\n"
                    "- ASLR, NX, PIE — защиты\n"
                    "- Простые переполнения буфера и поиск гаджетов\n"
                    "Практика: найти уязвимый ввод, построить эксплойт для переполнения стека."
                ),
                "questions": [
                    {
                        "q": "Какая защита блокирует исполнение стека?",
                        "answers": [("NX", True), ("ASLR", False), ("PIE", False)],
                    },
                    {
                        "q": "Чем полезен objdump -d?",
                        "answers": [
                            ("Дизассемблирование бинаря", True),
                            ("Запуск программы", False),
                            ("Сборка из исходников", False),
                        ],
                    },
                ],
            },
            {
                "title": "Продвинутый: Web-пентест основы",
                "level": "продвинутый",
                "text": (
                    "Ключевые техники web-пентеста:\n"
                    "- Burp Suite Proxy/Repeater\n"
                    "- SQLi: UNION-based, boolean/time-based\n"
                    "- XSS: отражённый, хранимый, DOM\n"
                    "- SSRF, LFI/RFI\n"
                    "- Аутентификация/сессии: cookies, JWT, CSRF-токены\n"
                    "Практика: перехватите запрос, поищите инъекции и XSS на тестовом стенде."
                ),
                "questions": [
                    {
                        "q": "Какой тип XSS сохраняется на сервере?",
                        "answers": [("Хранимый (stored)", True), ("Отражённый", False), ("DOM без сервера", False)],
                    },
                    {
                        "q": "Что часто используют для защиты от CSRF?",
                        "answers": [
                            ("Уникальные токены в форме/заголовке", True),
                            ("Base64 кодирование", False),
                            ("Минификация JS", False),
                        ],
                    },
                ],
            },
        ]

        for material in default_materials:
            if self._material_exists(material["title"]):
                continue
            material_id = self.add_material(
                title=material["title"],
                text_content=material["text"],
                level=material["level"],
            )
            for q in material["questions"]:
                question_id = self.add_question(material_id, q["q"])
                for ans_text, is_correct in q["answers"]:
                    self.add_answer(question_id, ans_text, is_correct)


# Глобальный экземпляр базы данных
db = Database()
