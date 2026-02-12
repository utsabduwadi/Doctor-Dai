import sqlite3

def init_db():
    conn = None
    try:
        conn = sqlite3.connect("database.db")
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL
            )
        """)
        conn.commit()
    finally:
        if conn:
            conn.close()



def init_dbp():
    with sqlite3.connect("personal_database.db") as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS health_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name TEXT NOT NULL,
            height REAL,
            weight REAL,
            Age INTEGER,
            Gender TEXT,
            Systolic INTEGER,
            Diastolic INTEGER,
            Heart_rate INTEGER,
            blood_sugar INTEGER
        )
        """)

        # One-time migration from legacy table shape (users.user_name UNIQUE)
        legacy_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()
        if legacy_exists:
            conn.execute("""
                INSERT INTO health_entries (id, user_name, height, weight, Age, Gender, Systolic, Diastolic, Heart_rate, blood_sugar)
                SELECT id, user_name, height, weight, Age, Gender, Systolic, Diastolic, Heart_rate, blood_sugar
                FROM users
                WHERE NOT EXISTS (
                    SELECT 1 FROM health_entries he WHERE he.id = users.id
                )
            """)


def user_exists(username):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    return user is not None
