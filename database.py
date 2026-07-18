"""
TheraTrak Pro ΓÇô Database layer (SQLite)
"""
import sqlite3
import hashlib
import hmac
import secrets
from pathlib import Path
from datetime import date

from app_paths import DB_FILE

DB_PATH = DB_FILE


# ΓöÇΓöÇΓöÇ Connection ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


# ΓöÇΓöÇΓöÇ Schema ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

def initialize_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS patients (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        last_name        TEXT NOT NULL,
        first_name       TEXT NOT NULL,
        middle_name      TEXT DEFAULT '',
        dob              TEXT DEFAULT '',
        sex              TEXT DEFAULT 'U',
        ssn              TEXT DEFAULT '',
        address          TEXT DEFAULT '',
        address2         TEXT DEFAULT '',
        city             TEXT DEFAULT '',
        state            TEXT DEFAULT '',
        zip              TEXT DEFAULT '',
        phone_home       TEXT DEFAULT '',
        phone_cell       TEXT DEFAULT '',
        phone_work       TEXT DEFAULT '',
        email            TEXT DEFAULT '',
        ins_name         TEXT DEFAULT '',
        ins_id           TEXT DEFAULT '',
        ins_group        TEXT DEFAULT '',
        ins_plan         TEXT DEFAULT '',
        ins_holder       TEXT DEFAULT '',
        ins_holder_dob   TEXT DEFAULT '',
        ins_holder_sex   TEXT DEFAULT '',
        ins_relation     TEXT DEFAULT 'Self',
        ins_address      TEXT DEFAULT '',
        ins_city         TEXT DEFAULT '',
        ins_state        TEXT DEFAULT '',
        ins_zip          TEXT DEFAULT '',
        ins_phone        TEXT DEFAULT '',
        ins2_name        TEXT DEFAULT '',
        ins2_id          TEXT DEFAULT '',
        ins2_group       TEXT DEFAULT '',
        ins2_plan        TEXT DEFAULT '',
        ins2_holder      TEXT DEFAULT '',
        ins2_relation    TEXT DEFAULT '',
        dx1              TEXT DEFAULT '',
        dx2              TEXT DEFAULT '',
        dx3              TEXT DEFAULT '',
        dx4              TEXT DEFAULT '',
        dx5              TEXT DEFAULT '',
        dx6              TEXT DEFAULT '',
        dx7              TEXT DEFAULT '',
        dx8              TEXT DEFAULT '',
        dx9              TEXT DEFAULT '',
        dx10             TEXT DEFAULT '',
        dx11             TEXT DEFAULT '',
        dx12             TEXT DEFAULT '',
        emr_name         TEXT DEFAULT '',
        emr_relation     TEXT DEFAULT '',
        emr_phone        TEXT DEFAULT '',
        referring_name   TEXT DEFAULT '',
        referring_taxonomy TEXT DEFAULT '',
        referring_npi    TEXT DEFAULT '',
        illness_date     TEXT DEFAULT '',
        illness_date_qual TEXT DEFAULT '',
        other_date       TEXT DEFAULT '',
        other_date_qual  TEXT DEFAULT '',
        intake_date      TEXT DEFAULT '',
        sig_on_file_date TEXT DEFAULT '',
        status           TEXT DEFAULT 'Active',
        notes            TEXT DEFAULT '',
        created_at       TEXT DEFAULT (datetime('now')),
        updated_at       TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS session_notes (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id       INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
        session_date     TEXT NOT NULL,
        start_time       TEXT DEFAULT '',
        end_time         TEXT DEFAULT '',
        duration         INTEGER DEFAULT 50,
        session_type     TEXT DEFAULT 'Individual',
        place_of_service TEXT DEFAULT '11',
        cpt_code         TEXT DEFAULT '90834',
        cpt_modifier     TEXT DEFAULT '',
        dx1              TEXT DEFAULT '',
        dx2              TEXT DEFAULT '',
        dx3              TEXT DEFAULT '',
        dx4              TEXT DEFAULT '',
        dx5              TEXT DEFAULT '',
        dx6              TEXT DEFAULT '',
        dx7              TEXT DEFAULT '',
        dx8              TEXT DEFAULT '',
        dx9              TEXT DEFAULT '',
        dx10             TEXT DEFAULT '',
        dx11             TEXT DEFAULT '',
        dx12             TEXT DEFAULT '',
        fee              REAL DEFAULT 0.0,
        note_text        TEXT DEFAULT '',
        goals            TEXT DEFAULT '',
        interventions    TEXT DEFAULT '',
        response         TEXT DEFAULT '',
        plan             TEXT DEFAULT '',
        signed           INTEGER DEFAULT 0,
        signed_date      TEXT DEFAULT '',
        created_at       TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS billing_records (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id       INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
        session_id       INTEGER REFERENCES session_notes(id),
        record_date      TEXT NOT NULL,
        service_date     TEXT DEFAULT '',
        description      TEXT DEFAULT '',
        charge           REAL DEFAULT 0.0,
        payment          REAL DEFAULT 0.0,
        payment_type     TEXT DEFAULT '',
        check_number     TEXT DEFAULT '',
        ins_payment      REAL DEFAULT 0.0,
        adjustment       REAL DEFAULT 0.0,
        balance          REAL DEFAULT 0.0,
        claim_number     TEXT DEFAULT '',
        created_at       TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS provider_settings (
        id                INTEGER PRIMARY KEY DEFAULT 1,
        practice_name     TEXT DEFAULT '',
        provider_last     TEXT DEFAULT '',
        provider_first    TEXT DEFAULT '',
        provider_suffix   TEXT DEFAULT '',
        credentials       TEXT DEFAULT '',
        npi               TEXT DEFAULT '',
        tax_id            TEXT DEFAULT '',
        tax_id_type       TEXT DEFAULT 'EIN',
        upin              TEXT DEFAULT '',
        id_qualifier      TEXT DEFAULT 'ZZ',
        license_num       TEXT DEFAULT '',
        address           TEXT DEFAULT '',
        address2          TEXT DEFAULT '',
        city              TEXT DEFAULT '',
        state             TEXT DEFAULT '',
        zip               TEXT DEFAULT '',
        phone             TEXT DEFAULT '',
        fax               TEXT DEFAULT '',
        email             TEXT DEFAULT '',
        accept_assign     INTEGER DEFAULT 1,
        sig_on_file       TEXT DEFAULT 'Signature On File',
        default_pos       TEXT DEFAULT '11',
        updated_at        TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS dsm_codes (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        code             TEXT NOT NULL UNIQUE,
        description      TEXT NOT NULL,
        category         TEXT DEFAULT '',
        is_favorite      INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS users (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        username         TEXT NOT NULL UNIQUE,
        password_hash    TEXT NOT NULL,
        password_salt    TEXT NOT NULL,
        first_name       TEXT NOT NULL,
        middle_name      TEXT DEFAULT '',
        last_name        TEXT NOT NULL,
        suffix           TEXT DEFAULT '',
        email            TEXT DEFAULT '',
        phone            TEXT DEFAULT '',
        role             TEXT DEFAULT 'User',
        address          TEXT DEFAULT '',
        city             TEXT DEFAULT '',
        state            TEXT DEFAULT '',
        zip              TEXT DEFAULT '',
        license_number   TEXT DEFAULT '',
        npi_number       TEXT DEFAULT '',
        billing_address  TEXT DEFAULT '',
        billing_city     TEXT DEFAULT '',
        billing_state    TEXT DEFAULT '',
        billing_zip      TEXT DEFAULT '',
        is_active        INTEGER DEFAULT 1,
        created_at       TEXT DEFAULT (datetime('now')),
        last_login       TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS app_preferences (
        pref_key         TEXT PRIMARY KEY,
        pref_value       TEXT DEFAULT ''
    );
    """)

    conn.commit()

    # Seed provider row
    cur.execute("INSERT OR IGNORE INTO provider_settings (id) VALUES (1)")
    conn.commit()
    conn.close()

    _migrate_patients_table()
    _migrate_session_notes_table()
    _migrate_billing_records_table()
    _migrate_users_table()
    _migrate_provider_settings_table()
    _migrate_app_preferences_table()
    _migrate_cms1500_forms_log_table()
    _migrate_bookkeeping_tables()
    _migrate_appointments_table()
    _seed_dsm_codes()


def _migrate_patients_table():
    """Add any missing columns to patients (forward migration)."""
    new_columns = [
        ("sig_on_file_date", "TEXT DEFAULT ''"),
        ("referring_taxonomy", "TEXT DEFAULT ''"),
        ("illness_date", "TEXT DEFAULT ''"),
        ("illness_date_qual", "TEXT DEFAULT ''"),
        ("other_date", "TEXT DEFAULT ''"),
        ("other_date_qual", "TEXT DEFAULT ''"),
        ("dx5", "TEXT DEFAULT ''"),
        ("dx6", "TEXT DEFAULT ''"),
        ("dx7", "TEXT DEFAULT ''"),
        ("dx8", "TEXT DEFAULT ''"),
        ("dx9", "TEXT DEFAULT ''"),
        ("dx10", "TEXT DEFAULT ''"),
        ("dx11", "TEXT DEFAULT ''"),
        ("dx12", "TEXT DEFAULT ''"),
    ]
    conn = get_connection()
    cur = conn.cursor()
    existing = {row[1] for row in cur.execute("PRAGMA table_info(patients)").fetchall()}
    for col, col_def in new_columns:
        if col not in existing:
            cur.execute(f"ALTER TABLE patients ADD COLUMN {col} {col_def}")
    conn.commit()
    conn.close()


def _migrate_session_notes_table():
    """Add any missing columns to session_notes (forward migration)."""
    new_columns = [
        ("start_time", "TEXT DEFAULT ''"),
        ("end_time", "TEXT DEFAULT ''"),
        ("duration", "INTEGER DEFAULT 50"),
        ("session_type", "TEXT DEFAULT 'Individual'"),
        ("place_of_service", "TEXT DEFAULT '11'"),
        ("cpt_code", "TEXT DEFAULT '90834'"),
        ("cpt_modifier", "TEXT DEFAULT ''"),
        ("dx1", "TEXT DEFAULT ''"),
        ("dx2", "TEXT DEFAULT ''"),
        ("dx3", "TEXT DEFAULT ''"),
        ("dx4", "TEXT DEFAULT ''"),
        ("dx5", "TEXT DEFAULT ''"),
        ("dx6", "TEXT DEFAULT ''"),
        ("dx7", "TEXT DEFAULT ''"),
        ("dx8", "TEXT DEFAULT ''"),
        ("dx9", "TEXT DEFAULT ''"),
        ("dx10", "TEXT DEFAULT ''"),
        ("dx11", "TEXT DEFAULT ''"),
        ("dx12", "TEXT DEFAULT ''"),
        ("fee", "REAL DEFAULT 0.0"),
        ("note_text", "TEXT DEFAULT ''"),
        ("goals", "TEXT DEFAULT ''"),
        ("interventions", "TEXT DEFAULT ''"),
        ("response", "TEXT DEFAULT ''"),
        ("plan", "TEXT DEFAULT ''"),
        ("signed", "INTEGER DEFAULT 0"),
        ("signed_date", "TEXT DEFAULT ''"),
        ("created_at", "TEXT DEFAULT (datetime('now'))"),
    ]
    conn = get_connection()
    cur = conn.cursor()
    existing = {row[1] for row in cur.execute("PRAGMA table_info(session_notes)").fetchall()}
    for col, col_def in new_columns:
        if col not in existing:
            cur.execute(f"ALTER TABLE session_notes ADD COLUMN {col} {col_def}")
    conn.commit()
    conn.close()


def _migrate_billing_records_table():
    """Add any missing columns to billing_records (forward migration)."""
    new_columns = [
        ("session_id", "INTEGER REFERENCES session_notes(id)"),
        ("claim_number", "TEXT DEFAULT ''"),
    ]
    conn = get_connection()
    cur = conn.cursor()
    existing = {row[1] for row in cur.execute("PRAGMA table_info(billing_records)").fetchall()}
    for col, col_def in new_columns:
        if col not in existing:
            cur.execute(f"ALTER TABLE billing_records ADD COLUMN {col} {col_def}")
    conn.commit()
    conn.close()


def _migrate_users_table():
    """Add any missing columns to an existing users table (forward migration)."""
    new_columns = [
        ("email",            "TEXT DEFAULT ''"),
        ("phone",            "TEXT DEFAULT ''"),
        ("role",             "TEXT DEFAULT 'User'"),
        ("address",          "TEXT DEFAULT ''"),
        ("city",             "TEXT DEFAULT ''"),
        ("state",            "TEXT DEFAULT ''"),
        ("zip",              "TEXT DEFAULT ''"),
        ("middle_name",      "TEXT DEFAULT ''"),
        ("suffix",           "TEXT DEFAULT ''"),
        ("license_number",   "TEXT DEFAULT ''"),
        ("npi_number",       "TEXT DEFAULT ''"),
        ("billing_address",  "TEXT DEFAULT ''"),
        ("billing_city",     "TEXT DEFAULT ''"),
        ("billing_state",    "TEXT DEFAULT ''"),
        ("billing_zip",      "TEXT DEFAULT ''"),
        ("is_active",        "INTEGER DEFAULT 1"),
        ("created_at",       "TEXT DEFAULT (datetime('now'))"),
        ("last_login",       "TEXT DEFAULT ''"),
    ]
    conn = get_connection()
    cur = conn.cursor()
    existing = {row[1] for row in cur.execute("PRAGMA table_info(users)").fetchall()}
    for col, col_def in new_columns:
        if col not in existing:
            cur.execute(f"ALTER TABLE users ADD COLUMN {col} {col_def}")
    conn.commit()
    conn.close()


def _migrate_provider_settings_table():
    """Add any missing columns to provider_settings (forward migration)."""
    new_columns = [
        ("id_qualifier", "TEXT DEFAULT 'ZZ'"),
        ("provider_suffix", "TEXT DEFAULT ''"),
        ("cms_overlay_offset_x", "REAL DEFAULT 0.0"),
        ("cms_overlay_offset_y", "REAL DEFAULT 0.0"),
        ("cms_blank_offset_x", "REAL DEFAULT 0.0"),
        ("cms_blank_offset_y", "REAL DEFAULT 0.0"),
        ("cms_overlay_box_offsets", "TEXT DEFAULT '{}'"),
    ]
    conn = get_connection()
    cur = conn.cursor()
    existing = {row[1] for row in cur.execute("PRAGMA table_info(provider_settings)").fetchall()}
    for col, col_def in new_columns:
        if col not in existing:
            cur.execute(f"ALTER TABLE provider_settings ADD COLUMN {col} {col_def}")
    conn.commit()
    conn.close()


def _migrate_app_preferences_table():
    """Ensure app_preferences exists for lightweight app-wide settings."""
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_preferences (
            pref_key   TEXT PRIMARY KEY,
            pref_value TEXT DEFAULT ''
        )
        """
    )
    conn.commit()
    conn.close()


def _migrate_cms1500_forms_log_table():
    """Ensure CMS-1500 creation logs table exists for reporting."""
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cms1500_forms_log (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id     INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
            created_source TEXT DEFAULT '',
            output_path    TEXT DEFAULT '',
            created_at     TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()
    conn.close()


def get_app_preference(pref_key: str, default: str = "") -> str:
    conn = get_connection()
    row = conn.execute(
        "SELECT pref_value FROM app_preferences WHERE pref_key=?",
        (pref_key,),
    ).fetchone()
    conn.close()
    if row is None:
        return default
    return str(row["pref_value"] if row["pref_value"] is not None else default)


def set_app_preference(pref_key: str, pref_value: str):
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO app_preferences(pref_key, pref_value)
        VALUES(?, ?)
        ON CONFLICT(pref_key) DO UPDATE SET pref_value=excluded.pref_value
        """,
        (pref_key, str(pref_value or "")),
    )
    conn.commit()
    conn.close()


def _seed_dsm_codes():
    from dsm_codes import DSM_CODES
    conn = get_connection()
    cur = conn.cursor()
    count = cur.execute("SELECT COUNT(*) FROM dsm_codes").fetchone()[0]
    if count == 0:
        cur.executemany(
            "INSERT OR IGNORE INTO dsm_codes (code, description, category) VALUES (?,?,?)",
            DSM_CODES
        )
        conn.commit()
    conn.close()


# ΓöÇΓöÇΓöÇ Patients ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

def get_all_patients(status="Active"):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM patients WHERE status=? ORDER BY last_name, first_name",
        (status,)
    ).fetchall()
    conn.close()
    return rows


def search_patients(term, status="Active"):
    conn = get_connection()
    like = f"%{term}%"
    rows = conn.execute(
        """SELECT * FROM patients
           WHERE status=? AND (last_name LIKE ? OR first_name LIKE ?
                               OR phone_home LIKE ? OR phone_cell LIKE ?)
           ORDER BY last_name, first_name""",
        (status, like, like, like, like)
    ).fetchall()
    conn.close()
    return rows


def get_patient(pid):
    conn = get_connection()
    row = conn.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    conn.close()
    return row


def save_patient(data: dict):
    """Insert if no 'id', update otherwise. Returns patient id."""
    conn = get_connection()
    cur = conn.cursor()
    pid = data.pop("id", None)
    data["updated_at"] = "datetime('now')"
    cols = list(data.keys())
    vals = list(data.values())
    if pid is None:
        placeholders = ",".join(["?"] * len(cols))
        col_str = ",".join(cols)
        cur.execute(f"INSERT INTO patients ({col_str}) VALUES ({placeholders})", vals)
        pid = cur.lastrowid
    else:
        set_str = ",".join([f"{c}=?" for c in cols])
        vals.append(pid)
        cur.execute(f"UPDATE patients SET {set_str}, updated_at=datetime('now') WHERE id=?", vals)
    conn.commit()
    conn.close()
    return pid


def delete_patient(pid):
    conn = get_connection()
    conn.execute("DELETE FROM patients WHERE id=?", (pid,))
    conn.commit()
    conn.close()


def set_patient_status(pid, status):
    conn = get_connection()
    conn.execute("UPDATE patients SET status=? WHERE id=?", (status, pid))
    conn.commit()
    conn.close()


def count_patients(status="Active"):
    conn = get_connection()
    n = conn.execute("SELECT COUNT(*) FROM patients WHERE status=?", (status,)).fetchone()[0]
    conn.close()
    return n


# ΓöÇΓöÇΓöÇ Session Notes ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

def get_sessions_for_patient(pid):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM session_notes WHERE patient_id=? ORDER BY session_date DESC",
        (pid,)
    ).fetchall()
    conn.close()
    return rows


def get_unbilled_sessions_for_patient(pid):
    """Return sessions that do not yet have a linked billing record."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT s.*
           FROM session_notes s
           LEFT JOIN billing_records b ON b.session_id = s.id
           WHERE s.patient_id=? AND b.id IS NULL
           ORDER BY s.session_date DESC, s.id DESC""",
        (pid,),
    ).fetchall()
    conn.close()
    return rows


def get_sessions_by_date(session_date):
    conn = get_connection()
    rows = conn.execute(
        """SELECT s.*, p.first_name||' '||p.last_name AS patient_name
           FROM session_notes s
           JOIN patients p ON s.patient_id = p.id
           WHERE s.session_date=? ORDER BY p.last_name""",
        (session_date,)
    ).fetchall()
    conn.close()
    return rows


def get_recent_sessions(limit=20):
    conn = get_connection()
    rows = conn.execute(
        """SELECT s.*, p.first_name||' '||p.last_name AS patient_name
           FROM session_notes s
           JOIN patients p ON s.patient_id = p.id
           ORDER BY s.session_date DESC, s.id DESC LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()
    return rows


def get_session(sid):
    conn = get_connection()
    row = conn.execute("SELECT * FROM session_notes WHERE id=?", (sid,)).fetchone()
    conn.close()
    return row


def save_session(data: dict):
    payload = dict(data)
    sid = payload.pop("id", None)

    def _write_once() -> int:
        conn = get_connection()
        cur = conn.cursor()
        cols = list(payload.keys())
        vals = list(payload.values())
        if sid is None:
            placeholders = ",".join(["?"] * len(cols))
            col_str = ",".join(cols)
            cur.execute(f"INSERT INTO session_notes ({col_str}) VALUES ({placeholders})", vals)
            out_sid = cur.lastrowid
        else:
            set_str = ",".join([f"{c}=?" for c in cols])
            vals.append(sid)
            cur.execute(f"UPDATE session_notes SET {set_str} WHERE id=?", vals)
            out_sid = sid
        conn.commit()
        conn.close()
        return out_sid

    try:
        return _write_once()
    except sqlite3.OperationalError as ex:
        msg = str(ex).lower()
        if "no such column" not in msg and "has no column named" not in msg:
            raise
        _migrate_session_notes_table()
        return _write_once()


def delete_session(sid):
    conn = get_connection()
    # Keep billing history but unlink it from the session before deleting.
    conn.execute("UPDATE billing_records SET session_id=NULL WHERE session_id=?", (sid,))
    conn.execute("DELETE FROM session_notes WHERE id=?", (sid,))
    conn.commit()
    conn.close()


# ΓöÇΓöÇΓöÇ Billing ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

def get_billing_for_patient(pid):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM billing_records WHERE patient_id=? ORDER BY record_date DESC, id DESC",
        (pid,)
    ).fetchall()
    conn.close()
    return rows


def get_billing_record(rid):
    conn = get_connection()
    row = conn.execute("SELECT * FROM billing_records WHERE id=?", (rid,)).fetchone()
    conn.close()
    return row


def get_billing_record_for_session(session_id):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM billing_records WHERE session_id=? ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
    except sqlite3.OperationalError as ex:
        conn.close()
        if "no such column" in str(ex).lower() and "session_id" in str(ex).lower():
            _migrate_billing_records_table()
            conn = get_connection()
            row = conn.execute(
                "SELECT * FROM billing_records WHERE session_id=? ORDER BY id DESC LIMIT 1",
                (session_id,),
            ).fetchone()
        else:
            raise
    conn.close()
    return row


def get_patient_balance(pid):
    conn = get_connection()
    row = conn.execute(
        "SELECT SUM(charge)-SUM(payment)-SUM(ins_payment)-SUM(adjustment) AS bal FROM billing_records WHERE patient_id=?",
        (pid,)
    ).fetchone()
    conn.close()
    return round(row["bal"] or 0.0, 2)


def save_billing_record(data: dict):
    def _write_once(payload: dict):
        conn_local = get_connection()
        cur = conn_local.cursor()
        rid_local = payload.pop("id", None)
        cols_local = list(payload.keys())
        vals_local = list(payload.values())
        if rid_local is None:
            placeholders = ",".join(["?"] * len(cols_local))
            col_str = ",".join(cols_local)
            cur.execute(f"INSERT INTO billing_records ({col_str}) VALUES ({placeholders})", vals_local)
            rid_local = cur.lastrowid
        else:
            set_str = ",".join([f"{c}=?" for c in cols_local])
            vals_local.append(rid_local)
            cur.execute(f"UPDATE billing_records SET {set_str} WHERE id=?", vals_local)
        conn_local.commit()
        conn_local.close()
        return rid_local

    try:
        return _write_once(dict(data))
    except sqlite3.OperationalError as ex:
        if "no such column" in str(ex).lower() and "session_id" in str(ex).lower():
            _migrate_billing_records_table()
            return _write_once(dict(data))
        raise


def delete_billing_record(rid):
    conn = get_connection()
    conn.execute("DELETE FROM billing_records WHERE id=?", (rid,))
    conn.commit()
    conn.close()


def get_billing_summary():
    """Returns (total_charges, total_payments, total_balance) across all patients."""
    conn = get_connection()
    row = conn.execute(
        """SELECT SUM(charge) AS tc, SUM(payment)+SUM(ins_payment) AS tp,
                  SUM(charge)-SUM(payment)-SUM(ins_payment)-SUM(adjustment) AS tb
           FROM billing_records"""
    ).fetchone()
    conn.close()
    return (round(row["tc"] or 0, 2), round(row["tp"] or 0, 2), round(row["tb"] or 0, 2))


def log_cms1500_form_creation(patient_id: int, created_source: str = "", output_path: str = "") -> int:
    """Persist a CMS-1500 form creation event for reporting."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO cms1500_forms_log(patient_id, created_source, output_path)
        VALUES (?, ?, ?)
        """,
        (int(patient_id), (created_source or "").strip(), str(output_path or "")),
    )
    log_id = cur.lastrowid
    conn.commit()
    conn.close()
    return int(log_id)


def get_cms1500_form_creation_logs(limit: int = 0, created_from: str = "", created_to: str = ""):
    """Return CMS-1500 creation rows joined with patient identity."""
    conn = get_connection()
    sql = """
        SELECT l.id,
               l.patient_id,
               p.last_name,
               p.first_name,
               l.created_source,
               l.output_path,
               l.created_at
        FROM cms1500_forms_log l
        JOIN patients p ON p.id = l.patient_id
    """
    where = []
    params_list: list[object] = []
    if created_from:
        where.append("l.created_at >= ?")
        params_list.append(str(created_from))
    if created_to:
        where.append("l.created_at < ?")
        params_list.append(str(created_to))
    if where:
        sql += " WHERE " + " AND ".join(where)

    sql += " ORDER BY l.created_at DESC, l.id DESC"

    params = tuple(params_list)
    if limit and int(limit) > 0:
        sql += " LIMIT ?"
        params = params + (int(limit),)

    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as ex:
        msg = str(ex).lower()
        if "no such table" in msg and "cms1500_forms_log" in msg:
            conn.close()
            _migrate_cms1500_forms_log_table()
            conn = get_connection()
            rows = conn.execute(sql, params).fetchall()
        else:
            conn.close()
            raise
    conn.close()
    return rows


# ΓöÇΓöÇΓöÇ Provider Settings ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

def get_provider():
    conn = get_connection()
    row = conn.execute("SELECT * FROM provider_settings WHERE id=1").fetchone()
    conn.close()
    return dict(row) if row else {}


def save_provider(data: dict):
    data.pop("id", None)
    cols = list(data.keys())
    vals = list(data.values())
    set_str = ",".join([f"{c}=?" for c in cols])
    conn = get_connection()
    conn.execute(
        f"UPDATE provider_settings SET {set_str}, updated_at=datetime('now') WHERE id=1",
        vals
    )
    conn.commit()
    conn.close()


# ΓöÇΓöÇΓöÇ DSM Codes ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

def search_dsm(term):
    conn = get_connection()
    like = f"%{term}%"
    rows = conn.execute(
        "SELECT * FROM dsm_codes WHERE code LIKE ? OR description LIKE ? ORDER BY is_favorite DESC, code",
        (like, like)
    ).fetchall()
    conn.close()
    return rows


def get_all_dsm():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM dsm_codes ORDER BY is_favorite DESC, code").fetchall()
    conn.close()
    return rows


def toggle_dsm_favorite(code):
    conn = get_connection()
    conn.execute(
        "UPDATE dsm_codes SET is_favorite = CASE WHEN is_favorite=1 THEN 0 ELSE 1 END WHERE code=?",
        (code,)
    )
    conn.commit()
    conn.close()


# ΓöÇΓöÇΓöÇ Users / Authentication ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

def _hash_password(password: str, salt_hex: str) -> str:
    salt = bytes.fromhex(salt_hex)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return hashed.hex()


def _new_salt_hex() -> str:
    return secrets.token_hex(16)


def count_users() -> int:
    conn = get_connection()
    n = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return n


# ΓöÇΓöÇΓöÇ Bookkeeping ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

_BOOKKEEPING_TABLES = """
CREATE TABLE IF NOT EXISTS bookkeeping_entries (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date       TEXT NOT NULL,
    check_number     TEXT DEFAULT '',
    payee            TEXT DEFAULT '',
    memo             TEXT DEFAULT '',
    is_tax_deductible INTEGER DEFAULT 0,
    inc_client       REAL DEFAULT 0.0,
    inc_insurance    REAL DEFAULT 0.0,
    inc_other        REAL DEFAULT 0.0,
    exp_rent         REAL DEFAULT 0.0,
    exp_utilities    REAL DEFAULT 0.0,
    exp_office       REAL DEFAULT 0.0,
    exp_insurance    REAL DEFAULT 0.0,
    exp_phone        REAL DEFAULT 0.0,
    exp_professional REAL DEFAULT 0.0,
    exp_advertising  REAL DEFAULT 0.0,
    exp_misc         REAL DEFAULT 0.0,
    created_at       TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS bookkeeping_settings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    year            INTEGER NOT NULL UNIQUE,
    opening_balance REAL DEFAULT 0.0
);
"""

_APPOINTMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS appointments (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id       INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    appt_date        TEXT NOT NULL,
    appt_time        TEXT DEFAULT '',
    duration         INTEGER DEFAULT 50,
    session_type     TEXT DEFAULT 'Individual',
    status           TEXT DEFAULT 'Scheduled',
    notes            TEXT DEFAULT '',
    created_at       TEXT DEFAULT (datetime('now'))
);
"""


def _migrate_appointments_table():
    conn = get_connection()
    conn.executescript(_APPOINTMENTS_TABLE)
    conn.commit()
    conn.close()


def _migrate_bookkeeping_tables():
    conn = get_connection()
    cur = conn.cursor()
    cur.executescript(_BOOKKEEPING_TABLES)
    conn.commit()
    conn.close()


def get_bookkeeping_entries(year: int, month: int = 0):
    """Return entries for a given year.  month=0 means all months."""
    conn = get_connection()
    if month:
        month_str = f"{year}-{month:02d}"
        rows = conn.execute(
            "SELECT * FROM bookkeeping_entries WHERE strftime('%Y-%m', entry_date)=? ORDER BY entry_date, id",
            (month_str,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM bookkeeping_entries WHERE strftime('%Y', entry_date)=? ORDER BY entry_date, id",
            (str(year),)
        ).fetchall()
    conn.close()
    return rows


def save_bookkeeping_entry(data: dict):
    conn = get_connection()
    cur = conn.cursor()
    eid = data.pop("id", None)
    cols = list(data.keys())
    vals = list(data.values())
    if eid is None:
        placeholders = ",".join(["?"] * len(cols))
        col_str = ",".join(cols)
        cur.execute(f"INSERT INTO bookkeeping_entries ({col_str}) VALUES ({placeholders})", vals)
        eid = cur.lastrowid
    else:
        set_str = ",".join([f"{c}=?" for c in cols])
        vals.append(eid)
        cur.execute(f"UPDATE bookkeeping_entries SET {set_str} WHERE id=?", vals)
    conn.commit()
    conn.close()
    return eid


def delete_bookkeeping_entry(eid: int):
    conn = get_connection()
    conn.execute("DELETE FROM bookkeeping_entries WHERE id=?", (eid,))
    conn.commit()
    conn.close()


def get_bookkeeping_opening_balance(year: int) -> float:
    conn = get_connection()
    row = conn.execute(
        "SELECT opening_balance FROM bookkeeping_settings WHERE year=?", (year,)
    ).fetchone()
    conn.close()
    return float(row["opening_balance"]) if row else 0.0


def save_bookkeeping_opening_balance(year: int, balance: float):
    conn = get_connection()
    conn.execute(
        "INSERT INTO bookkeeping_settings (year, opening_balance) VALUES (?,?) "
        "ON CONFLICT(year) DO UPDATE SET opening_balance=excluded.opening_balance",
        (year, balance)
    )
    conn.commit()
    conn.close()


def get_bookkeeping_annual_summary(year: int) -> dict:
    """Return column totals for the full year."""
    conn = get_connection()
    row = conn.execute(
        """SELECT
            SUM(inc_client) AS inc_client,
            SUM(inc_insurance) AS inc_insurance,
            SUM(inc_other) AS inc_other,
            SUM(exp_rent) AS exp_rent,
            SUM(exp_utilities) AS exp_utilities,
            SUM(exp_office) AS exp_office,
            SUM(exp_insurance) AS exp_insurance,
            SUM(exp_phone) AS exp_phone,
            SUM(exp_professional) AS exp_professional,
            SUM(exp_advertising) AS exp_advertising,
            SUM(exp_misc) AS exp_misc
           FROM bookkeeping_entries
           WHERE strftime('%Y', entry_date)=?""",
        (str(year),)
    ).fetchone()
    conn.close()
    return {k: float(row[k] or 0) for k in row.keys()} if row else {}


def get_bookkeeping_monthly_summary(year: int) -> list:
    """Return per-month totals for the year (list of dicts, one per month that has data)."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT strftime('%m', entry_date) AS month,
            SUM(inc_client) AS inc_client,
            SUM(inc_insurance) AS inc_insurance,
            SUM(inc_other) AS inc_other,
            SUM(exp_rent) AS exp_rent,
            SUM(exp_utilities) AS exp_utilities,
            SUM(exp_office) AS exp_office,
            SUM(exp_insurance) AS exp_insurance,
            SUM(exp_phone) AS exp_phone,
            SUM(exp_professional) AS exp_professional,
            SUM(exp_advertising) AS exp_advertising,
            SUM(exp_misc) AS exp_misc
           FROM bookkeeping_entries
           WHERE strftime('%Y', entry_date)=?
           GROUP BY month ORDER BY month""",
        (str(year),)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_user_by_username(username: str):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM users WHERE lower(username)=lower(?)",
        (username.strip(),)
    ).fetchone()
    conn.close()
    return row


def create_user(data: dict):
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    first_name = (data.get("first_name") or "").strip()
    last_name = (data.get("last_name") or "").strip()

    if not username or not password or not first_name or not last_name:
        raise ValueError("Username, password, first name, and last name are required.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")

    if get_user_by_username(username):
        raise ValueError("Username already exists.")

    salt_hex = _new_salt_hex()
    password_hash = _hash_password(password, salt_hex)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO users
           (username, password_hash, password_salt, first_name, middle_name, last_name, email,
                                phone, role, address, city, state, zip, license_number, npi_number,
            billing_address, billing_city, billing_state, billing_zip, is_active)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
        (
            username,
            password_hash,
            salt_hex,
            first_name,
            (data.get("middle_name") or "").strip(),
            last_name,
            (data.get("email") or "").strip(),
            (data.get("phone") or "").strip(),
            (data.get("role") or "User").strip() or "User",
            (data.get("address") or "").strip(),
            (data.get("city") or "").strip(),
            (data.get("state") or "").strip(),
            (data.get("zip") or "").strip(),
            (data.get("license_number") or "").strip(),
            (data.get("npi_number") or "").strip(),
            (data.get("billing_address") or "").strip(),
            (data.get("billing_city") or "").strip(),
            (data.get("billing_state") or "").strip(),
            (data.get("billing_zip") or "").strip(),
        )
    )
    uid = cur.lastrowid
    conn.commit()
    conn.close()
    return uid


def verify_user_credentials(username: str, password: str):
    row = get_user_by_username(username)
    if not row or not row["is_active"]:
        return None

    actual_hash = row["password_hash"] or ""
    test_hash = _hash_password(password, row["password_salt"])
    if not hmac.compare_digest(actual_hash, test_hash):
        return None

    conn = get_connection()
    conn.execute(
        "UPDATE users SET last_login=datetime('now') WHERE id=?",
        (row["id"],)
    )
    conn.commit()
    conn.close()

    conn = get_connection()
    refreshed = conn.execute("SELECT * FROM users WHERE id=?", (row["id"],)).fetchone()
    conn.close()
    return refreshed if refreshed else row


def get_all_users():
    conn = get_connection()
    try:
        _migrate_users_table()
        existing = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}

        wanted = [
            "id", "username", "first_name", "middle_name", "last_name",
            "email", "phone", "role", "address", "city", "state", "zip",
            "license_number", "npi_number",
            "billing_address", "billing_city", "billing_state", "billing_zip",
            "is_active", "created_at", "last_login",
        ]

        select_parts = []
        for col in wanted:
            if col in existing:
                select_parts.append(col)
            elif col == "is_active":
                select_parts.append("1 AS is_active")
            else:
                select_parts.append(f"'' AS {col}")

        sql = f"SELECT {', '.join(select_parts)} FROM users ORDER BY username"
        rows = conn.execute(sql).fetchall()
    finally:
        conn.close()
    return rows


def get_appointments_for_date(appt_date: str):
    """Return all appointments for a given date (YYYY-MM-DD), ordered by time."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT a.*, p.last_name, p.first_name, p.phone_cell, p.phone_home
           FROM appointments a
           JOIN patients p ON p.id = a.patient_id
           WHERE a.appt_date=?
           ORDER BY a.appt_time, a.id""",
        (appt_date,)
    ).fetchall()
    conn.close()
    return rows


def get_appointments_range(date_from: str, date_to: str):
    """Return appointments between two dates (inclusive), ordered by date then time."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT a.*, p.last_name, p.first_name, p.phone_cell, p.phone_home
           FROM appointments a
           JOIN patients p ON p.id = a.patient_id
           WHERE a.appt_date BETWEEN ? AND ?
           ORDER BY a.appt_date, a.appt_time, a.id""",
        (date_from, date_to)
    ).fetchall()
    conn.close()
    return rows


def get_upcoming_appointments(days: int = 30):
    """Return appointments from today forward for the next N days."""
    from datetime import date, timedelta
    today = date.today().isoformat()
    end = (date.today() + timedelta(days=days)).isoformat()
    return get_appointments_range(today, end)


def save_appointment(data: dict):
    """Insert or update an appointment. Returns the appointment id."""
    conn = get_connection()
    cur = conn.cursor()
    aid = data.pop("id", None)
    cols = list(data.keys())
    vals = list(data.values())
    if aid is None:
        placeholders = ",".join(["?"] * len(cols))
        col_str = ",".join(cols)
        cur.execute(f"INSERT INTO appointments ({col_str}) VALUES ({placeholders})", vals)
        aid = cur.lastrowid
    else:
        set_str = ",".join([f"{c}=?" for c in cols])
        vals.append(aid)
        cur.execute(f"UPDATE appointments SET {set_str} WHERE id=?", vals)
    conn.commit()
    conn.close()
    return aid


def delete_appointment(aid: int):
    conn = get_connection()
    conn.execute("DELETE FROM appointments WHERE id=?", (aid,))
    conn.commit()
    conn.close()


def get_appointment(aid: int):
    conn = get_connection()
    row = conn.execute("SELECT * FROM appointments WHERE id=?", (aid,)).fetchone()
    conn.close()
    return row


def update_user(uid: int, data: dict):
    """Update an existing user's profile fields. If 'password' is non-empty, reset the password hash."""
    profile_fields = [
        "first_name", "middle_name", "last_name",
        "email", "phone", "role",
        "address", "city", "state", "zip",
        "license_number", "npi_number",
        "billing_address", "billing_city", "billing_state", "billing_zip",
        "is_active",
    ]
    conn = get_connection()
    cur = conn.cursor()
    existing_row = cur.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not existing_row:
        conn.close()
        raise ValueError("User not found.")

    params = []
    for f in profile_fields:
        if f in data:
            val = data.get(f)
        else:
            val = existing_row[f]
        if f == "is_active":
            params.append(int(bool(val)))
        else:
            params.append((str(val).strip() if val is not None else ""))
    set_clause = ", ".join(f"{f}=?" for f in profile_fields)
    params.append(uid)

    cur.execute(f"UPDATE users SET {set_clause} WHERE id=?", params)

    new_pw = (data.get("password") or "").strip()
    if new_pw:
        if len(new_pw) < 8:
            conn.close()
            raise ValueError("Password must be at least 8 characters.")
        salt_hex = _new_salt_hex()
        pw_hash = _hash_password(new_pw, salt_hex)
        cur.execute(
            "UPDATE users SET password_hash=?, password_salt=? WHERE id=?",
            (pw_hash, salt_hex, uid),
        )

    conn.commit()
    conn.close()
