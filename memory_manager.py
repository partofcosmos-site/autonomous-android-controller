#!/usr/bin/env python3
"""
On-Device Personal Knowledge Graph & Memory Manager
===================================================
Manages an on-device SQLite database at /sdcard/agent/memory.db with automatic
fallback to local memory.db.
Provides fast semantic entity-relationship retrieval, fuzzy contact resolution,
routine storage, and mission execution history logging for mobile agents.
"""

import os
import re
import sys
import json
import sqlite3
import difflib
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

DEFAULT_DEVICE_DB = "/sdcard/agent/memory.db"
DEFAULT_LOCAL_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory.db")

# RFC 2606 and E.164-compliant mock / safe placeholders
DEFAULT_CONTACTS = [
    {
        "name": "Lakhan Pal",
        "relationship": "Maths Teacher",
        "phone": "+919999999999",
        "email": "teacher@example.com",
        "notes": "Teaches mathematics, calculus, and advanced algebra."
    },
    {
        "name": "Alex Mercer",
        "relationship": "Doctor",
        "phone": "+15550199",
        "email": "dr.mercer@example.org",
        "notes": "Primary care physician and clinic contact."
    },
    {
        "name": "Emergency Support",
        "relationship": "Emergency",
        "phone": "112",
        "email": "sos@example.net",
        "notes": "Emergency responder helpline."
    }
]

DEFAULT_ROUTINES = [
    {
        "name": "Morning Briefing",
        "trigger": "good morning",
        "actions_json": json.dumps([
            {"type": "volume", "level": "60%"},
            {"type": "brightness", "level": "70%"},
            {"type": "notifications", "filter": "alerts"}
        ]),
        "context": "Morning wake-up and daily notification summary."
    },
    {
        "name": "Study Mode",
        "trigger": "study mode",
        "actions_json": json.dumps([
            {"type": "mode", "mode": "study"}
        ]),
        "context": "Silence non-critical alerts and optimize for study focus."
    }
]

STOP_WORDS = {
    "call", "dial", "ring", "phone", "contact", "message", "text", "sms",
    "whatsapp", "email", "to", "my", "the", "a", "an", "please", "reach",
    "out", "find", "who", "is", "where", "tell", "show", "open", "launch"
}


def normalize_query(text: str) -> str:
    """Normalize text by lowering, removing punctuation, and collapsing whitespace."""
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s+]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def strip_command_noise(text: str) -> str:
    """Strip conversational commands and noise words like 'call my', 'whatsapp the'."""
    normalized = normalize_query(text)
    tokens = normalized.split()
    # Filter leading and trailing command words
    filtered = [t for t in tokens if t not in STOP_WORDS]
    if filtered:
        return " ".join(filtered)
    return normalized


def resolve_db_path(custom_path: Optional[str] = None) -> str:
    """
    Resolve SQLite database location:
    1. Explicit custom_path
    2. MEMORY_DB_PATH environment variable
    3. /sdcard/agent/memory.db (if /sdcard/agent is accessible and writable)
    4. Local repo directory memory.db
    """
    if custom_path:
        return custom_path
    env_path = os.environ.get("MEMORY_DB_PATH")
    if env_path:
        return env_path
    try:
        if os.path.exists("/sdcard/agent") and os.access("/sdcard/agent", os.W_OK):
            return DEFAULT_DEVICE_DB
    except Exception:
        pass
    return DEFAULT_LOCAL_DB


