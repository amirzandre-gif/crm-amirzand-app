# -*- coding: utf-8 -*-
"""
CRM پویا عدالت × آرمان‌سازان — نسخه پایتون v3 (All-in-One)
Streamlit + SQLite | دو موسسه مستقل | bcrypt | Audit Log | Plotly | اعلان‌ها | بکاپ

اجرا:
    pip install streamlit pandas openpyxl bcrypt plotly
    streamlit run crm_app.py
"""

import os
import sys
import json
import shutil
import sqlite3
import hashlib
import smtplib
import ssl
from datetime import datetime, date, timedelta
from pathlib import Path
from email.message import EmailMessage

import pandas as pd
import streamlit as st

try:
    import bcrypt
    HAS_BCRYPT = True
except ImportError:
    HAS_BCRYPT = False

try:
    import plotly.express as px
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

# ═════════════════════════════════════════════
# تنظیمات
# ═════════════════════════════════════════════
BASE_DIR = Path(__file__).parent
DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "crm_data.db"))
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", BASE_DIR / "backups"))
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

INSTITUTES = {
    "arman": {"id": "arman", "name": "موسسه آرمان‌سازان", "short": "آرمان‌سازان", "icon": "🏗️"},
    "pouya": {"id": "pouya", "name": "موسسه حقوقی پویا عدالت", "short": "پویا عدالت", "icon": "⚖️"},
}

# ═════════════════════════════════════════════
# رمزنگاری
# ═════════════════════════════════════════════
def hash_pass(password: str) -> str:
    if HAS_BCRYPT:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    return "sha256$" + hashlib.sha256(("crm$" + password).encode()).hexdigest()


def verify_pass(password: str, stored: str) -> bool:
    if stored.startswith("$2") and HAS_BCRYPT:
        try:
            return bcrypt.checkpw(password.encode(), stored.encode())
        except Exception:
            return False
    if stored.startswith("sha256$"):
        return stored == "sha256$" + hashlib.sha256(("crm$" + password).encode()).hexdigest()
    return stored == hashlib.sha256(password.encode()).hexdigest()


# ═════════════════════════════════════════════
# DB
# ═════════════════════════════════════════════
def get_conn():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def backup_db(tag="auto"):
    if not DB_PATH.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"crm_data_{tag}_{ts}.db"
    try:
        src = sqlite3.connect(str(DB_PATH))
        dst = sqlite3.connect(str(dest))
        with dst:
            src.backup(dst)
        dst.close(); src.close()
    except Exception:
        shutil.copy2(DB_PATH, dest)
    for old in sorted(BACKUP_DIR.glob("crm_data_*.db"))[:-20]:
        try: old.unlink()
        except Exception: pass
    return dest


def audit(conn, user, inst, action, entity, eid, detail=""):
    try:
        conn.execute(
            "INSERT INTO audit_log (ts,user_name,institute,action,entity,entity_id,detail) VALUES (?,?,?,?,?,?,?)",
            (datetime.now().isoformat(), user or "-", inst or "-", action, entity, eid, detail),
        )
    except Exception:
        pass


# ═════════════════════════════════════════════
# Init
# ═════════════════════════════════════════════
def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, pass_hash TEXT NOT NULL, name TEXT, role TEXT DEFAULT 'staff', active INTEGER DEFAULT 1)")
    c.execute("CREATE TABLE IF NOT EXISTS modules (id TEXT PRIMARY KEY, institute TEXT NOT NULL, name TEXT NOT NULL, icon TEXT, prefix TEXT, fields_json TEXT, enabled INTEGER DEFAULT 1)")
    c.execute("CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, module_id TEXT NOT NULL, institute TEXT NOT NULL, data_json TEXT, created_at TEXT, updated_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS reminders (id INTEGER PRIMARY KEY AUTOINCREMENT, institute TEXT, title TEXT, due_date TEXT, phone TEXT, module_id TEXT, record_id TEXT, text TEXT, status TEXT DEFAULT 'active', user_name TEXT, created_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS settings (institute TEXT PRIMARY KEY, company_name TEXT, theme TEXT DEFAULT 'dark', custom_colors TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, user_name TEXT, institute TEXT, action TEXT, entity TEXT, entity_id TEXT, detail TEXT)")

    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        c.executemany(
            "INSERT INTO users (username,pass_hash,name,role) VALUES (?,?,?,?)",
            [
                ("admin", hash_pass("admin123"), "مدیر", "admin"),
                ("manager", hash_pass("manager123"), "مدیر عملیات", "manager"),
                ("staff", hash_pass("staff123"), "کارمند", "staff"),
                ("viewer", hash_pass("viewer123"), "مشاهده‌گر", "readonly"),
            ],
        )

    for inst in INSTITUTES:
        c.execute("SELECT COUNT(*) FROM modules WHERE institute=?", (inst,))
        if c.fetchone()[0] == 0:
            for m in _default_modules(inst):
                c.execute(
                    "INSERT INTO modules (id,institute,name,icon,prefix,fields_json) VALUES (?,?,?,?,?,?)",
                    (f"{inst}_{m['id']}", inst, m["name"], m["icon"], m["prefix"], json.dumps(m["fields"], ensure_ascii=False)),
                )
        c.execute("INSERT OR IGNORE INTO settings (institute,company_name,theme) VALUES (?,?,?)", (inst, INSTITUTES[inst]["name"], "dark"))

    conn.commit(); conn.close()


