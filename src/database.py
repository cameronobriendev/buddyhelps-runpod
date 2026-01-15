"""
SQLite database for phone number configuration.
Stored on /workspace for persistence across pod restarts.
"""
import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Dict
from contextlib import contextmanager

# Use /workspace in RunPod (persistent), fallback to local for dev
DB_PATH = "/workspace/buddyhelps.db" if os.path.exists("/workspace") else "buddyhelps.db"

def init_db():
    """Initialize database and create tables if they don't exist."""
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS phone_numbers (
                phone_number TEXT PRIMARY KEY,
                business_name TEXT NOT NULL,
                business_type TEXT DEFAULT 'plumber',
                greeting_name TEXT DEFAULT 'Benny',
                system_prompt TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def get_all_numbers() -> List[Dict]:
    """Get all phone numbers."""
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM phone_numbers ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

def get_number(phone: str) -> Optional[Dict]:
    """Get a specific phone number config."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM phone_numbers WHERE phone_number = ?",
            (phone,)
        ).fetchone()
        return dict(row) if row else None

def add_number(
    phone_number: str,
    business_name: str,
    business_type: str = "plumber",
    greeting_name: str = "Benny",
    system_prompt: str = None,
    is_active: bool = True
) -> Dict:
    """Add a new phone number."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO phone_numbers
            (phone_number, business_name, business_type, greeting_name, system_prompt, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (phone_number, business_name, business_type, greeting_name, system_prompt, int(is_active)))
        conn.commit()
    return get_number(phone_number)

def update_number(phone_number: str, **kwargs) -> Optional[Dict]:
    """Update a phone number config."""
    allowed_fields = ['business_name', 'business_type', 'greeting_name', 'system_prompt', 'is_active']
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}

    if not updates:
        return get_number(phone_number)

    # Convert is_active to int
    if 'is_active' in updates:
        updates['is_active'] = int(updates['is_active'])

    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [phone_number]

    with get_db() as conn:
        conn.execute(
            f"UPDATE phone_numbers SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE phone_number = ?",
            values
        )
        conn.commit()

    return get_number(phone_number)

def delete_number(phone_number: str) -> bool:
    """Delete a phone number."""
    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM phone_numbers WHERE phone_number = ?",
            (phone_number,)
        )
        conn.commit()
        return cursor.rowcount > 0

def get_config_for_call(phone_number: str) -> Optional[Dict]:
    """
    Get config for an incoming call. Fast lookup.
    Returns None if number not found or inactive.
    """
    with get_db() as conn:
        row = conn.execute("""
            SELECT business_name, business_type, greeting_name, system_prompt
            FROM phone_numbers
            WHERE phone_number = ? AND is_active = 1
        """, (phone_number,)).fetchone()
        return dict(row) if row else None
