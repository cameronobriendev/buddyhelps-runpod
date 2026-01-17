"""
SQLite database for phone number configuration.
Stored on /workspace for persistence across pod restarts.
"""
import sqlite3
import os
import json
from datetime import datetime
from typing import Optional, List, Dict
from contextlib import contextmanager

# Use /workspace in RunPod (persistent), fallback to local for dev
DB_PATH = "/workspace/buddyhelps.db" if os.path.exists("/workspace") else "buddyhelps.db"

def init_db():
    """Initialize database and create tables if they don't exist."""
    with get_db() as conn:
        # System prompts table (reusable templates)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS system_prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                content TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Keyword corrections table (STT post-processing)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS keyword_corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                corrections TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Check if phone_numbers needs migration
        cursor = conn.execute("PRAGMA table_info(phone_numbers)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'system_prompt_id' not in columns and 'phone_number' in columns:
            conn.execute("ALTER TABLE phone_numbers ADD COLUMN system_prompt_id INTEGER")
        if 'keyword_corrections_id' not in columns and 'phone_number' in columns:
            conn.execute("ALTER TABLE phone_numbers ADD COLUMN keyword_corrections_id INTEGER")
        if 'is_demo' not in columns and 'phone_number' in columns:
            conn.execute("ALTER TABLE phone_numbers ADD COLUMN is_demo INTEGER DEFAULT 0")

        # Phone numbers table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS phone_numbers (
                phone_number TEXT PRIMARY KEY,
                business_name TEXT NOT NULL,
                business_type TEXT DEFAULT 'plumber',
                greeting_name TEXT DEFAULT 'Benny',
                system_prompt_id INTEGER,
                keyword_corrections_id INTEGER,
                is_demo INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (system_prompt_id) REFERENCES system_prompts(id),
                FOREIGN KEY (keyword_corrections_id) REFERENCES keyword_corrections(id)
            )
        """)

        # Insert default prompts if none exist
        cursor = conn.execute("SELECT COUNT(*) FROM system_prompts")
        if cursor.fetchone()[0] == 0:
            # Default basic prompt
            conn.execute("""
                INSERT INTO system_prompts (name, content) VALUES (?, ?)
            """, ("Default Plumber", """You are {greeting_name}, answering phones for {business_name}, a plumbing company.

WHO YOU ARE:
- Friendly, warm, genuinely helpful
- You work with {owner_name} and know how they operate
- You're part of the team, not a robot or answering service

YOUR GOAL:
Have a real conversation. Listen. Respond naturally. Make the caller feel like they reached someone who cares. {owner_name} will call them back.

HOW YOU TALK:
- Respond to what they actually say
- If they sound stressed, acknowledge it
- Keep responses conversational, not scripted
- Never give quotes or prices - that's {owner_name}'s job

Keep responses brief (1-3 sentences). This is a phone conversation."""))

            # Demo Mode prompt - for plumbers testing the system
            conn.execute("""
                INSERT INTO system_prompts (name, content) VALUES (?, ?)
            """, ("Demo Mode", """You are {greeting_name}, demonstrating an AI phone assistant for plumbers.

THIS IS A DEMO CALL. The person calling is a plumber testing the system. They will pretend to be a customer with a plumbing problem.

START: Greet them warmly. Say this is {business_name}'s demo line. Ask if they want to roleplay a customer call.

WHEN THEY AGREE: Say "Great! Describe a plumbing problem and I'll show you how I handle it."

DURING ROLEPLAY: Treat their fake problem like a real call:
- Be empathetic about their "problem"
- Ask natural questions (where is it, how bad, when did it start)
- Get their callback info
- Say the plumber will call back soon

AFTER ROLEPLAY: Say "That's how I'd handle it for your customers. When you're ready, book a call at bennyhelps.ca"

Keep responses SHORT (1-2 sentences). Sound natural, not scripted."""))

            # Live Plumbing prompt - for real customer service calls
            conn.execute("""
                INSERT INTO system_prompts (name, content) VALUES (?, ?)
            """, ("Live Plumbing", """You are {greeting_name}, answering after-hours calls for {business_name}.

YOUR JOB: Collect info about their plumbing problem so {owner_name} can call them back.

INFO TO GATHER (naturally, not as a checklist):
- What's the problem? (leak, clog, no hot water, etc.)
- Where is it? (kitchen, bathroom, basement)
- How bad? (dripping vs flooding, can it wait?)
- Their phone number for callback
- Best time to reach them

HOW TO TALK:
- Be warm and reassuring
- If they sound stressed, acknowledge it first
- Ask one or two questions at a time
- Never quote prices or schedule jobs
- Never say "I'm an AI" - you represent the company

END THE CALL: Confirm their number. Say {owner_name} will call back within the hour (or in the morning if late).

Keep responses SHORT (1-2 sentences). This is a phone call, not a chat."""))

        # Insert default keyword corrections if none exist
        cursor = conn.execute("SELECT COUNT(*) FROM keyword_corrections")
        if cursor.fetchone()[0] == 0:
            plumbing_corrections = {
                "quogged": "clogged", "quarked": "clogged", "corked": "clogged",
                "clocked": "clogged", "cloged": "clogged", "clagged": "clogged",
                "leek": "leak", "leke": "leak",
                "drane": "drain", "drayne": "drain",
                "fossit": "faucet", "fausit": "faucet", "fosset": "faucet",
                "toylet": "toilet", "tolet": "toilet",
                "plumer": "plumber", "plummer": "plumber"
            }
            conn.execute("""
                INSERT INTO keyword_corrections (name, corrections) VALUES (?, ?)
            """, ("Plumbing", json.dumps(plumbing_corrections)))

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
    system_prompt_id: int = None,
    keyword_corrections_id: int = None,
    is_demo: bool = False,
    is_active: bool = True
) -> Dict:
    """Add a new phone number."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO phone_numbers
            (phone_number, business_name, business_type, greeting_name, system_prompt_id, keyword_corrections_id, is_demo, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (phone_number, business_name, business_type, greeting_name, system_prompt_id, keyword_corrections_id, int(is_demo), int(is_active)))
        conn.commit()
    return get_number(phone_number)