def _default_modules(inst):
    if inst == "arman":
        return [
            {"id": "marketing", "name": "بازاریابی", "icon": "📣", "prefix": "MK", "fields": [
                {"id": "title", "label": "عنوان کمپین", "type": "text"},
                {"id": "channel", "label": "کانال", "type": "select", "options": ["اینستاگرام", "سایت", "دیوار", "معرفی", "تماس سرد", "سایر"]},
                {"id": "budget", "label": "بودجه", "type": "number"},
                {"id": "start", "label": "شروع", "type": "date"},
                {"id": "end", "label": "پایان", "type": "date"},
                {"id": "status", "label": "وضعیت", "type": "select", "options": ["برنامه‌ریزی", "در حال اجرا", "پایان‌یافته", "لغو"]},
                {"id": "result", "label": "نتیجه", "type": "textarea"},
            ]},
            {"id": "leads", "name": "سرنخ‌ها", "icon": "🎯", "prefix": "LD", "fields": [
                {"id": "name", "label": "نام", "type": "text"},
                {"id": "phone", "label": "تلفن", "type": "text"},
                {"id": "source", "label": "منبع", "type": "select", "options": ["بازاریابی", "معرفی", "سایت", "تماس", "سایر"]},
                {"id": "need", "label": "نیاز", "type": "text"},
                {"id": "amount", "label": "مبلغ", "type": "number"},
                {"id": "stage", "label": "مرحله", "type": "select", "options": ["جدید", "تماس اولیه", "مشاوره", "پیشنهاد", "مذاکره", "برنده", "بازنده"]},
                {"id": "owner", "label": "مسئول", "type": "text"},
                {"id": "followUp", "label": "پیگیری", "type": "date"},
            ]},
            {"id": "projects", "name": "پروژه‌ها", "icon": "🏗️", "prefix": "PRJ", "fields": [
                {"id": "title", "label": "عنوان پروژه", "type": "text"},
                {"id": "client", "label": "کارفرما", "type": "text"},
                {"id": "type", "label": "نوع", "type": "select", "options": ["مسکونی", "تجاری", "اداری", "صنعتی", "سایر"]},
                {"id": "location", "label": "موقعیت", "type": "text"},
                {"id": "budget", "label": "بودجه", "type": "number"},
                {"id": "start", "label": "شروع", "type": "date"},
                {"id": "end", "label": "پایان", "type": "date"},
                {"id": "status", "label": "وضعیت", "type": "select", "options": ["برنامه‌ریزی", "در حال اجرا", "متوقف", "تحویل", "لغو"]},
                {"id": "manager", "label": "مدیر پروژه", "type": "text"},
            ]},
            {"id": "contracts", "name": "قراردادها", "icon": "📜", "prefix": "CTR", "fields": [
                {"id": "title", "label": "عنوان", "type": "text"},
                {"id": "party", "label": "طرف قرارداد", "type": "text"},
                {"id": "amount", "label": "مبلغ", "type": "number"},
                {"id": "date", "label": "تاریخ", "type": "date"},
                {"id": "status", "label": "وضعیت", "type": "select", "options": ["پیش‌نویس", "امضا شده", "در حال اجرا", "خاتمه", "فسخ"]},
                {"id": "desc", "label": "شرح", "type": "textarea"},
            ]},
            {"id": "invoices", "name": "فاکتورها", "icon": "🧾", "prefix": "INV", "fields": [
                {"id": "clientId", "label": "کارفرما", "type": "text"},
                {"id": "projectId", "label": "کد پروژه", "type": "text"},
                {"id": "date", "label": "تاریخ", "type": "date"},
                {"id": "amount", "label": "مبلغ", "type": "number"},
                {"id": "tax", "label": "مالیات", "type": "number"},
                {"id": "total", "label": "جمع", "type": "number"},
                {"id": "status", "label": "وضعیت", "type": "select", "options": ["صادر شده", "بخشی پرداخت", "تسویه", "باطل"]},
                {"id": "desc", "label": "شرح", "type": "textarea"},
            ]},
            {"id": "payments", "name": "پرداختی‌ها", "icon": "💰", "prefix": "PAY", "fields": [
                {"id": "invoiceId", "label": "کد فاکتور", "type": "text"},
                {"id": "date", "label": "تاریخ", "type": "date"},
                {"id": "amount", "label": "مبلغ", "type": "number"},
                {"id": "method", "label": "روش", "type": "select", "options": ["نقد", "کارت", "حواله", "چک"]},
                {"id": "ref", "label": "شماره پیگیری", "type": "text"},
                {"id": "status", "label": "وضعیت", "type": "select", "options": ["ثبت‌شده", "تأییدشده", "برگشت"]},
            ]},
        ]
    return [
        {"id": "marketing", "name": "بازاریابی", "icon": "📣", "prefix": "MK", "fields": [
            {"id": "title", "label": "عنوان کمپین", "type": "text"},
            {"id": "channel", "label": "کانال", "type": "select", "options": ["اینستاگرام", "سایت", "دیوار", "معرفی", "تماس سرد", "سایر"]},
            {"id": "budget", "label": "بودجه", "type": "number"},
            {"id": "start", "label": "شروع", "type": "date"},
            {"id": "end", "label": "پایان", "type": "date"},
            {"id": "status", "label": "وضعیت", "type": "select", "options": ["برنامه‌ریزی", "در حال اجرا", "پایان‌یافته", "لغو"]},
            {"id": "result", "label": "نتیجه", "type": "textarea"},
        ]},
        {"id": "leads", "name": "سرنخ‌ها", "icon": "🎯", "prefix": "LD", "fields": [
            {"id": "name", "label": "نام", "type": "text"},
            {"id": "phone", "label": "تلفن", "type": "text"},
            {"id": "source", "label": "منبع", "type": "select", "options": ["بازاریابی", "معرفی", "سایت", "تماس", "سایر"]},
            {"id": "need", "label": "نیاز", "type": "text"},
            {"id": "amount", "label": "مبلغ", "type": "number"},
            {"id": "stage", "label": "مرحله", "type": "select", "options": ["جدید", "تماس اولیه", "مشاوره", "پیشنهاد", "مذاکره", "برنده", "بازنده"]},
            {"id": "owner", "label": "مسئول", "type": "text"},
            {"id": "followUp", "label": "پیگیری", "type": "date"},
        ]},
        {"id": "clients", "name": "موکلین", "icon": "👥", "prefix": "CL", "fields": [
            {"id": "name", "label": "نام", "type": "text"},
            {"id": "type", "label": "نوع", "type": "select", "options": ["حقیقی", "حقوقی"]},
            {"id": "phone", "label": "تلفن", "type": "text"},
            {"id": "email", "label": "ایمیل", "type": "text"},
            {"id": "status", "label": "وضعیت", "type": "select", "options": ["فعال", "غیرفعال"]},
        ]},
        {"id": "cases", "name": "پرونده‌ها", "icon": "⚖️", "prefix": "PA", "fields": [
            {"id": "clientId", "label": "کد موکل", "type": "text"},
            {"id": "subject", "label": "موضوع", "type": "text"},
            {"id": "type", "label": "نوع", "type": "select", "options": ["کیفری", "حقوقی", "خانواده", "ملکی", "تجاری", "سایر"]},
            {"id": "lawyer", "label": "وکیل", "type": "text"},
            {"id": "status", "label": "وضعیت", "type": "select", "options": ["جدید", "در جریان", "منتظر رأی", "اجرای حکم", "مختومه"]},
            {"id": "priority", "label": "اولویت", "type": "select", "options": ["بالا", "متوسط", "پایین"]},
        ]},
        {"id": "case_tasks", "name": "وظایف پرونده", "icon": "✅", "prefix": "CTK", "fields": [
            {"id": "caseId", "label": "کد پرونده", "type": "text"},
            {"id": "title", "label": "عنوان", "type": "text"},
            {"id": "assignee", "label": "مسئول", "type": "text"},
            {"id": "due", "label": "سررسید", "type": "date"},
            {"id": "status", "label": "وضعیت", "type": "select", "options": ["جدید", "در حال انجام", "منتظر", "انجام‌شده", "لغو"]},
            {"id": "priority", "label": "اولویت", "type": "select", "options": ["بالا", "متوسط", "پایین"]},
        ]},
        {"id": "proformas", "name": "پیش‌فاکتورها", "icon": "📝", "prefix": "PF", "fields": [
            {"id": "clientId", "label": "کد موکل", "type": "text"},
            {"id": "caseId", "label": "کد پرونده", "type": "text"},
            {"id": "date", "label": "تاریخ", "type": "date"},
            {"id": "amount", "label": "مبلغ", "type": "number"},
            {"id": "tax", "label": "مالیات", "type": "number"},
            {"id": "desc", "label": "شرح", "type": "textarea"},
            {"id": "status", "label": "وضعیت", "type": "select", "options": ["پیش‌نویس", "ارسال‌شده", "تأییدشده", "ردشده", "تبدیل به فاکتور"]},
        ]},
        {"id": "invoices", "name": "فاکتورها", "icon": "🧾", "prefix": "INV", "fields": [
            {"id": "clientId", "label": "کد موکل", "type": "text"},
            {"id": "caseId", "label": "کد پرونده", "type": "text"},
            {"id": "date", "label": "تاریخ", "type": "date"},
            {"id": "amount", "label": "مبلغ", "type": "number"},
            {"id": "tax", "label": "مالیات", "type": "number"},
            {"id": "total", "label": "جمع", "type": "number"},
            {"id": "status", "label": "وضعیت", "type": "select", "options": ["صادر شده", "بخشی پرداخت", "تسویه", "باطل"]},
            {"id": "desc", "label": "شرح", "type": "textarea"},
        ]},
        {"id": "payments", "name": "پرداختی‌های مشتریان", "icon": "💰", "prefix": "PAY", "fields": [
            {"id": "invoiceId", "label": "کد فاکتور", "type": "text"},
            {"id": "clientId", "label": "کد موکل", "type": "text"},
            {"id": "date", "label": "تاریخ", "type": "date"},
            {"id": "amount", "label": "مبلغ", "type": "number"},
            {"id": "method", "label": "روش", "type": "select", "options": ["نقد", "کارت", "حواله", "چک"]},
            {"id": "ref", "label": "شماره پیگیری", "type": "text"},
            {"id": "status", "label": "وضعیت", "type": "select", "options": ["ثبت‌شده", "تأییدشده", "برگشت"]},
        ]},
        {"id": "lawyer_pay", "name": "پرداخت به وکلا", "icon": "⚖️", "prefix": "LP", "fields": [
            {"id": "lawyer", "label": "نام وکیل", "type": "text"},
            {"id": "caseId", "label": "کد پرونده", "type": "text"},
            {"id": "date", "label": "تاریخ", "type": "date"},
            {"id": "amount", "label": "مبلغ", "type": "number"},
            {"id": "type", "label": "نوع", "type": "select", "options": ["حق‌الوکاله", "پاداش", "هزینه دادرسی", "سایر"]},
            {"id": "method", "label": "روش", "type": "select", "options": ["نقد", "حواله", "چک"]},
            {"id": "status", "label": "وضعیت", "type": "select", "options": ["ثبت‌شده", "پرداخت‌شده", "لغو"]},
            {"id": "desc", "label": "توضیح", "type": "textarea"},
        ]},
    ]