class MemoryManager:
    """On-device Personal Knowledge Graph and persistent memory manager."""

    def __init__(self, db_path: Optional[str] = None, auto_seed: bool = True):
        self.db_path = resolve_db_path(db_path)
        if self.db_path != ":memory:":
            db_dir = os.path.dirname(os.path.abspath(self.db_path))
            if db_dir and not os.path.exists(db_dir):
                try:
                    os.makedirs(db_dir, exist_ok=True)
                except Exception:
                    pass
        self._init_db()
        if auto_seed:
            self.seed_placeholders(force=False)

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def close(self) -> None:
        """Close connection resources."""
        pass

    def _init_db(self) -> None:
        """Create database tables and performance indexes."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 1. Contacts (Personal Knowledge Graph)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS contacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    relationship TEXT,
                    phone TEXT,
                    email TEXT,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_contacts_name ON contacts(name);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_contacts_rel ON contacts(relationship);")

            # 2. Routines (Compound Task Automations)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS routines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    trigger TEXT,
                    trigger_phrase TEXT,
                    actions_json TEXT NOT NULL,
                    context TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_routines_trig ON routines(trigger);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_routines_tp ON routines(trigger_phrase);")

            # 3. History (Audit Trail & Performance Metrics)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    instruction TEXT NOT NULL,
                    command TEXT,
                    status TEXT NOT NULL,
                    outcome TEXT,
                    duration_ms REAL DEFAULT 0.0
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_ts ON history(timestamp DESC);")

            # 4. Action Journal (Inverse Rollback & Step Undo)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS action_journal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    session_id TEXT,
                    forward_action TEXT NOT NULL,
                    forward_params TEXT NOT NULL,
                    inverse_action TEXT,
                    inverse_params TEXT,
                    state_before TEXT,
                    state_after TEXT,
                    rolled_back INTEGER DEFAULT 0
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_journal_ts ON action_journal(timestamp DESC);")

            # 5. Continuous Multi-Turn Chat Sessions & Turns
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    title TEXT,
                    summary TEXT
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversation_turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    turn_index INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_turns_sess ON conversation_turns(session_id, turn_index);")

            # 6. Distilled Knowledge Facts (Permanent Compressed Knowledge)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT UNIQUE,
                    category TEXT,
                    fact TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Enable WAL mode for zero-bloat, high concurrency performance
            try:
                cursor.execute("PRAGMA journal_mode=WAL;")
                cursor.execute("PRAGMA synchronous=NORMAL;")
            except Exception:
                pass
            conn.commit()

    def seed_placeholders(self, force: bool = False) -> None:
        """Pre-seed default schema with safe RFC 2606 placeholder data."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM contacts")
            contact_count = cursor.fetchone()[0]
            if contact_count == 0 or force:
                for c in DEFAULT_CONTACTS:
                    cursor.execute("""
                        INSERT INTO contacts (name, relationship, phone, email, notes)
                        VALUES (?, ?, ?, ?, ?)
                    """, (c["name"], c.get("relationship"), c.get("phone"), c.get("email"), c.get("notes")))

            cursor.execute("SELECT COUNT(*) FROM routines")
            routine_count = cursor.fetchone()[0]
            if routine_count == 0 or force:
                for r in DEFAULT_ROUTINES:
                    cursor.execute("""
                        INSERT INTO routines (name, trigger, trigger_phrase, actions_json, context)
                        VALUES (?, ?, ?, ?, ?)
                    """, (r["name"], r["trigger"], r["trigger"], r["actions_json"], r.get("context")))

            conn.commit()

    # ─── Contact Management & Fuzzy Lookup ───────────────────────────────────

    def add_contact(self, name: str, relationship: Optional[str] = None,
                    phone: Optional[str] = None, email: Optional[str] = None,
                    notes: Optional[str] = None) -> int:
        """Insert a new contact into the knowledge graph."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO contacts (name, relationship, phone, email, notes)
                VALUES (?, ?, ?, ?, ?)
            """, (name.strip(), relationship.strip() if relationship else None,
                  phone.strip() if phone else None, email.strip() if email else None,
                  notes.strip() if notes else None))
            conn.commit()
            return cursor.lastrowid

    def get_contact(self, contact_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve a contact by primary key."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_contacts(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List all contacts in the database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM contacts ORDER BY name ASC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def delete_contact(self, contact_id: int) -> bool:
        """Delete a contact by primary key."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
            conn.commit()
            return cursor.rowcount > 0

    def resolve_contact(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Fuzzy match a query (e.g. 'maths teacher', 'Lakhan Pal', 'call my doctor')
        against name, relationship, notes, phone, and email.
        Returns the top matching contact record dict, or None if confidence is low.
        """
        matches = self.resolve_contacts(query, limit=1)
        return matches[0] if matches else None

    def resolve_contacts(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Rank all contacts against the given query using multi-tiered fuzzy matching:
        - Exact matches (name, relationship) -> 98-100
        - Substring / containment -> 88-92
        - Word / token set overlap -> 80-87
        - SequenceMatcher similarity -> ratio * 75
        """
        if not query or not str(query).strip():
            return []

        raw_clean = normalize_query(str(query))
        stripped_clean = strip_command_noise(str(query))
        search_terms = list(dict.fromkeys([raw_clean, stripped_clean]))
        query_tokens = [t for t in stripped_clean.split() if len(t) > 1] or raw_clean.split()

        all_contacts = self.list_contacts(limit=500)
        scored_contacts: List[Tuple[float, Dict[str, Any]]] = []

        for contact in all_contacts:
            name = normalize_query(contact.get("name") or "")
            rel = normalize_query(contact.get("relationship") or "")
            notes = normalize_query(contact.get("notes") or "")
            phone = normalize_query(contact.get("phone") or "")
            email = normalize_query(contact.get("email") or "")
            combined = f"{name} {rel} {notes}"

            best_score = 0.0

            for term in search_terms:
                if not term:
                    continue

                # 1. Exact Match
                if term == name:
                    best_score = max(best_score, 100.0)
                elif term == rel:
                    best_score = max(best_score, 98.0)
                elif term == phone or term == email:
                    best_score = max(best_score, 95.0)

                # 2. Substring Containment
                if term in rel or (len(rel) >= 3 and rel in term):
                    best_score = max(best_score, 92.0)
                elif term in name or (len(name) >= 3 and name in term):
                    best_score = max(best_score, 90.0)
                elif term in notes:
                    best_score = max(best_score, 82.0)

            # 3. Token Overlap / Stemming
            if query_tokens:
                combined_tokens = combined.split()
                matched_tokens = 0
                for qt in query_tokens:
                    # Check exact token or prefix/suffix match (len >= 3)
                    if any(qt == ct or (len(qt) >= 3 and (ct.startswith(qt) or qt.startswith(ct)))
                           for ct in combined_tokens):
                        matched_tokens += 1

                token_ratio = matched_tokens / len(query_tokens)
                if token_ratio == 1.0:
                    # All query tokens found in record
                    if any(all(qt == rt or (len(qt) >= 3 and (rt.startswith(qt) or qt.startswith(rt)))
                               for qt in query_tokens) for rt in [rel, name]):
                        best_score = max(best_score, 88.0)
                    else:
                        best_score = max(best_score, 80.0)
                elif token_ratio > 0.0:
                    best_score = max(best_score, token_ratio * 70.0)

            # 4. SequenceMatcher Similarity (Typos / Levenshtein)
            for field_val in [name, rel]:
                if field_val:
                    ratio = difflib.SequenceMatcher(None, stripped_clean, field_val).ratio()
                    if ratio >= 0.65:
                        best_score = max(best_score, ratio * 75.0)

            # Threshold for relevance
            if best_score >= 50.0:
                contact_with_score = dict(contact)
                contact_with_score["_score"] = round(best_score, 2)
                scored_contacts.append((best_score, contact_with_score))

        # Sort descending by score
        scored_contacts.sort(key=lambda x: x[0], reverse=True)
        return [c[1] for c in scored_contacts[:limit]]

    # ─── Routines Management ─────────────────────────────────────────────────

    def add_routine(self, name: str, trigger: str, actions_json: Any,
                    context: Optional[str] = None) -> int:
        """Save an automated compound routine."""
        if isinstance(actions_json, (list, dict)):
            actions_str = json.dumps(actions_json)
        else:
            actions_str = str(actions_json)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO routines (name, trigger, trigger_phrase, actions_json, context)
                VALUES (?, ?, ?, ?, ?)
            """, (name.strip(), trigger.strip(), trigger.strip(), actions_str,
                  context.strip() if context else None))
            conn.commit()
            return cursor.lastrowid

    def get_routine(self, routine_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve a routine by primary key."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM routines WHERE id = ?", (routine_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_routines(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List all stored routines."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM routines ORDER BY id ASC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def delete_routine(self, routine_id: int) -> bool:
        """Delete a routine by primary key."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM routines WHERE id = ?", (routine_id,))
            conn.commit()
            return cursor.rowcount > 0

    def find_routine(self, trigger_phrase: str) -> Optional[Dict[str, Any]]:
        """
        Fuzzy match a user prompt against stored routine triggers.
        Returns the matching routine if found.
        """
        if not trigger_phrase or not str(trigger_phrase).strip():
            return None

        clean_input = normalize_query(trigger_phrase)
        routines = self.list_routines()

        best_match = None
        best_score = 0.0

        for r in routines:
            trig = normalize_query(r.get("trigger") or r.get("trigger_phrase") or "")
            name = normalize_query(r.get("name") or "")

            score = 0.0
            if clean_input == trig or clean_input == name:
                score = 100.0
            elif trig in clean_input or clean_input in trig:
                score = 90.0
            else:
                sim = difflib.SequenceMatcher(None, clean_input, trig).ratio()
                if sim >= 0.7:
                    score = sim * 85.0

            if score > best_score:
                best_score = score
                best_match = r

        if best_score >= 60.0:
            return best_match
        return None

    # ─── Mission History & Audit Trail ───────────────────────────────────────

    def record_history(self, instruction: str, status: str = "success",
                       duration_ms: float = 0.0) -> int:
        """Log a mission execution event."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO history (timestamp, instruction, command, status, outcome, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (datetime.now(timezone.utc).isoformat(), instruction, instruction,
                  status, status, float(duration_ms)))
            conn.commit()
            return cursor.lastrowid

    def get_recent_history(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Fetch the most recent execution history logs."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM history ORDER BY id DESC LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def clear_history(self) -> int:
        """Clear all records from the execution history table."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM history")
            conn.commit()
            return cursor.rowcount


    # ─── Action Journal & Step Rollback (Undo) ───────────────────────────────

    def record_action_journal(self, forward_action: str, forward_params: Any,
                              inverse_action: Optional[str] = None,
                              inverse_params: Optional[Any] = None,
                              state_before: Optional[Dict[str, Any]] = None,
                              state_after: Optional[Dict[str, Any]] = None,
                              session_id: Optional[str] = None) -> int:
        """Record an executed action and its inverse compensation action for rollback."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            f_params_str = json.dumps(forward_params) if not isinstance(forward_params, str) else forward_params
            inv_params_str = json.dumps(inverse_params) if inverse_params and not isinstance(inverse_params, str) else (inverse_params or "")
            sb_str = json.dumps(state_before) if state_before else ""
            sa_str = json.dumps(state_after) if state_after else ""
            cursor.execute("""
                INSERT INTO action_journal (
                    timestamp, session_id, forward_action, forward_params,
                    inverse_action, inverse_params, state_before, state_after, rolled_back
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (datetime.now(timezone.utc).isoformat(), session_id or "default",
                  forward_action, f_params_str, inverse_action or "", inv_params_str,
                  sb_str, sa_str))
            conn.commit()
            return cursor.lastrowid

    def get_last_reversible_action(self, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieve the most recent un-reverted action that has an inverse rollback."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT * FROM action_journal
                WHERE rolled_back = 0 AND inverse_action IS NOT NULL AND inverse_action != ''
            """
            params = []
            if session_id:
                query += " AND session_id = ?"
                params.append(session_id)
            query += " ORDER BY id DESC LIMIT 1"
            cursor.execute(query, params)
            row = cursor.fetchone()
            return dict(row) if row else None

    def mark_action_rolled_back(self, journal_id: int) -> bool:
        """Mark an action in the journal as rolled back."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE action_journal SET rolled_back = 1 WHERE id = ?
            """, (journal_id,))
            conn.commit()
            return cursor.rowcount > 0

    def list_recent_actions(self, limit: int = 10, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List recent action journal records."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if session_id:
                cursor.execute("SELECT * FROM action_journal WHERE session_id = ? ORDER BY id DESC LIMIT ?", (session_id, limit))
            else:
                cursor.execute("SELECT * FROM action_journal ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

    # ─── Continuous Multi-Turn Chat Sessions ─────────────────────────────────

    def create_session(self, session_id: Optional[str] = None, title: Optional[str] = None) -> str:
        """Initialize or retrieve a chat session."""
        sess_id = session_id or f"sess_{int(datetime.now(timezone.utc).timestamp())}"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO chat_sessions (session_id, title, created_at, last_active)
                VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (sess_id, title or "Autonomous Session"))
            conn.commit()
            return sess_id

    def save_turn(self, session_id: str, role: str, content: str,
                  metadata: Optional[Dict[str, Any]] = None) -> int:
        """Save a conversation turn (user prompt or agent response) to continuous memory."""
        self.create_session(session_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Calculate next turn index
            cursor.execute("SELECT COALESCE(MAX(turn_index), 0) + 1 FROM conversation_turns WHERE session_id = ?", (session_id,))
            next_idx = cursor.fetchone()[0]
            meta_str = json.dumps(metadata) if metadata else None
            cursor.execute("""
                INSERT INTO conversation_turns (session_id, turn_index, role, content, metadata_json, timestamp)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (session_id, next_idx, role, content, meta_str))
            cursor.execute("""
                UPDATE chat_sessions SET last_active = CURRENT_TIMESTAMP WHERE session_id = ?
            """, (session_id,))
            conn.commit()
            return cursor.lastrowid

    def get_session_history(self, session_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        """Retrieve recent conversation turns for continuous context."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM conversation_turns
                WHERE session_id = ?
                ORDER BY turn_index ASC
                LIMIT ?
            """, (session_id, limit))
            turns = []
            for r in cursor.fetchall():
                d = dict(r)
                if d.get("metadata_json"):
                    try:
                        d["metadata"] = json.loads(d["metadata_json"])
                    except Exception:
                        d["metadata"] = {}
                turns.append(d)
            return turns

    # ─── Semantic Fact Distillation ──────────────────────────────────────────

    def save_fact(self, key: str, fact: str, category: str = "user_preference",
                  confidence: float = 1.0) -> int:
        """Store a high-density distilled semantic fact."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO knowledge_facts (key, category, fact, confidence, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    fact = excluded.fact,
                    category = excluded.category,
                    confidence = excluded.confidence,
                    updated_at = CURRENT_TIMESTAMP
            """, (key, category, fact, confidence))
            conn.commit()
            return cursor.lastrowid

    def list_facts(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all distilled semantic knowledge facts."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if category:
                cursor.execute("SELECT * FROM knowledge_facts WHERE category = ? ORDER BY key ASC", (category,))
            else:
                cursor.execute("SELECT * FROM knowledge_facts ORDER BY category ASC, key ASC")
            return [dict(r) for r in cursor.fetchall()]

    # ─── Self-Compacting Storage Engine (25MB Hard Ceiling) ───────────────────

    def get_storage_metrics(self) -> Dict[str, Any]:
        """Compute disk usage metrics for the SQLite database."""
        if self.db_path == ":memory:" or not os.path.exists(self.db_path):
            return {"size_bytes": 0, "size_mb": 0.0, "is_memory": True}
        
        size_bytes = os.path.getsize(self.db_path)
        wal_path = f"{self.db_path}-wal"
        if os.path.exists(wal_path):
            size_bytes += os.path.getsize(wal_path)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA page_count;")
            page_count = cursor.fetchone()[0]
            cursor.execute("PRAGMA page_size;")
            page_size = cursor.fetchone()[0]

        return {
            "size_bytes": size_bytes,
            "size_mb": round(size_bytes / (1024 * 1024), 3),
            "page_count": page_count,
            "page_size": page_size,
            "is_memory": False
        }

    def check_and_compact_storage(self, max_bytes: int = 25 * 1024 * 1024,
                                   force: bool = False,
                                   retention_days: int = 30) -> Dict[str, Any]:
        """
        Enforce hard storage ceiling (< 25 MB).
        If database exceeds 80% of max_bytes (or force=True):
        1. Distill recurring routines/preferences to knowledge_facts.
        2. Prune raw verbose history and conversation turns beyond retention_days.
        3. Prune old rolled_back action journal entries.
        4. Execute VACUUM and WAL checkpoint to return disk blocks to the OS.
        """
        metrics_before = self.get_storage_metrics()
        current_size = metrics_before["size_bytes"]
        threshold = int(max_bytes * 0.8)

        if not force and current_size <= threshold:
            return {
                "compacted": False,
                "reason": "under_threshold",
                "size_bytes_before": current_size,
                "size_bytes_after": current_size,
                "max_bytes": max_bytes,
                "under_ceiling": True
            }

        # Compaction execution
        pruned_turns = 0
        pruned_history = 0
        pruned_journal = 0

        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 1. Prune conversation turns older than retention days
            cursor.execute("""
                DELETE FROM conversation_turns
                WHERE timestamp < datetime('now', '-' || ? || ' days')
            """, (retention_days,))
            pruned_turns = cursor.rowcount

            # 2. Prune old raw history
            cursor.execute("""
                DELETE FROM history
                WHERE timestamp < datetime('now', '-' || ? || ' days')
            """, (retention_days,))
            pruned_history = cursor.rowcount

            # 3. Prune old rolled_back or ancient journal entries
            cursor.execute("""
                DELETE FROM action_journal
                WHERE rolled_back = 1 OR timestamp < datetime('now', '-' || ? || ' days')
            """, (retention_days,))
            pruned_journal = cursor.rowcount
            conn.commit()

        # 4. Vacuum and reclaim disk space
        if self.db_path != ":memory:" and os.path.exists(self.db_path):
            with self._get_connection() as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                conn.execute("VACUUM;")

        metrics_after = self.get_storage_metrics()
        return {
            "compacted": True,
            "pruned_turns": pruned_turns,
            "pruned_history": pruned_history,
            "pruned_journal": pruned_journal,
            "size_bytes_before": metrics_before["size_bytes"],
            "size_bytes_after": metrics_after["size_bytes"],
            "max_bytes": max_bytes,
            "under_ceiling": metrics_after["size_bytes"] <= max_bytes
        }



# Module-level default singleton instance
_default_manager: Optional[MemoryManager] = None


def get_memory_manager(db_path: Optional[str] = None) -> MemoryManager:
    """Get or instantiate the default MemoryManager singleton."""
    global _default_manager
    if _default_manager is None or (db_path and _default_manager.db_path != db_path):
        _default_manager = MemoryManager(db_path=db_path)
    return _default_manager


def resolve_contact(query: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Convenience functional interface for contact resolution."""
    return get_memory_manager(db_path).resolve_contact(query)


def find_routine(trigger_phrase: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Convenience functional interface for routine lookup."""
    return get_memory_manager(db_path).find_routine(trigger_phrase)


def record_history(instruction: str, status: str = "success",
                   duration_ms: float = 0.0, db_path: Optional[str] = None) -> int:
    """Convenience functional interface for mission history logging."""
    return get_memory_manager(db_path).record_history(instruction, status, duration_ms)


def get_recent_history(limit: int = 5, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Convenience functional interface for recent history retrieval."""
    return get_memory_manager(db_path).get_recent_history(limit)


def clear_history(db_path: Optional[str] = None) -> int:
    """Convenience functional interface to clear execution history."""
    return get_memory_manager(db_path).clear_history()



if __name__ == "__main__":
    mm = get_memory_manager()
    print(f"Memory Manager initialized at: {mm.db_path}")
    print(f"Contacts in KG: {len(mm.list_contacts())}")
    test_query = "maths teacher"
    match = mm.resolve_contact(test_query)
    if match:
        print(f"Query '{test_query}' -> Resolved to: {match['name']} ({match['phone']}) - {match['relationship']}")
    else:
        print(f"Query '{test_query}' -> No match found.")