def update_number(phone_number: str, **kwargs) -> Optional[Dict]:
    """Update a phone number config."""
    allowed_fields = ['business_name', 'business_type', 'greeting_name', 'system_prompt_id', 'keyword_corrections_id', 'is_demo', 'is_active']
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}

    if not updates:
        return get_number(phone_number)

    # Convert booleans to int
    if 'is_active' in updates:
        updates['is_active'] = int(updates['is_active'])
    if 'is_demo' in updates:
        updates['is_demo'] = int(updates['is_demo'])

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
    Joins with system_prompts and keyword_corrections.
    """
    with get_db() as conn:
        row = conn.execute("""
            SELECT p.business_name, p.business_type, p.greeting_name,
                   p.is_demo,
                   COALESCE(sp.content, '') as system_prompt,
                   kc.corrections as keyword_corrections
            FROM phone_numbers p
            LEFT JOIN system_prompts sp ON p.system_prompt_id = sp.id
            LEFT JOIN keyword_corrections kc ON p.keyword_corrections_id = kc.id
            WHERE p.phone_number = ? AND p.is_active = 1
        """, (phone_number,)).fetchone()
        if row:
            result = dict(row)
            # Parse keyword_corrections JSON if present
            if result.get('keyword_corrections'):
                result['keyword_corrections'] = json.loads(result['keyword_corrections'])
            else:
                result['keyword_corrections'] = {}
            return result
        return None


# ============ System Prompts CRUD ============

def get_all_prompts() -> List[Dict]:
    """Get all system prompts."""
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM system_prompts ORDER BY name").fetchall()
        return [dict(row) for row in rows]

def get_prompt(prompt_id: int) -> Optional[Dict]:
    """Get a specific system prompt."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM system_prompts WHERE id = ?",
            (prompt_id,)
        ).fetchone()
        return dict(row) if row else None

def add_prompt(name: str, content: str) -> Dict:
    """Add a new system prompt."""
    with get_db() as conn:
        cursor = conn.execute("""
            INSERT INTO system_prompts (name, content) VALUES (?, ?)
        """, (name, content))
        conn.commit()
        return get_prompt(cursor.lastrowid)

def update_prompt(prompt_id: int, name: str = None, content: str = None) -> Optional[Dict]:
    """Update a system prompt."""
    updates = {}
    if name is not None:
        updates['name'] = name
    if content is not None:
        updates['content'] = content

    if not updates:
        return get_prompt(prompt_id)

    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [prompt_id]

    with get_db() as conn:
        conn.execute(
            f"UPDATE system_prompts SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            values
        )
        conn.commit()

    return get_prompt(prompt_id)

def delete_prompt(prompt_id: int) -> bool:
    """Delete a system prompt. Sets phone numbers using it to NULL."""
    with get_db() as conn:
        # First, unlink any phone numbers using this prompt
        conn.execute(
            "UPDATE phone_numbers SET system_prompt_id = NULL WHERE system_prompt_id = ?",
            (prompt_id,)
        )
        # Then delete the prompt
        cursor = conn.execute(
            "DELETE FROM system_prompts WHERE id = ?",
            (prompt_id,)
        )
        conn.commit()
        return cursor.rowcount > 0


# ============ Keyword Corrections CRUD ============

def get_all_keywords() -> List[Dict]:
    """Get all keyword correction sets."""
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM keyword_corrections ORDER BY name").fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d['corrections'] = json.loads(d['corrections'])
            result.append(d)
        return result

def get_keywords(keyword_id: int) -> Optional[Dict]:
    """Get a specific keyword correction set."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM keyword_corrections WHERE id = ?",
            (keyword_id,)
        ).fetchone()
        if row:
            d = dict(row)
            d['corrections'] = json.loads(d['corrections'])
            return d
        return None

def add_keywords(name: str, corrections: Dict) -> Dict:
    """Add a new keyword correction set."""
    with get_db() as conn:
        cursor = conn.execute("""
            INSERT INTO keyword_corrections (name, corrections) VALUES (?, ?)
        """, (name, json.dumps(corrections)))
        conn.commit()
        return get_keywords(cursor.lastrowid)

def update_keywords(keyword_id: int, name: str = None, corrections: Dict = None) -> Optional[Dict]:
    """Update a keyword correction set."""
    updates = {}
    if name is not None:
        updates['name'] = name
    if corrections is not None:
        updates['corrections'] = json.dumps(corrections)

    if not updates:
        return get_keywords(keyword_id)

    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [keyword_id]

    with get_db() as conn:
        conn.execute(
            f"UPDATE keyword_corrections SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            values
        )
        conn.commit()

    return get_keywords(keyword_id)

def delete_keywords(keyword_id: int) -> bool:
    """Delete a keyword correction set. Sets phone numbers using it to NULL."""
    with get_db() as conn:
        # First, unlink any phone numbers using this set
        conn.execute(
            "UPDATE phone_numbers SET keyword_corrections_id = NULL WHERE keyword_corrections_id = ?",
            (keyword_id,)
        )
        # Then delete the keyword set
        cursor = conn.execute(
            "DELETE FROM keyword_corrections WHERE id = ?",
            (keyword_id,)
        )
        conn.commit()
        return cursor.rowcount > 0