# ═════════════════════════════════════════════
# helpers
# ═════════════════════════════════════════════
def login(username, password):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE username=? AND active=1", (username,)).fetchone()
    conn.close()
    if row and verify_pass(password, row["pass_hash"]):
        return dict(row)
    return None


def can_write(user): return user and user.get("role") in ("admin", "manager", "staff")
def is_admin(user): return user and user.get("role") == "admin"


@st.cache_data(ttl=30, show_spinner=False)
def get_modules(institute):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM modules WHERE institute=? AND enabled=1 ORDER BY name", (institute,)).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["fields"] = json.loads(d["fields_json"] or "[]")
        out.append(d)
    return out


@st.cache_data(ttl=15, show_spinner=False)
def count_records(institute, module_id=None):
    conn = get_conn()
    if module_id:
        n = conn.execute("SELECT COUNT(*) FROM records WHERE institute=? AND module_id=?", (institute, module_id)).fetchone()[0]
    else:
        n = conn.execute("SELECT COUNT(*) FROM records WHERE institute=?", (institute,)).fetchone()[0]
    conn.close()
    return n


def get_records(institute, module_id):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM records WHERE institute=? AND module_id=? ORDER BY id DESC", (institute, module_id)).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        data = json.loads(d["data_json"] or "{}")
        data["id"] = d["id"]
        out.append(data)
    return out


def next_record_id(conn, institute, module_id, prefix):
    row = conn.execute(
        "SELECT id FROM records WHERE institute=? AND module_id=? ORDER BY CAST(SUBSTR(id, INSTR(id,'-')+1) AS INTEGER) DESC LIMIT 1",
        (institute, module_id),
    ).fetchone()
    num = 1
    if row:
        try: num = int(row["id"].split("-")[-1]) + 1
        except Exception: num = 1
    return f"{prefix}-{num:05d}"


def clear_caches():
    get_modules.clear()
    count_records.clear()


# ═════════════════════════════════════════════
# اعلان‌ها
# ═════════════════════════════════════════════
def send_email(to, subject, body):
    host = os.getenv("SMTP_HOST"); user = os.getenv("SMTP_USER"); pwd = os.getenv("SMTP_PASSWORD")
    if not (host and user and pwd):
        print(f"[EMAIL-DRY] to={to} | {subject}\n{body}")
        return {"ok": True, "dry_run": True}
    try:
        msg = EmailMessage()
        msg["From"] = os.getenv("SMTP_SENDER", user); msg["To"] = to; msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=15) as s:
            s.ehlo()
            if os.getenv("SMTP_TLS", "1") == "1":
                s.starttls(context=ssl.create_default_context())
            s.login(user, pwd); s.send_message(msg)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def send_sms(to, message):
    provider = os.getenv("SMS_PROVIDER", "console").lower()
    api = os.getenv("SMS_API_KEY", "")
    if provider == "console" or not api:
        print(f"[SMS-DRY] to={to} | {message}")
        return {"ok": True, "dry_run": True}
    if provider == "kavenegar":
        try:
            import requests
            r = requests.post(
                f"https://api.kavenegar.com/v1/{api}/sms/send.json",
                data={"receptor": to, "sender": os.getenv("SMS_SENDER", ""), "message": message},
                timeout=15,
            )
            return {"ok": r.status_code == 200, "raw": r.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    return {"ok": False, "error": "provider ناشناخته"}


# ═════════════════════════════════════════════
# CSS
# ═════════════════════════════════════════════
def inject_css(theme="dark"):
    if theme == "light":
        bg, card, text, accent = "#f1f5f9", "#ffffff", "#0f172a", "#2563eb"
    elif theme == "arman":
        bg, card, text, accent = "#0c1222", "#1a2332", "#f1f5f9", "#0ea5e9"
    elif theme == "pouya":
        bg, card, text, accent = "#0f0a1a", "#1e1533", "#f1f5f9", "#a855f7"
    else:
        bg, card, text, accent = "#0b1120", "#1e293b", "#f1f5f9", "#3b82f6"
    st.markdown(f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;600;700&display=swap');
        html, body, [class*="css"] {{ font-family: 'Vazirmatn', Tahoma, sans-serif !important; direction: rtl; text-align: right; }}
        .stApp {{ background: {bg}; color: {text}; }}
        section[data-testid="stSidebar"] {{ background: linear-gradient(180deg, {card}, {bg}); border-left: 1px solid #334155; }}
        .stButton > button {{ border-radius: 10px; }}
        div[data-testid="stMetric"] {{ background: {card}; border: 1px solid #334155; border-radius: 12px; padding: 12px 16px; border-right: 3px solid {accent}; }}
        .block-container {{ padding-top: 1.5rem; }}
        h1, h2, h3 {{ color: {text} !important; }}
        .stDataFrame {{ direction: rtl; }}
        </style>
    """, unsafe_allow_html=True)


# ═════════════════════════════════════════════
# صفحات
# ═════════════════════════════════════════════
def page_login():
    st.markdown('<div style="text-align:center;padding:2rem 0 1rem"><h1 style="background:linear-gradient(90deg,#60a5fa,#a78bfa);-webkit-background-clip:text;-webkit-text-fill-color:transparent;font-size:1.6rem">CRM پویا عدالت × آرمان‌سازان</h1><p style="color:#94a3b8;font-size:0.85rem">نسخه پایتون v3 — All-in-One</p></div>', unsafe_allow_html=True)
    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        with st.form("login"):
            u = st.text_input("نام کاربری")
            p = st.text_input("رمز عبور", type="password")
            if st.form_submit_button("ورود", use_container_width=True):
                user = login(u.strip(), p)
                if user:
                    st.session_state.user = user
                    st.session_state.page = "select_inst"
                    st.rerun()
                else:
                    st.error("نام کاربری یا رمز اشتباه است")
        st.caption("admin / admin123")


def page_select_institute():
    st.markdown('<div style="text-align:center;padding:1.5rem 0"><h2>انتخاب موسسه</h2><p style="color:#94a3b8">هر موسسه داده‌ها و ماژول‌های مستقل دارد</p></div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    for col, (inst_id, inst) in zip((c1, c2), INSTITUTES.items()):
        with col:
            st.markdown(f'<div style="background:#1a2332;border:1px solid #334155;border-radius:16px;padding:2rem;text-align:center"><div style="font-size:3rem">{inst["icon"]}</div><h3>{inst["name"]}</h3></div>', unsafe_allow_html=True)
            if st.button(f"ورود به {inst['short']}", key=f"btn_{inst_id}", use_container_width=True):
                st.session_state.institute = inst_id
                st.session_state.page = "app"
                st.session_state.module = "dashboard"
                st.rerun()
    st.markdown("---")
    if st.button("خروج"):
        for k in list(st.session_state.keys()): del st.session_state[k]
        st.rerun()


def page_dashboard(institute, user):
    inst = INSTITUTES[institute]
    st.subheader(f"📊 داشبورد — {inst['icon']} {inst['short']}")
    mods = get_modules(institute)
    total = count_records(institute)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("ماژول‌ها", len(mods))
    k2.metric("کل رکوردها", total)

    conn = get_conn()
    amount_sum = 0.0
    for mid in ("invoices", "payments", "lawyer_pay"):
        for r in conn.execute("SELECT data_json FROM records WHERE institute=? AND module_id=?", (institute, mid)).fetchall():
            try:
                d = json.loads(r["data_json"] or "{}")
                for k in ("total", "amount"):
                    v = d.get(k)
                    if v is not None: amount_sum += float(v)
            except Exception: pass
    k3.metric("مجموع مبالغ", f"{amount_sum:,.0f}")

    today = date.today().isoformat()
    overdue = conn.execute("SELECT COUNT(*) FROM reminders WHERE institute=? AND status!='done' AND due_date<=?", (institute, today)).fetchone()[0]
    k4.metric("سررسیدشده", overdue)

    st.markdown("---")

    if HAS_PLOTLY and mods:
        st.markdown("#### 📊 توزیع رکوردها")
        df_m = pd.DataFrame([{"ماژول": f"{m['icon']} {m['name']}", "تعداد": count_records(institute, m["id"])} for m in mods])
        fig = px.bar(df_m, x="ماژول", y="تعداد", color="تعداد", color_continuous_scale="Blues", text="تعداد")
        fig.update_traces(textposition="outside")
        fig.update_layout(height=340, margin=dict(l=10, r=10, t=20, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Vazirmatn"), xaxis=dict(tickangle=-30))
        st.plotly_chart(fig, use_container_width=True)

        leads = conn.execute("SELECT data_json FROM records WHERE institute=? AND module_id='leads'", (institute,)).fetchall()
        if leads:
            stages = ["جدید", "تماس اولیه", "مشاوره", "پیشنهاد", "مذاکره", "برنده", "بازنده"]
            cnt = {s: 0 for s in stages}
            for r in leads:
                try:
                    s = json.loads(r["data_json"] or "{}").get("stage")
                    if s in cnt: cnt[s] += 1
                except Exception: pass
            fig2 = go.Figure(go.Funnel(y=list(cnt.keys()), x=list(cnt.values()), textinfo="value+percent initial", marker=dict(color="#3b82f6")))
            fig2.update_layout(height=340, margin=dict(l=10, r=10, t=30, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Vazirmatn"), title="قیف سرنخ‌ها")
            st.plotly_chart(fig2, use_container_width=True)

    rems = conn.execute("SELECT * FROM reminders WHERE institute=? AND status!='done' ORDER BY due_date LIMIT 5", (institute,)).fetchall()
    conn.close()

    if rems:
        st.markdown("#### ⏰ یادآوری‌های نزدیک")
        for r in rems:
            od = r["due_date"] and r["due_date"] <= today
            st.markdown(f"{'🔴' if od else '🟡'} **{r['title']}** — `{r['due_date']}`")


def page_module(institute, module, user):
    st.subheader(f"{module['icon']} {module['name']}")
    fields = module["fields"]
    records = get_records(institute, module["id"])

    if can_write(user):
        with st.expander("＋ افزودن / ویرایش", expanded=False):
            edit_id = st.session_state.get(f"edit_{module['id']}")
            existing = next((r for r in records if r["id"] == edit_id), {}) if edit_id else {}
            with st.form(f"form_{module['id']}"):
                vals = {}
                cols = st.columns(2)
                for i, f in enumerate(fields):
                    col = cols[i % 2]; fid = f["id"]; lbl = f["label"]; ft = f.get("type", "text"); dv = existing.get(fid, "")
                    with col:
                        if ft == "select":
                            opts = f.get("options", []); idx = opts.index(dv) if dv in opts else 0
                            vals[fid] = st.selectbox(lbl, opts, index=idx, key=f"f_{module['id']}_{fid}")
                        elif ft == "number":
                            try: n = float(dv or 0)
                            except Exception: n = 0.0
                            vals[fid] = st.number_input(lbl, value=n, key=f"f_{module['id']}_{fid}")
                        elif ft == "date":
                            try: d = date.fromisoformat(str(dv)[:10]) if dv else date.today()
                            except Exception: d = date.today()
                            vals[fid] = st.date_input(lbl, value=d, key=f"f_{module['id']}_{fid}").isoformat()
                        elif ft == "textarea":
                            vals[fid] = st.text_area(lbl, value=str(dv or ""), key=f"f_{module['id']}_{fid}")
                        else:
                            vals[fid] = st.text_input(lbl, value=str(dv or ""), key=f"f_{module['id']}_{fid}")
                if st.form_submit_button("ذخیره"):
                    conn = get_conn(); now = datetime.now().isoformat()
                    if edit_id:
                        conn.execute("UPDATE records SET data_json=?,updated_at=? WHERE id=? AND institute=?", (json.dumps(vals, ensure_ascii=False), now, edit_id, institute))
                        audit(conn, user["name"], institute, "update", module["id"], edit_id)
                        st.toast("ویرایش شد", icon="✅")
                    else:
                        rid = next_record_id(conn, institute, module["id"], module["prefix"])
                        conn.execute("INSERT INTO records (id,module_id,institute,data_json,created_at,updated_at) VALUES (?,?,?,?,?,?)", (rid, module["id"], institute, json.dumps(vals, ensure_ascii=False), now, now))
                        audit(conn, user["name"], institute, "create", module["id"], rid)
                        st.toast(f"ثبت: {rid}", icon="✅")
                    conn.commit(); conn.close(); clear_caches()
                    st.session_state.pop(f"edit_{module['id']}", None)
                    st.rerun()
            if edit_id and st.button("انصراف"):
                st.session_state.pop(f"edit_{module['id']}", None); st.rerun()

    if not records:
        st.info("رکوردی ثبت نشده"); return

    df = pd.DataFrame([{**{"کد": r["id"]}, **{f["label"]: r.get(f["id"], "—") for f in fields}} for r in records])
    st.dataframe(df, use_container_width=True, hide_index=True)

    if can_write(user):
        st.markdown("##### عملیات")
        c1, c2, c3 = st.columns(3)
        with c1: sel = st.selectbox("رکورد", [r["id"] for r in records], key=f"sel_{module['id']}")
        with c2:
            if st.button("ویرایش", key=f"ed_{module['id']}"):
                st.session_state[f"edit_{module['id']}"] = sel; st.rerun()
        with c3:
            with st.popover("حذف"):
                st.warning(f"حذف `{sel}`؟")
                if st.checkbox("مطمئنم", key=f"cf_{module['id']}"):
                    if st.button("بله", key=f"dl_{module['id']}"):
                        backup_db(f"predelete_{module['id']}")
                        conn = get_conn()
                        conn.execute("DELETE FROM records WHERE id=? AND institute=?", (sel, institute))
                        audit(conn, user["name"], institute, "delete", module["id"], sel)
                        conn.commit(); conn.close(); clear_caches()
                        st.toast("حذف شد", icon="🗑️"); st.rerun()

    st.download_button("📥 CSV", df.to_csv(index=False).encode("utf-8-sig"), file_name=f"{module['name']}_{institute}.csv", mime="text/csv")


def page_reminders(institute, user):
    st.subheader("⏰ یادآوری‌ها")
    conn = get_conn()
    rems = [dict(r) for r in conn.execute("SELECT * FROM reminders WHERE institute=? ORDER BY due_date", (institute,)).fetchall()]
    conn.close()

    if can_write(user):
        with st.expander("＋ یادآوری جدید"):
            with st.form("rem"):
                t = st.text_input("عنوان"); d = st.date_input("سررسید", value=date.today())
                ph = st.text_input("تلفن"); tx = st.text_area("متن")
                if st.form_submit_button("ذخیره") and t.strip():
                    conn = get_conn()
                    conn.execute("INSERT INTO reminders (institute,title,due_date,phone,text,status,user_name,created_at) VALUES (?,?,?,?,?,?,?,?)", (institute, t.strip(), d.isoformat(), ph.strip(), tx.strip(), "active", user["name"], datetime.now().isoformat()))
                    conn.commit(); conn.close(); st.toast("ثبت شد", icon="✅"); st.rerun()

    if not rems: st.info("خالی"); return
    today = date.today().isoformat()
    for r in rems:
        od = r["status"] != "done" and r["due_date"] and r["due_date"] <= today
        stt = "✅" if r["status"] == "done" else ("🔴" if od else "🟡")
        st.markdown(f"{stt} **{r['title']}** | `{r['due_date']}`")
        if r["text"]: st.caption(r["text"])
        if can_write(user) and r["status"] != "done":
            c1, c2 = st.columns(2)
            with c1:
                if st.button(f"✓ انجام شد #{r['id']}", key=f"dn_{r['id']}"):
                    conn = get_conn(); conn.execute("UPDATE reminders SET status='done' WHERE id=?", (r["id"],)); conn.commit(); conn.close(); st.rerun()
            with c2:
                if r["phone"] and st.button(f"📨 ارسال پیامک #{r['id']}", key=f"sm_{r['id']}"):
                    res = send_sms(r["phone"], f"🔔 {r['title']}\nسررسید: {r['due_date']}\n{r['text'] or ''}")
                    st.toast("ارسال شد" if res.get("ok") else f"خطا: {res.get('error')}", icon="📨" if res.get("ok") else "❌")


def page_theme(institute):
    st.subheader("🎨 ظاهر")
    conn = get_conn()
    row = conn.execute("SELECT * FROM settings WHERE institute=?", (institute,)).fetchone()
    conn.close()
    cur = row["theme"] if row else "dark"
    themes = [("dark", "تیره", "#0b1120"), ("light", "روشن", "#f1f5f9"), ("arman", "آرمان", "#0c1222"), ("pouya", "پویا", "#0f0a1a")]
    cols = st.columns(4)
    for i, (tid, lbl, col) in enumerate(themes):
        with cols[i]:
            st.markdown(f'<div style="background:{col};height:48px;border-radius:12px;border:2px solid {"#3b82f6" if cur==tid else "#334155"}"></div>', unsafe_allow_html=True)
            if st.button(lbl, key=f"t_{tid}", use_container_width=True):
                conn = get_conn(); conn.execute("UPDATE settings SET theme=? WHERE institute=?", (tid, institute)); conn.commit(); conn.close()
                st.toast(f"تم «{lbl}»", icon="🎨"); st.rerun()


def page_users(user):
    if not is_admin(user): st.warning("دسترسی ندارید"); return
    st.subheader("👤 کاربران")
    conn = get_conn()
    df = pd.DataFrame([dict(r) for r in conn.execute("SELECT id,username,name,role,active FROM users").fetchall()])
    conn.close()
    st.dataframe(df, use_container_width=True, hide_index=True)


def page_audit(institute, user):
    if not is_admin(user): st.warning("دسترسی ندارید"); return
    st.subheader("📝 لاگ تغییرات")
    conn = get_conn()
    rows = conn.execute("SELECT * FROM audit_log WHERE institute=? ORDER BY id DESC LIMIT 200", (institute,)).fetchall()
    conn.close()
    if rows:
        df = pd.DataFrame([dict(r) for r in rows])
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button("📥 CSV", df.to_csv(index=False).encode("utf-8-sig"), file_name=f"audit_{institute}.csv", mime="text/csv")
    else: st.info("خالی")


# ═════════════════════════════════════════════
# Sidebar + routing
# ═════════════════════════════════════════════
def render_sidebar(institute, user):
    inst = INSTITUTES[institute]
    st.sidebar.markdown("### CRM حرفه‌ای")
    st.sidebar.markdown(f"**{inst['icon']} {inst['short']}**")
    st.sidebar.caption(f"{user['name']} · {user['role']}")
    st.sidebar.markdown("---")
    mods = get_modules(institute)
    menu = {"dashboard": "📊 داشبورد", "reminders": "⏰ یادآوری‌ها"}
    for m in mods: menu[m["id"]] = f"{m['icon']} {m['name']}"
    menu["theme"] = "🎨 ظاهر"
    if is_admin(user):
        menu["users"] = "👤 کاربران"
        menu["audit"] = "📝 لاگ"
    cur = st.session_state.get("module", "dashboard")
    choice = st.sidebar.radio("منو", list(menu.keys()), format_func=lambda k: menu[k], index=list(menu.keys()).index(cur) if cur in menu else 0)
    st.session_state.module = choice

    st.sidebar.markdown("---")
    if st.sidebar.button("💾 بکاپ دستی", use_container_width=True):
        p = backup_db("manual")
        if p: st.sidebar.success(f"✓ {p.name}")
    if st.sidebar.button("🔀 تعویض موسسه", use_container_width=True):
        st.session_state.page = "select_inst"; st.session_state.pop("institute", None); st.session_state.pop("module", None); st.rerun()
    if st.sidebar.button("خروج", use_container_width=True):
        for k in list(st.session_state.keys()): del st.session_state[k]
        st.rerun()


def main_app():
    institute = st.session_state.institute
    user = st.session_state.user
    conn = get_conn()
    row = conn.execute("SELECT theme FROM settings WHERE institute=?", (institute,)).fetchone()
    conn.close()
    inject_css(row["theme"] if row else "dark")
    render_sidebar(institute, user)
    mk = st.session_state.get("module", "dashboard")
    if mk == "dashboard": page_dashboard(institute, user)
    elif mk == "reminders": page_reminders(institute, user)
    elif mk == "theme": page_theme(institute)
    elif mk == "users": page_users(user)
    elif mk == "audit": page_audit(institute, user)
    else:
        mod = next((m for m in get_modules(institute) if m["id"] == mk), None)
        if mod: page_module(institute, mod, user)
        else: st.warning("ماژول یافت نشد")


# ═════════════════════════════════════════════
# Entry
# ═════════════════════════════════════════════
def main():
    st.set_page_config(page_title="CRM پویا × آرمان", page_icon="⚖️", layout="wide", initial_sidebar_state="expanded")
    init_db()
    st.session_state.setdefault("page", "login")
    page = st.session_state.page
    if page == "login":
        inject_css("dark"); page_login()
    elif page == "select_inst":
        inject_css("dark"); page_select_institute()
    elif page == "app":
        if "user" not in st.session_state or "institute" not in st.session_state:
            st.session_state.page = "login"; st.rerun()
        main_app()
    else:
        st.session_state.page = "login"; st.rerun()


if __name__ == "__main__":
    main()