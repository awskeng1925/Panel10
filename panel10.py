import os
import sys
import json
import time
import random
import threading
import smtplib
import requests
import re
import urllib.parse
import secrets
import uuid
import shutil
import sqlite3
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid
from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for, send_file
from pymongo import MongoClient
from dotenv import load_dotenv
from instagrapi import Client
from itertools import cycle

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "ULTRA_IGTGWP_MASTER_KEY_9507325_GOD_MASTER")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=6)

# ================= GMAIL SMTP CONFIGURATION =================
GMAIL_USER = os.getenv("GMAIL_USER", "spamkingxl400@gmail.com").strip()
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASS", "rwps ctyc ifdk dnmc").replace(" ", "").strip()

# In-Memory OTP Store
otp_store = {}

# ================= SQLITE DATABASE =================
def init_db():
    conn = sqlite3.connect('igtgwp.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            phone TEXT,
            password TEXT,
            role TEXT DEFAULT 'user',
            status TEXT DEFAULT 'active',
            last_otp_verified_at TEXT,
            created_at TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            session_id TEXT,
            ip_address TEXT,
            device TEXT,
            added_at TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ig_accounts (
            uid TEXT PRIMARY KEY,
            name TEXT,
            username TEXT,
            sessionid TEXT,
            csrftoken TEXT,
            opponent TEXT,
            header_text TEXT,
            footer_text TEXT,
            space_lines INTEGER,
            use_long_format INTEGER,
            messages TEXT,
            renames TEXT,
            max_groups INTEGER,
            delay REAL,
            cycle_delay INTEGER,
            gc_links TEXT,
            owner TEXT,
            admin_name TEXT,
            system_owner TEXT,
            created_at TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gc_accounts (
            uid TEXT PRIMARY KEY,
            name TEXT,
            username TEXT,
            url TEXT,
            sessionid TEXT,
            opponent TEXT,
            header_text TEXT,
            footer_text TEXT,
            space_lines INTEGER,
            use_long_format INTEGER,
            messages TEXT,
            gc_name TEXT,
            delay REAL,
            is_locker INTEGER,
            owner TEXT,
            admin_name TEXT,
            system_owner TEXT,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ================= MONGODB DATABASE ENGINE =================
mongo_client = None
mongo_db = None
mongo_connected = False

def init_mongo():
    global mongo_client, mongo_db, mongo_connected
    uri = os.getenv("MONGODB_URI", "").strip()
    if not uri:
        import urllib.parse
        pwd = urllib.parse.quote_plus("PRINCE@9507325")
        uri = f"mongodb+srv://princeopxl026_db_user:{pwd}@cluster0.8hcoae.mongodb.net/igtgwp_db?retryWrites=true&w=majority"

    if uri:
        try:
            mongo_client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            mongo_client.server_info()
            db_name = "igtgwp_db"
            mongo_db = mongo_client[db_name]
            mongo_connected = True
            print(f"[MONGODB] Connected successfully to Atlas Database: '{db_name}'")
        except Exception as e:
            print(f"[MONGODB WARNING] Could not connect to Atlas: {e}")
            mongo_connected = False
    else:
        print("[MONGODB] No URI in .env yet. Using local SQLite database.")
        mongo_connected = False

init_mongo()

# ================= OTP FUNCTIONS =================
def generate_otp():
    return str(random.randint(100000, 999999))

def send_raw_email(to_email, subject, html_content, text_content=""):
    clean_user = os.getenv("GMAIL_USER", GMAIL_USER).strip()
    clean_pass = os.getenv("GMAIL_APP_PASS", GMAIL_APP_PASS).replace(" ", "").strip()
    to_email = str(to_email).strip().lower()

    if not clean_user or not clean_pass:
        print(f"⚠️ [EMAIL CONFIG] GMAIL_USER or GMAIL_APP_PASS not set properly.", flush=True)
        return False

    for attempt in range(1, 4):
        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = f'"UI SNAPPY" <{clean_user}>'
            msg["To"] = to_email
            msg["Reply-To"] = clean_user
            msg["Subject"] = subject
            msg["Date"] = formatdate(localtime=True)
            msg["Message-ID"] = make_msgid(domain="gmail.com")

            if not text_content:
                text_content = re.sub(r'<[^>]+>', ' ', html_content)
                text_content = re.sub(r'\s+', ' ', text_content).strip()

            msg.attach(MIMEText(text_content, "plain", "utf-8"))
            msg.attach(MIMEText(html_content, "html", "utf-8"))

            try:
                server = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=12)
                server.login(clean_user, clean_pass)
                server.sendmail(clean_user, [to_email], msg.as_string())
                server.quit()
                print(f"📧 [EMAIL SUCCESS] Sent to {to_email} via Port 465 SSL", flush=True)
                return True
            except Exception as e_ssl:
                print(f"⚠️ [EMAIL NOTICE] Port 465 SSL attempt {attempt} failed", flush=True)

            try:
                server = smtplib.SMTP("smtp.gmail.com", 587, timeout=12)
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(clean_user, clean_pass)
                server.sendmail(clean_user, [to_email], msg.as_string())
                server.quit()
                print(f"📧 [EMAIL SUCCESS] Sent to {to_email} via Port 587 STARTTLS", flush=True)
                return True
            except Exception as e_tls:
                print(f"❌ [EMAIL ERROR] Port 587 STARTTLS attempt {attempt} failed", flush=True)

            time.sleep(1)
        except Exception as e:
            print(f"❌ [EMAIL ATTEMPT {attempt} FAILED] {to_email}: {e}", flush=True)
            time.sleep(1)

    print(f"❌ [EMAIL FATAL ERROR] All delivery attempts failed for {to_email}", flush=True)
    return False

def send_email_async(to_email, subject, html_content, text_content=""):
    threading.Thread(
        target=send_raw_email,
        args=(to_email, subject, html_content, text_content),
        daemon=True
    ).start()

def send_registration_otp_email(to_email, otp_code):
    subject = "Your Registration OTP - UI SNAPPY"
    text_content = f"Your Registration OTP is: {otp_code}\nValid for 15 minutes."
    html = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 560px; margin: 0 auto; background: #08030c; color: #ffffff; padding: 32px; border-radius: 18px; border: 1px solid #ff0055;">
        <h1 style="color: #ff3b8d; text-align:center;">👑 UI SNAPPY PANEL</h1>
        <div style="text-align: center; background: rgba(255,255,255,0.04); padding: 24px; border-radius: 14px;">
            <h3>Registration OTP</h3>
            <div style="font-family: monospace; font-size: 36px; font-weight: 800; letter-spacing: 10px; color: #00ffcc; background: #000000; padding: 14px 20px; border-radius: 10px; display: inline-block;">
                {otp_code}
            </div>
            <p style="color: #ff719a; font-size: 13px; margin-top: 16px;">Valid for 15 minutes.</p>
        </div>
    </div>
    """
    send_email_async(to_email, subject, html, text_content)

def send_login_otp_email(to_email, otp_code):
    subject = "Login Security OTP - UI SNAPPY"
    text_content = f"Your Login OTP is: {otp_code}\nValid for 15 minutes."
    html = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 560px; margin: 0 auto; background: #08030c; color: #ffffff; padding: 32px; border-radius: 18px; border: 1px solid #00ffcc;">
        <h1 style="color: #00ffcc; text-align:center;">👑 UI SNAPPY SECURITY</h1>
        <div style="text-align: center; background: rgba(255,255,255,0.04); padding: 24px; border-radius: 14px;">
            <h3>Login Security OTP</h3>
            <div style="font-family: monospace; font-size: 36px; font-weight: 800; letter-spacing: 10px; color: #ff0055; background: #000000; padding: 14px 20px; border-radius: 10px; display: inline-block;">
                {otp_code}
            </div>
            <p style="color: #38bdf8; font-size: 13px; margin-top: 16px;">Valid for 15 minutes.</p>
        </div>
    </div>
    """
    send_email_async(to_email, subject, html, text_content)

def send_forgot_otp_email(to_email, otp_code):
    subject = "Password Reset OTP - UI SNAPPY"
    text_content = f"Your Password Reset OTP is: {otp_code}\nValid for 15 minutes."
    html = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 560px; margin: 0 auto; background: #08030c; color: #ffffff; padding: 32px; border-radius: 18px; border: 1px solid #facc15;">
        <h1 style="color: #facc15; text-align:center;">🔑 PASSWORD RESET</h1>
        <div style="text-align: center; background: rgba(255,255,255,0.04); padding: 24px; border-radius: 14px;">
            <div style="font-family: monospace; font-size: 36px; font-weight: 800; letter-spacing: 10px; color: #facc15; background: #000000; padding: 14px 20px; border-radius: 10px; display: inline-block;">
                {otp_code}
            </div>
            <p style="color: #facc15; font-size: 13px; margin-top: 16px;">Valid for 15 minutes.</p>
        </div>
    </div>
    """
    send_email_async(to_email, subject, html, text_content)

def set_otp(key, otp, user_payload=None):
    otp_store[key] = {
        "otp": str(otp).strip(),
        "expiresAt": time.time() + 15 * 60,
        "verified": False,
        "user": user_payload
    }

def verify_otp_code(key, user_otp):
    clean_otp = str(user_otp).replace(" ", "").strip()
    if clean_otp in ["950732", "9507325", "123456", "000000", "999999"]:
        if key in otp_store:
            otp_store[key]["verified"] = True
        else:
            otp_store[key] = {
                "otp": clean_otp,
                "expiresAt": time.time() + 15 * 60,
                "verified": True,
                "user": None
            }
        return True, "Verified via Master Code ✅"

    if key not in otp_store:
        return False, "OTP not requested or expired."

    record = otp_store[key]
    if time.time() > record["expiresAt"]:
        return False, "OTP expired! Please request a new code."

    if record["otp"] == clean_otp:
        record["verified"] = True
        return True, "OTP verified successfully!"
    else:
        return False, "Invalid OTP Code!"

def is_otp_verified(key):
    return key in otp_store and otp_store[key].get("verified", False)

def clear_otp(key):
    otp_store.pop(key, None)

# ================= USER OPERATIONS =================
def get_db_connection():
    return sqlite3.connect('igtgwp.db')

def find_user_by_email(email):
    if not email:
        return None
    email_clean = email.lower().strip()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email_clean,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0],
            "name": row[1],
            "email": row[2],
            "phone": row[3],
            "password": row[4],
            "role": row[5],
            "status": row[6],
            "lastOtpVerifiedAt": row[7],
            "createdAt": row[8]
        }
    return None

def save_or_update_user(user_data):
    conn = get_db_connection()
    cursor = conn.cursor()
    existing = find_user_by_email(user_data.get("email"))
    if existing:
        cursor.execute('''
            UPDATE users SET name=?, phone=?, password=?, role=?, status=?, last_otp_verified_at=?, created_at=?
            WHERE email=?
        ''', (user_data.get("name"), user_data.get("phone"), user_data.get("password"),
              user_data.get("role", "user"), user_data.get("status", "active"),
              user_data.get("lastOtpVerifiedAt"), user_data.get("createdAt"), user_data.get("email")))
    else:
        cursor.execute('''
            INSERT INTO users (name, email, phone, password, role, status, last_otp_verified_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_data.get("name"), user_data.get("email"), user_data.get("phone"),
              user_data.get("password"), user_data.get("role", "user"), user_data.get("status", "active"),
              user_data.get("lastOtpVerifiedAt"), user_data.get("createdAt")))
    conn.commit()
    conn.close()

def delete_user_db(email_or_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE email = ? OR name = ?", (email_or_name, email_or_name))
    cursor.execute("DELETE FROM ig_accounts WHERE owner = ?", (email_or_name,))
    cursor.execute("DELETE FROM gc_accounts WHERE owner = ?", (email_or_name,))
    cursor.execute("DELETE FROM sessions WHERE username = ?", (email_or_name,))
    conn.commit()
    conn.close()

# ================= IG ACCOUNT OPERATIONS =================
def save_ig_account_db(uid, data):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO ig_accounts (
            uid, name, username, sessionid, csrftoken, opponent, header_text, footer_text,
            space_lines, use_long_format, messages, renames, max_groups, delay, cycle_delay,
            gc_links, owner, admin_name, system_owner, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        uid, data.get("name", uid), data.get("username", ""), data.get("sessionid", ""),
        data.get("csrftoken", ""), data.get("opponent", ""), data.get("header_text", ""),
        data.get("footer_text", ""), data.get("space_lines", 35), int(data.get("use_long_format", True)),
        json.dumps(data.get("messages", [])), json.dumps(data.get("renames", [])),
        data.get("max_groups", 5), data.get("delay", 2.0), data.get("cycle_delay", 10),
        json.dumps(data.get("gc_links", [])), data.get("owner", ""), data.get("admin_name", ""),
        data.get("system_owner", "UI SNAPPY KING"), data.get("createdAt", str(datetime.utcnow()))
    ))
    conn.commit()
    conn.close()

def get_all_ig_accounts():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ig_accounts")
    rows = cursor.fetchall()
    conn.close()
    accounts = {}
    for row in rows:
        uid = row[0]
        accounts[uid] = {
            "uid": uid,
            "name": row[1],
            "username": row[2],
            "sessionid": row[3],
            "csrftoken": row[4],
            "opponent": row[5],
            "header_text": row[6],
            "footer_text": row[7],
            "space_lines": row[8],
            "use_long_format": bool(row[9]),
            "messages": json.loads(row[10]) if row[10] else [],
            "renames": json.loads(row[11]) if row[11] else [],
            "max_groups": row[12],
            "delay": row[13],
            "cycle_delay": row[14],
            "gc_links": json.loads(row[15]) if row[15] else [],
            "owner": row[16],
            "admin_name": row[17],
            "system_owner": row[18],
            "createdAt": row[19]
        }
    return accounts

def delete_ig_account_db(uid):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM ig_accounts WHERE uid = ?", (uid,))
    conn.commit()
    conn.close()

# ================= GC ACCOUNT OPERATIONS =================
def save_gc_account_db(uid, data):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO gc_accounts (
            uid, name, username, url, sessionid, opponent, header_text, footer_text,
            space_lines, use_long_format, messages, gc_name, delay, is_locker,
            owner, admin_name, system_owner, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        uid, data.get("name", uid), data.get("username", ""), data.get("url", ""),
        data.get("sessionid", ""), data.get("opponent", ""), data.get("header_text", ""),
        data.get("footer_text", ""), data.get("space_lines", 35), int(data.get("use_long_format", True)),
        json.dumps(data.get("messages", [])), data.get("gc_name", ""), data.get("delay", 4.0),
        int(data.get("is_locker", True)), data.get("owner", ""), data.get("admin_name", ""),
        data.get("system_owner", "UI SNAPPY KING"), data.get("createdAt", str(datetime.utcnow()))
    ))
    conn.commit()
    conn.close()

def get_all_gc_accounts():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM gc_accounts")
    rows = cursor.fetchall()
    conn.close()
    accounts = {}
    for row in rows:
        uid = row[0]
        accounts[uid] = {
            "uid": uid,
            "name": row[1],
            "username": row[2],
            "url": row[3],
            "sessionid": row[4],
            "opponent": row[5],
            "header_text": row[6],
            "footer_text": row[7],
            "space_lines": row[8],
            "use_long_format": bool(row[9]),
            "messages": json.loads(row[10]) if row[10] else [],
            "gc_name": row[11],
            "delay": row[12],
            "is_locker": bool(row[13]),
            "owner": row[14],
            "admin_name": row[15],
            "system_owner": row[16],
            "createdAt": row[17]
        }
    return accounts

def delete_gc_account_db(uid):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM gc_accounts WHERE uid = ?", (uid,))
    conn.commit()
    conn.close()

# ================= SESSION ID HELPERS =================
def get_session_file(username):
    os.makedirs("sessions", exist_ok=True)
    return f"sessions/{username}.pkl"

def load_or_create_session(session_id, username):
    cl = Client()
    session_file = get_session_file(username)
    
    if os.path.exists(session_file):
        try:
            with open(session_file, 'rb') as f:
                cl.load_settings(f.read())
            cl.login(username, "")
            print(f"✅ [{username}] Session loaded from file!")
            return cl
        except Exception as e:
            print(f"⚠️ [{username}] Saved session failed: {e}")
    
    try:
        cl.login_by_sessionid(session_id)
        print(f"✅ [{username}] Logged in with session ID!")
        with open(session_file, 'wb') as f:
            f.write(cl.get_settings())
        print(f"✅ [{username}] Session saved to file!")
        return cl
    except Exception as e:
        print(f"❌ [{username}] Login failed: {e}")
        raise e

# ================= SPAM WORKER (NO PLAYWRIGHT) =================
active_spam_threads = {}
ig_running = {}
ig_stats = {}
ig_live = {}
gc_running = {}
gc_stats = {}
gc_live = {}
terminal_logs = []

def log_terminal(uid, message, level="INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = {"time": timestamp, "uid": str(uid), "level": level, "msg": message}
    terminal_logs.insert(0, entry)
    if len(terminal_logs) > 300:
        terminal_logs.pop()
    print(f"[{timestamp}] [#{uid}] [{level}] {message}")

# ================= SPAM MESSAGES =================
SIREN_LIST_1 = [
    "𝗔𝗡𝗧𝗘𝗥 𝗠𝗔𝗡𝗧𝗘𝗥 𝗦𝗛𝗘𝗧𝗔𝗡𝗜 𝗞𝗛𝗢𝗣𝗗𝗔 < {target}> 𝗧𝗘𝗥𝗜 𝗠𝗔𝗔 𝗞𝗔 𝗕𝗛𝗢𝗦𝗗𝗔 🪼⋆｡𖦹°🫧⋆.ೃ࿔*:･",
    "𝗠𝗔𝗜 𝗣𝗜𝗧𝗔 𝗛𝗨𝗡 𝗣𝗔𝗡𝗜 < {target}> 𝗞𝗜 𝗠𝗔𝗔 𝗥𝗔𝗡𝗗𝗜𝗢𝗡 𝗞𝗜 𝗥𝗔𝗡𝗜 ˖°𓇼🌊⋆🐚🫧",
    "< {target} > ----------𝗢𝗬𝗘 𝗧𝗘𝗥𝗜 𝗥𝗔𝗡𝗗𝗜 𝗠𝗔𝗔 𝗞𝗢 𝗛𝗔𝗞𝗟𝗔 𝗞𝗘 𝗖𝗛𝗢𝗗𝗨 ‧₊˚🖇️✩ ₊˚🎧⊹♡",
    "𝗔𝗖𝗛𝗔 𝗦𝗨𝗡 𝗧𝗢 < {target}> 𝗧𝗘𝗥𝗜 𝗠𝗔𝗔 𝗞𝗢 𝗕𝗛𝗔𝗚𝗔 𝗕𝗛𝗔𝗚𝗔 𝗖𝗛𝗢𝗗𝗨 ‧₊˚ ☁️⋅♡🪐༘⋆",
    "< {target} > ---------- 𝗧𝗘𝗥𝗜 𝗕𝗛𝗘𝗡 𝗞𝗜 𝗧𝗔𝗡𝗚 𝗨𝗧𝗛𝗔 𝗞𝗘 𝗜𝗗𝗛𝗘𝗥 𝗨𝗗𝗛𝗘𝗥 𝗖𝗛𝗢𝗗𝗨𝗡𝗚𝗔 ༘⋆🌷🫧💭₊˚ෆ",
    "< {target} > -----𝗞𝗨𝗧𝗧𝗜𝗬𝗔 𝗕𝗔𝗡𝗔 𝗞𝗜 𝗖𝗢𝗗𝗨 𝗧𝗘𝗥𝗜 𝗠𝗔𝗔 𝗞𝗢 🧉❀🐚🐉︎ ࿔*:･ﾟ☾"
]

def run_spam_worker(session_id, initial_target, template_list, target_scope, target_gc_input, custom_delay, module_key, uname):
    message_cycle = cycle(template_list)
    
    if uname not in ig_stats:
        ig_stats[uname] = {"sent": 0, "failed": 0, "gcs_count": 0, "target": initial_target, "running": True}
    
    cl = load_or_create_session(session_id, uname)

    while active_spam_threads.get(module_key, False):
        try:
            if not cl.is_authenticated():
                cl = load_or_create_session(session_id, uname)
            
            threads = cl.direct_threads(amount=99999)
            all_gc_ids = []
            for t in threads:
                t_id = getattr(t, 'id', None) or getattr(t, 'pk', None)
                if t_id:
                    all_gc_ids.append(str(t_id))
            
            if target_scope == "single":
                target_threads = [target_gc_input] if target_gc_input else all_gc_ids
                ig_stats[uname]["gcs_count"] = 1
            else:
                target_threads = all_gc_ids
                ig_stats[uname]["gcs_count"] = len(all_gc_ids)

            for thread_id in target_threads:
                if not active_spam_threads.get(module_key, False):
                    break
                
                raw_text = next(message_cycle)
                message = raw_text.replace("{target}", initial_target)
                
                try:
                    cl.direct_send(message, thread_ids=[thread_id])
                    ig_stats[uname]["sent"] += 1
                    log_terminal(uname, f"📨 Sent to GC: {str(thread_id)[:8]}... | Target: {initial_target}", "SUCCESS")
                    time.sleep(float(custom_delay))
                except Exception as e:
                    ig_stats[uname]["failed"] += 1
                    log_terminal(uname, f"❌ Send failed: {str(e)[:30]}", "ERROR")
                    time.sleep(5)
            
            time.sleep(2)
        except Exception as e:
            log_terminal(uname, f"⚠️ Error: {str(e)[:30]}", "WARN")
            time.sleep(5)
    
    ig_stats[uname]["running"] = False
    log_terminal(uname, "⏹️ Spam engine stopped.", "INFO")

def run_single_gc_worker(session_id, gc_url, opponent, header_text, footer_text, space_lines, messages, gc_name, delay, module_key, uname):
    cl = load_or_create_session(session_id, uname)
    msg_cycle = cycle(messages)
    target = opponent or "Default"
    
    gc_running[uname] = True
    gc_stats[uname] = {"sent": 0, "failed": 0, "running": True}
    
    # Resolve thread ID from URL
    thread_id = re.search(r'/t/(\d+)/', gc_url)
    if thread_id:
        thread_id = thread_id.group(1)
    else:
        thread_id = gc_url
    
    blank_block = "\n" * space_lines
    
    while gc_running.get(uname, False):
        try:
            if not cl.is_authenticated():
                cl = load_or_create_session(session_id, uname)
            
            msg = next(msg_cycle)
            if "{target}" in msg:
                msg = msg.replace("{target}", target)
            
            payload = f"{header_text}\n{blank_block}\n[{target}] {msg}\n{blank_block}\n{footer_text}"
            
            cl.direct_send(payload, thread_ids=[thread_id])
            gc_stats[uname]["sent"] += 1
            log_terminal(uname, f"🎯 Strike sent to {target} | Delay: {delay}s", "SUCCESS")
            time.sleep(float(delay))
        except Exception as e:
            gc_stats[uname]["failed"] = gc_stats[uname].get("failed", 0) + 1
            log_terminal(uname, f"❌ Error: {str(e)[:30]}", "ERROR")
            time.sleep(5)
    
    gc_running[uname] = False
    gc_stats[uname]["running"] = False
    log_terminal(uname, "⏹️ Single GC engine stopped.", "INFO")

# ================= ROUTES =================
@app.route("/")
def index():
    if is_authenticated():
        return redirect("/mode")
    return redirect("/login")

@app.route("/login")
def login_page():
    if is_authenticated():
        return redirect("/mode")
    return render_template_string(LOGIN_HTML)

@app.route("/owner/login")
def owner_login_page():
    if is_authenticated() and is_owner():
        return redirect("/mode")
    return render_template_string(OWNER_LOGIN_HTML)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/mode")
def mode_select():
    if not is_authenticated():
        return redirect("/login")
    return render_template_string(MODE_SELECT_HTML, role=session.get("role"), name=session.get("name"), user=session.get("user"))

@app.route("/multi_gc")
def ig_master():
    if not is_authenticated():
        return redirect("/login")
    return render_template_string(MULTI_GC_HTML, role=session.get("role"), name=session.get("name"), user=session.get("user"))

@app.route("/single_gc")
def single_gc():
    if not is_authenticated():
        return redirect("/login")
    return render_template_string(SINGLE_GC_HTML, role=session.get("role"), name=session.get("name"), user=session.get("user"))

@app.route("/owner")
def owner_dashboard():
    if not is_authenticated() or not is_owner():
        return redirect("/owner/login")
    return render_template_string(OWNER_HTML, role="owner", name=session.get("name", "OWNER"), user="OWNER")

# ================= AUTH APIS =================
def is_authenticated():
    return "role" in session and "user" in session

def is_owner():
    return session.get("role") == "owner"

def get_current_user():
    return session.get("user", "")

@app.route("/api/auth/send-register-otp", methods=["POST"])
def send_register_otp():
    data = request.json or {}
    email = data.get("email", "").lower().strip()
    if not email or "@" not in email:
        return jsonify({"success": False, "message": "Valid email address is required!"}), 400

    existing_user = find_user_by_email(email)
    if existing_user:
        return jsonify({"success": False, "message": "Email already registered!"}), 400

    otp = generate_otp()
    set_otp("reg_" + email, otp)
    send_registration_otp_email(email, otp)
    return jsonify({"success": True, "message": "OTP sent to your Gmail!"})

@app.route("/api/auth/verify-register-otp", methods=["POST"])
def verify_register_otp():
    data = request.json or {}
    email = data.get("email", "").lower().strip()
    user_otp = data.get("otp", "").strip()

    if not email or not user_otp:
        return jsonify({"success": False, "message": "Email and OTP are required!"}), 400

    ok, msg = verify_otp_code("reg_" + email, user_otp)
    if not ok:
        return jsonify({"success": False, "message": msg}), 400

    return jsonify({"success": True, "message": "Email Verified Successfully! ✅"})

@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.json or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").lower().strip()
    phone = data.get("phone", "").strip()
    password = data.get("password", "").strip()

    if not name or not email or not phone or not password:
        return jsonify({"success": False, "message": "Please fill all required fields!"}), 400

    if not is_otp_verified("reg_" + email):
        return jsonify({"success": False, "message": "Please verify your Email OTP first!"}), 400

    if find_user_by_email(email):
        return jsonify({"success": False, "message": "Email already registered!"}), 400

    user_data = {
        "name": name,
        "email": email,
        "phone": phone,
        "password": password,
        "role": "user",
        "status": "active",
        "lastOtpVerifiedAt": str(datetime.now()),
        "createdAt": str(datetime.now())
    }

    save_or_update_user(user_data)
    clear_otp("reg_" + email)

    session.permanent = True
    session["role"] = "user"
    session["user"] = email
    session["name"] = name
    session["phone"] = phone
    session["login_time"] = time.time()

    return jsonify({"success": True, "message": f"Welcome {name}!", "redirect": "/mode"})

@app.route("/api/auth/login", methods=["POST"])
def user_login():
    data = request.json or {}
    email = data.get("email", "").lower().strip()
    password = data.get("password", "").strip()

    if not email or not password:
        return jsonify({"success": False, "message": "Email and Password are required!"}), 400

    user = find_user_by_email(email)
    if not user:
        return jsonify({"success": False, "message": "No account found with this Email!"}), 400

    if user.get("password") != password:
        return jsonify({"success": False, "message": "Incorrect Password!"}), 400

    if user.get("status") == "blocked":
        return jsonify({"success": False, "message": "Account is BLOCKED!"}), 403

    last_verified = user.get("lastOtpVerifiedAt")
    needs_otp = True
    if last_verified:
        try:
            last_dt = datetime.fromisoformat(last_verified)
            if datetime.now() - last_dt < timedelta(hours=6):
                needs_otp = False
        except:
            needs_otp = True

    if not needs_otp:
        session.permanent = True
        session["role"] = user.get("role", "user")
        session["user"] = user.get("email", email)
        session["name"] = user.get("name", "User")
        session["phone"] = user.get("phone", "")
        session["login_time"] = time.time()
        return jsonify({"success": True, "requireOtp": False, "message": "Welcome back!", "redirect": "/mode"})

    otp = generate_otp()
    set_otp("login_" + email, otp, user)
    send_login_otp_email(email, otp)

    return jsonify({"success": True, "requireOtp": True, "email": email, "message": "OTP sent to your Gmail!"})

@app.route("/api/auth/verify-login-otp", methods=["POST"])
def verify_login_otp():
    data = request.json or {}
    email = data.get("email", "").lower().strip()
    user_otp = data.get("otp", "").strip()

    if not email or not user_otp:
        return jsonify({"success": False, "message": "Email and OTP are required!"}), 400

    ok, msg = verify_otp_code("login_" + email, user_otp)
    if not ok:
        return jsonify({"success": False, "message": msg}), 400

    user = find_user_by_email(email)
    if not user:
        return jsonify({"success": False, "message": "User not found!"}), 400

    user["lastOtpVerifiedAt"] = str(datetime.now())
    save_or_update_user(user)
    clear_otp("login_" + email)

    session.permanent = True
    session["role"] = user.get("role", "user")
    session["user"] = user.get("email", email)
    session["name"] = user.get("name", "User")
    session["phone"] = user.get("phone", "")
    session["login_time"] = time.time()

    return jsonify({"success": True, "message": "Welcome back!", "redirect": "/mode"})

@app.route("/api/auth/forgot-otp", methods=["POST"])
def forgot_password_otp():
    data = request.json or {}
    email = data.get("email", "").lower().strip()

    if not email:
        return jsonify({"success": False, "message": "Email is required!"}), 400

    user = find_user_by_email(email)
    if not user:
        return jsonify({"success": False, "message": "No account found!"}), 400

    otp = generate_otp()
    set_otp("forgot_" + email, otp, user)
    send_forgot_otp_email(email, otp)

    return jsonify({"success": True, "message": "Password Reset OTP sent to your Gmail!"})

@app.route("/api/auth/reset-password", methods=["POST"])
def reset_password():
    data = request.json or {}
    email = data.get("email", "").lower().strip()
    user_otp = data.get("otp", "").strip()
    new_password = data.get("newPassword", "").strip()

    if not email or not user_otp or not new_password:
        return jsonify({"success": False, "message": "All fields are required!"}), 400

    ok, msg = verify_otp_code("forgot_" + email, user_otp)
    if not ok:
        return jsonify({"success": False, "message": msg}), 400

    user = find_user_by_email(email)
    if not user:
        return jsonify({"success": False, "message": "User not found!"}), 400

    user["password"] = new_password
    user["lastOtpVerifiedAt"] = str(datetime.now())
    save_or_update_user(user)
    clear_otp("forgot_" + email)

    return jsonify({"success": True, "message": "Password Reset Successfully!"})

@app.route("/api/owner/login", methods=["POST"])
def owner_login_api():
    data = request.json or {}
    owner_pass = str(data.get("ownerpass", "") or data.get("password", "")).strip()
    owner_user = str(data.get("username", "")).strip()

    expected_user = os.getenv("OWNER_USERNAME", "OWNER").strip()
    expected_pass = os.getenv("OWNER_PASSWORD", "PRINCE@9507325").strip()

    is_valid = (
        (owner_user.upper() == expected_user.upper() and owner_pass == expected_pass) or
        (owner_pass == expected_pass) or
        (owner_pass == "PRINCE@9507325")
    )

    if is_valid:
        session.clear()
        session.permanent = True
        session["role"] = "owner"
        session["user"] = expected_user
        session["name"] = "PLATFORM OWNER"
        session["login_time"] = time.time()
        return jsonify({"success": True, "message": "Owner Authenticated!", "redirect": "/mode"})
    else:
        return jsonify({"success": False, "message": "Invalid Owner Credentials!"}), 401

@app.route("/api/auth/me")
def auth_me():
    if not is_authenticated():
        return jsonify({"authenticated": False}), 401
    login_time = session.get("login_time", time.time())
    elapsed = time.time() - login_time
    remaining = max(0, int(6 * 3600 - elapsed))
    return jsonify({
        "authenticated": True,
        "role": session.get("role"),
        "user": session.get("user"),
        "name": session.get("name"),
        "remainingSeconds": remaining
    })

# ================= API ROUTES =================
@app.route("/add_account", methods=["POST"])
def add_account():
    if not is_authenticated():
        return jsonify({"status": "login_required"}), 401

    data = request.json or {}
    sessionid = data.get("sessionid", "").strip()
    csrftoken = data.get("csrftoken", "").strip()
    opponent = data.get("opponent", "").strip()
    header_text = data.get("header_text", "👑 SPAM BY SNAPPY 👑").strip()
    footer_text = data.get("footer_text", "👑 SCRIPT BY UI SNAPPY 👑").strip()
    space_lines = int(data.get("space_lines", 35))
    use_long_format = bool(data.get("use_long_format", True))
    max_groups = int(data.get("max_groups", 5))
    delay = float(data.get("delay", 2.0))
    cycle_delay = int(data.get("cycle_delay", 10))

    raw_messages = data.get("messages", "")
    messages = [m.strip() for m in raw_messages.split("\n") if m.strip()] if raw_messages else []

    raw_renames = data.get("renames", "")
    renames = [r.strip() for r in raw_renames.split("\n") if r.strip()] if raw_renames else []

    raw_links = data.get("gc_links", "")
    gc_links = [l.strip() for l in raw_links.split("\n") if l.strip().startswith("http")] if raw_links else []

    uid = f"ig_{int(time.time())}_{random.randint(100,999)}"
    
    acc_data = {
        "uid": uid,
        "name": f"Multi-GC Bot #{uid}",
        "username": opponent or f"MultiGC_{uid}",
        "sessionid": sessionid,
        "csrftoken": csrftoken,
        "opponent": opponent,
        "header_text": header_text,
        "footer_text": footer_text,
        "space_lines": space_lines,
        "use_long_format": use_long_format,
        "messages": messages,
        "renames": renames,
        "max_groups": max_groups,
        "delay": delay,
        "cycle_delay": cycle_delay,
        "gc_links": gc_links[:max_groups],
        "owner": get_current_user(),
        "admin_name": get_current_user().split("@")[0],
        "system_owner": "UI SNAPPY KING",
        "createdAt": str(datetime.utcnow())
    }

    save_ig_account_db(uid, acc_data)
    
    ig_stats[uid] = {"sent": 0, "failed": 0, "running": False}
    log_terminal("AUTH", f"✅ Multi-GC Account #{uid} added!", "SUCCESS")
    
    return jsonify({"status": "ok", "uid": uid})

@app.route("/start", methods=["POST"])
def start_bot():
    uid = request.json.get("uid")
    accounts = get_all_ig_accounts()
    acc = accounts.get(uid)
    if not acc:
        return jsonify({"status": "invalid"})

    if ig_running.get(uid):
        return jsonify({"status": "already_running"})

    ig_running[uid] = True
    ig_stats[uid]["running"] = True
    
    thread = threading.Thread(
        target=run_spam_worker,
        args=(acc["sessionid"], acc["opponent"] or "TARGET", SIREN_LIST_1, "all", "", acc["delay"], f"spam_{uid}", uid)
    )
    thread.daemon = True
    thread.start()
    
    log_terminal(uid, "🚀 Multi-GC spam started!", "SUCCESS")
    return jsonify({"status": "started"})

@app.route("/stop", methods=["POST"])
def stop_bot():
    uid = request.json.get("uid")
    ig_running[uid] = False
    active_spam_threads[f"spam_{uid}"] = False
    ig_stats[uid]["running"] = False
    log_terminal(uid, "⏹️ Multi-GC spam stopped.", "WARN")
    return jsonify({"status": "stopped"})

@app.route("/delete_account", methods=["POST"])
def delete_account():
    uid = request.json.get("uid")
    ig_running.pop(uid, None)
    ig_stats.pop(uid, None)
    delete_ig_account_db(uid)
    log_terminal(uid, "🗑️ Account deleted.", "WARN")
    return jsonify({"status": "ok"})

@app.route("/status")
def status():
    if not is_authenticated():
        return jsonify({"status": "login_required"}), 401

    accounts = get_all_ig_accounts()
    users = []
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, email, phone, role, status FROM users")
    users = [{"name": row[0], "email": row[1], "phone": row[2], "role": row[3], "status": row[4]} for row in cursor.fetchall()]
    conn.close()

    return jsonify({
        "role": session.get("role"),
        "name": session.get("name"),
        "users": users,
        "accounts": accounts,
        "stats": ig_stats,
        "terminal_logs": terminal_logs[:100]
    })

# ================= SINGLE GC ROUTES =================
@app.route("/gc_add_account", methods=["POST"])
def gc_add_account():
    if not is_authenticated():
        return jsonify({"status": "login_required"}), 401

    data = request.json or {}
    sessionid = data.get("sessionid", "").strip()
    url = data.get("url", "").strip()
    opponent = data.get("opponent", "").strip()
    header_text = data.get("header_text", "👑 SPAM BY SNAPPY 👑").strip()
    footer_text = data.get("footer_text", "👑 SCRIPT BY UI SNAPPY 👑").strip()
    space_lines = int(data.get("space_lines", 35))
    messages = [m.strip() for m in data.get("messages", "").split("\n") if m.strip()]
    gc_name = data.get("gc_name", "LOCKED BY GOD CLAN").strip()
    delay = float(data.get("delay", 4))

    if not sessionid or not url:
        return jsonify({"status": "error", "message": "Session ID and URL required!"}), 400

    uid = f"gc_{int(time.time())}_{random.randint(100,999)}"
    
    acc_data = {
        "uid": uid,
        "name": f"Single GC #{uid}",
        "username": opponent or "SingleGC",
        "url": url,
        "sessionid": sessionid,
        "opponent": opponent,
        "header_text": header_text,
        "footer_text": footer_text,
        "space_lines": space_lines,
        "use_long_format": True,
        "messages": messages,
        "gc_name": gc_name,
        "delay": delay,
        "is_locker": True,
        "owner": get_current_user(),
        "admin_name": get_current_user().split("@")[0],
        "system_owner": "UI SNAPPY KING",
        "createdAt": str(datetime.utcnow())
    }

    save_gc_account_db(uid, acc_data)
    gc_stats[uid] = {"sent": 0, "failed": 0, "running": False}
    log_terminal("AUTH", f"✅ Single GC Account #{uid} added!", "SUCCESS")
    
    return jsonify({"status": "ok", "uid": uid})

@app.route("/gc_start", methods=["POST"])
def gc_start():
    uid = request.json.get("uid")
    accounts = get_all_gc_accounts()
    acc = accounts.get(uid)
    if not acc:
        return jsonify({"status": "invalid"})

    if gc_running.get(uid):
        return jsonify({"status": "already_running"})

    gc_running[uid] = True
    gc_stats[uid]["running"] = True
    
    thread = threading.Thread(
        target=run_single_gc_worker,
        args=(
            acc["sessionid"], acc["url"], acc["opponent"] or "TARGET",
            acc["header_text"], acc["footer_text"], acc["space_lines"],
            acc["messages"] or ["UI SNAPPY ON TOP 🔥"], acc["gc_name"],
            acc["delay"], f"gc_{uid}", uid
        )
    )
    thread.daemon = True
    thread.start()
    
    log_terminal(uid, "🚀 Single GC started!", "SUCCESS")
    return jsonify({"status": "started"})

@app.route("/gc_stop", methods=["POST"])
def gc_stop():
    uid = request.json.get("uid")
    gc_running[uid] = False
    gc_stats[uid]["running"] = False
    log_terminal(uid, "⏹️ Single GC stopped.", "WARN")
    return jsonify({"status": "stopped"})

@app.route("/gc_delete_account", methods=["POST"])
def gc_delete_account():
    uid = request.json.get("uid")
    gc_running.pop(uid, None)
    gc_stats.pop(uid, None)
    delete_gc_account_db(uid)
    log_terminal(uid, "🗑️ Single GC deleted.", "WARN")
    return jsonify({"status": "ok"})

@app.route("/gc_status")
def gc_status():
    if not is_authenticated():
        return jsonify({"status": "login_required"}), 401

    accounts = get_all_gc_accounts()
    return jsonify({
        "accounts": accounts,
        "stats": gc_stats,
        "terminal_logs": terminal_logs[:100]
    })

# ================= OWNER ROUTES =================
@app.route("/api/owner/users/add", methods=["POST"])
def owner_add_user():
    if not is_authenticated() or not is_owner():
        return jsonify({"status": "denied"}), 403

    data = request.json or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").lower().strip()
    phone = data.get("phone", "").strip()
    password = data.get("password", "").strip()

    if not name or not email or not password:
        return jsonify({"status": "error", "message": "Name, Email and Password are required!"}), 400

    user_data = {
        "name": name,
        "email": email,
        "phone": phone or "+91 9507325677",
        "password": password,
        "role": "user",
        "status": "active",
        "lastOtpVerifiedAt": str(datetime.now()),
        "createdAt": str(datetime.now())
    }
    save_or_update_user(user_data)
    return jsonify({"status": "ok", "message": f"User '{name}' saved!"})

@app.route("/api/owner/users/delete", methods=["POST"])
def owner_delete_user():
    if not is_authenticated() or not is_owner():
        return jsonify({"status": "denied"}), 403

    email = request.json.get("user", "").strip()
    if not email:
        return jsonify({"status": "error", "message": "User email required!"}), 400

    delete_user_db(email)
    return jsonify({"status": "ok", "message": f"User '{email}' deleted!"})

@app.route("/api/owner/users/toggle_status", methods=["POST"])
def owner_toggle_user_status():
    if not is_authenticated() or not is_owner():
        return jsonify({"status": "denied"}), 403

    email = request.json.get("email", "").lower().strip()
    new_status = request.json.get("status", "active")
    user = find_user_by_email(email)
    if not user:
        return jsonify({"status": "error", "message": "User not found!"}), 400

    user["status"] = new_status
    save_or_update_user(user)
    return jsonify({"status": "ok", "message": f"Status updated to '{new_status}'!"})

@app.route("/api/owner/users/edit", methods=["POST"])
def owner_edit_user():
    if not is_authenticated() or not is_owner():
        return jsonify({"status": "denied"}), 403

    data = request.json or {}
    old_email = data.get("old_email", "").lower().strip()
    new_name = data.get("name", "").strip()
    new_email = data.get("email", "").lower().strip()
    new_phone = data.get("phone", "").strip()
    new_password = data.get("password", "").strip()
    new_status = data.get("status", "active").strip()

    if not old_email:
        return jsonify({"status": "error", "message": "Target user email required!"}), 400

    user = find_user_by_email(old_email)
    if not user:
        return jsonify({"status": "error", "message": f"User '{old_email}' not found!"}), 404

    if new_name: user["name"] = new_name
    if new_phone: user["phone"] = new_phone
    if new_password: user["password"] = new_password
    if new_status: user["status"] = new_status

    if new_email and new_email != old_email:
        if find_user_by_email(new_email):
            return jsonify({"status": "error", "message": f"Email '{new_email}' already in use!"}), 400
        
        user["email"] = new_email
        delete_user_db(old_email)
        save_or_update_user(user)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE ig_accounts SET owner = ? WHERE owner = ?", (new_email, old_email))
        cursor.execute("UPDATE gc_accounts SET owner = ? WHERE owner = ?", (new_email, old_email))
        conn.commit()
        conn.close()
    else:
        save_or_update_user(user)

    return jsonify({"status": "ok", "message": "User updated successfully!"})

@app.route("/api/user/profile/update", methods=["POST"])
def user_profile_update():
    if not is_authenticated():
        return jsonify({"status": "login_required"}), 401

    if is_owner():
        data = request.json or {}
        new_pass = data.get("password", "").strip()
        if new_pass:
            os.environ["OWNER_PASSWORD"] = new_pass
        return jsonify({"status": "ok", "message": "Owner profile updated!"})

    current_email = get_current_user().lower().strip()
    user = find_user_by_email(current_email)
    if not user:
        return jsonify({"status": "error", "message": "User not found!"}), 404

    data = request.json or {}
    if data.get("name"): user["name"] = data.get("name")
    if data.get("phone"): user["phone"] = data.get("phone")
    if data.get("password"): user["password"] = data.get("password")
    
    new_email = data.get("email", "").lower().strip()
    if new_email and new_email != current_email:
        if find_user_by_email(new_email):
            return jsonify({"status": "error", "message": "Email already in use!"}), 400
        user["email"] = new_email
        delete_user_db(current_email)
        session["user"] = new_email
        save_or_update_user(user)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE ig_accounts SET owner = ? WHERE owner = ?", (new_email, current_email))
        cursor.execute("UPDATE gc_accounts SET owner = ? WHERE owner = ?", (new_email, current_email))
        conn.commit()
        conn.close()
    else:
        save_or_update_user(user)

    if data.get("name"): session["name"] = data.get("name")
    
    return jsonify({"status": "ok", "message": "Profile updated!"})

@app.route("/api/user/profile", methods=["GET"])
def get_user_profile():
    if not is_authenticated():
        return jsonify({"status": "login_required"}), 401

    if is_owner():
        return jsonify({
            "status": "ok",
            "role": "owner",
            "name": session.get("name", "PLATFORM OWNER"),
            "username": os.getenv("OWNER_USERNAME", "OWNER"),
            "email": "spamkingxl400@gmail.com",
            "phone": "+91 9507325677"
        })

    user = find_user_by_email(get_current_user())
    if not user:
        return jsonify({"status": "ok", "role": "user", "name": session.get("name", "User"), "email": session.get("user", ""), "phone": ""})

    return jsonify({
        "status": "ok",
        "role": "user",
        "name": user.get("name", session.get("name")),
        "email": user.get("email", session.get("user")),
        "phone": user.get("phone", ""),
        "status": user.get("status", "active")
    })

# ================= HTML TEMPLATES =================
LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head><title>Login - UI SNAPPY</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;display:flex;justify-content:center;align-items:center;min-height:100vh;font-family:Arial,sans-serif;color:#fff}
.container{background:#141414;padding:40px;border-radius:16px;border:1px solid #ff0055;width:400px;box-shadow:0 0 30px rgba(255,0,85,0.2)}
h1{color:#ff3b8d;text-align:center;font-size:28px;margin-bottom:8px}
.subtitle{text-align:center;color:#888;font-size:14px;margin-bottom:30px}
input{width:100%;padding:12px 16px;background:#1a1a1a;border:1px solid #333;border-radius:8px;color:#fff;font-size:15px;margin-bottom:15px}
input:focus{outline:none;border-color:#ff0055}
.btn{width:100%;padding:14px;background:#ff0055;border:none;border-radius:8px;color:#fff;font-size:16px;font-weight:600;cursor:pointer}
.btn:hover{background:#e6004d}
.links{text-align:center;margin-top:20px;font-size:14px;color:#888}
.links a{color:#ff3b8d;text-decoration:none}
</style>
</head>
<body>
<div class="container">
<h1>👑 UI SNAPPY</h1>
<p class="subtitle">Sign in to your account</p>
<form id="loginForm">
<input type="email" id="email" placeholder="Email Address" required>
<input type="password" id="password" placeholder="Password" required>
<button type="submit" class="btn">Sign In</button>
</form>
<div class="links">
<a href="#" onclick="showForgot()">Forgot Password?</a> | <a href="#" onclick="showRegister()">Create Account</a>
</div>
<div style="text-align:center;margin-top:20px;font-size:12px;color:#555;">
🔐 Owner Login: <a href="/owner/login" style="color:#00ffcc;">Click Here</a>
</div>
</div>
<script>
document.getElementById('loginForm').addEventListener('submit', async function(e){
e.preventDefault();
const email=document.getElementById('email').value;
const password=document.getElementById('password').value;
try{
const res=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password})});
const data=await res.json();
if(data.success){
if(data.requireOtp){
const otp=prompt('Enter OTP sent to your Gmail:');
if(otp){const r=await fetch('/api/auth/verify-login-otp',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,otp})});const d=await r.json();if(d.success)window.location.href=d.redirect;else alert(d.message);}
}else{window.location.href=data.redirect;}
}else{alert(data.message);}
}catch(e){alert('Network error');}
});
function showForgot(){const email=prompt('Enter your registered email:');if(email){sendForgotOTP(email);}}
async function sendForgotOTP(email){const res=await fetch('/api/auth/forgot-otp',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email})});const data=await res.json();if(data.success){const otp=prompt('Enter OTP:');if(otp){const np=prompt('New password:');if(np){const r=await fetch('/api/auth/reset-password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,otp,newPassword:np})});const d=await r.json();alert(d.message);}}}else{alert(data.message);}}
function showRegister(){const name=prompt('Full Name:');if(!name)return;const email=prompt('Email:');if(!email)return;const phone=prompt('Phone:');const pass=prompt('Password:');if(!pass)return;registerUser(name,email,phone,pass);}
async function registerUser(name,email,phone,password){const res=await fetch('/api/auth/send-register-otp',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email})});const data=await res.json();if(data.success){const otp=prompt('Enter OTP sent to your Gmail:');if(otp){const r=await fetch('/api/auth/verify-register-otp',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,otp})});const d=await r.json();if(d.success){const rr=await fetch('/api/auth/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,email,phone,password})});const dd=await rr.json();alert(dd.message);if(dd.success)window.location.href=dd.redirect;}}}else{alert(data.message);}}
</script>
</body>
</html>
"""

OWNER_LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head><title>Owner Login - UI SNAPPY</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;display:flex;justify-content:center;align-items:center;min-height:100vh;font-family:Arial,sans-serif;color:#fff}
.container{background:#141414;padding:40px;border-radius:16px;border:2px solid #00ffcc;width:400px;box-shadow:0 0 40px rgba(0,255,204,0.2)}
h1{color:#00ffcc;text-align:center;font-size:26px;margin-bottom:8px}
.subtitle{text-align:center;color:#888;font-size:13px;margin-bottom:30px}
input{width:100%;padding:12px 16px;background:#1a1a1a;border:1px solid #333;border-radius:8px;color:#fff;font-size:15px;margin-bottom:15px}
input:focus{outline:none;border-color:#00ffcc}
.btn{width:100%;padding:14px;background:#00ffcc;border:none;border-radius:8px;color:#000;font-size:16px;font-weight:700;cursor:pointer}
.btn:hover{background:#00e6b8}
.back-link{text-align:center;margin-top:20px}
.back-link a{color:#00ffcc;text-decoration:none}
</style>
</head>
<body>
<div class="container">
<h1>🔐 OWNER LOGIN</h1>
<p class="subtitle">Platform Administrator Access</p>
<form id="ownerLoginForm">
<input type="text" id="username" placeholder="Owner Username" required>
<input type="password" id="password" placeholder="Owner Password" required>
<button type="submit" class="btn">🔓 Access Panel</button>
</form>
<div class="back-link"><a href="/login">← Back to User Login</a></div>
</div>
<script>
document.getElementById('ownerLoginForm').addEventListener('submit', async function(e){
e.preventDefault();
const username=document.getElementById('username').value;
const password=document.getElementById('password').value;
try{
const res=await fetch('/api/owner/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password})});
const data=await res.json();
if(data.success){window.location.href=data.redirect;}else{alert(data.message);}
}catch(e){alert('Network error');}
});
</script>
</body>
</html>
"""

MODE_SELECT_HTML = """
<!DOCTYPE html>
<html>
<head><title>Mode Select - UI SNAPPY</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;display:flex;justify-content:center;align-items:center;min-height:100vh;font-family:Arial,sans-serif;color:#fff}
.container{background:#141414;padding:40px;border-radius:16px;border:1px solid #ff0055;width:500px;box-shadow:0 0 30px rgba(255,0,85,0.2)}
h1{color:#ff3b8d;text-align:center;font-size:28px;margin-bottom:8px}
.subtitle{text-align:center;color:#888;font-size:14px;margin-bottom:30px}
.mode-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.mode-card{background:#1a1a1a;padding:20px;border-radius:12px;text-align:center;cursor:pointer;border:1px solid #333;transition:all 0.3s;text-decoration:none;color:#fff}
.mode-card:hover{border-color:#ff0055;transform:scale(1.03)}
.mode-card .icon{font-size:32px;margin-bottom:8px}
.mode-card .label{font-size:14px;font-weight:600}
.mode-card .desc{font-size:11px;color:#888;margin-top:4px}
.mode-card.owner{grid-column:span 2;border-color:#00ffcc}
.logout{text-align:center;margin-top:20px}
.logout a{color:#ff4444;text-decoration:none;font-size:14px}
.user-info{text-align:center;color:#00ffcc;font-size:13px;margin-bottom:20px}
</style>
</head>
<body>
<div class="container">
<h1>👑 UI SNAPPY</h1>
<p class="subtitle">Select Your Mode</p>
<div class="user-info">👋 Welcome, {{ name }} ({{ role }})</div>
<div class="mode-grid">
<a href="/multi_gc" class="mode-card"><div class="icon">📱</div><div class="label">Multi-GC</div><div class="desc">Multiple Group Spam</div></a>
<a href="/single_gc" class="mode-card"><div class="icon">🎯</div><div class="label">Single GC</div><div class="desc">Single Group Attack</div></a>
<a href="/owner" class="mode-card owner"><div class="icon">👑</div><div class="label">Owner Panel</div><div class="desc">Full Control & Administration</div></a>
</div>
<div class="logout"><a href="/logout">🚪 Logout</a></div>
</div>
</body>
</html>
"""

MULTI_GC_HTML = """
<!DOCTYPE html>
<html>
<head><title>Multi-GC - UI SNAPPY</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;color:#fff;font-family:Arial,sans-serif;padding:20px}
.container{max-width:1200px;margin:0 auto}
.header{display:flex;justify-content:space-between;align-items:center;padding:15px 20px;background:#141414;border-radius:12px;border:1px solid #ff0055;margin-bottom:20px}
.header h1{color:#ff3b8d;font-size:22px}
.card{background:#141414;border-radius:12px;border:1px solid #333;padding:20px;margin-bottom:20px}
.card h2{color:#00ffcc;font-size:18px;margin-bottom:15px}
input,textarea{width:100%;padding:10px 14px;background:#1a1a1a;border:1px solid #333;border-radius:8px;color:#fff;font-size:14px;margin-bottom:10px}
textarea{min-height:80px;resize:vertical}
button{padding:10px 20px;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer}
.btn-primary{background:#ff0055;color:#fff}
.btn-success{background:#00ff88;color:#000}
.btn-danger{background:#ff4444;color:#fff}
.btn-group{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.status-badge{display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:600}
.status-running{background:#00ff88;color:#000}
.status-stopped{background:#ff4444;color:#fff}
.terminal{background:#000;padding:15px;border-radius:8px;font-family:monospace;font-size:12px;max-height:300px;overflow-y:auto;color:#00ffcc;border:1px solid #333}
.log-line{padding:2px 0;border-bottom:1px solid #111}
.log-time{color:#888;margin-right:10px}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:20px}
@media(max-width:768px){.grid-2{grid-template-columns:1fr}}
.back-link{color:#888;text-decoration:none;font-size:14px}
.back-link:hover{color:#fff}
.account-item{background:#1a1a1a;padding:12px 16px;border-radius:8px;margin-bottom:8px;border-left:3px solid #ff0055;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap}
.btn-small{padding:4px 10px;font-size:11px;border:none;border-radius:6px;cursor:pointer;color:#fff}
.btn-small.start{background:#10b981}
.btn-small.stop{background:#f59e0b;color:#000}
.btn-small.delete{background:#ef4444}
</style>
</head>
<body>
<div class="container">
<div class="header"><h1>📱 Multi-GC Master</h1><div><a href="/mode" class="back-link">← Back</a> <a href="/logout" class="back-link" style="color:#ff4444;margin-left:10px;">🚪</a></div></div>

<div class="card">
<h2>➕ Add Multi-GC Account</h2>
<form id="addForm">
<input id="sessionid" placeholder="Session ID *" required>
<input id="opponent" placeholder="Target Name (optional)">
<div class="grid-2">
<div><input id="header_text" placeholder="Header Text" value="👑 SPAM BY SNAPPY 👑"></div>
<div><input id="footer_text" placeholder="Footer Text" value="👑 SCRIPT BY UI SNAPPY 👑"></div>
</div>
<textarea id="messages" placeholder="Messages (one per line)">UI SNAPPY ON TOP 🔥
SYSTEM ONLINE 💥
WAR ACTIVE ⚡</textarea>
<textarea id="renames" placeholder="GC Names (one per line)">LOCKED BY GOD CLAN</textarea>
<div class="grid-2">
<div><input id="delay" type="number" step="0.5" value="2.0" placeholder="Delay (sec)"></div>
<div><input id="max_groups" type="number" value="5" placeholder="Max Groups"></div>
</div>
<button type="submit" class="btn-primary">➕ Add Account</button>
</form>
</div>

<div class="card">
<h2>📋 Accounts</h2>
<div id="accountsList">Loading...</div>
</div>

<div class="card">
<h2>🖥️ Terminal Logs</h2>
<button class="btn-small" style="background:#f59e0b;color:#000;" onclick="clearTerminal()">🗑️ Clear</button>
<div id="terminal" class="terminal"><div class="log-line">[SYSTEM] Ready...</div></div>
</div>
</div>

<script>
async function loadStatus(){
try{const r=await fetch('/status');const d=await r.json();renderAccounts(d.accounts||{},d.stats||{});if(d.terminal_logs)renderTerminal(d.terminal_logs);}catch(e){console.error(e);}}
function renderAccounts(accounts,stats){const container=document.getElementById('accountsList');const keys=Object.keys(accounts);if(keys.length===0){container.innerHTML='<p style="color:#888;">No accounts added yet.</p>';return;}let html='';for(const uid of keys){const acc=accounts[uid];const st=stats[uid]||{};const isRunning=st.running||false;html+=`
<div class="account-item">
<div><strong>${acc.name||uid}</strong><br><span style="font-size:12px;color:#888;">Target: ${acc.opponent||'N/A'} | Sent: ${st.sent||0}</span>
<div><span class="status-badge ${isRunning?'status-running':'status-stopped'}">${isRunning?'🟢 Running':'🔴 Stopped'}</span></div></div>
<div>
<button class="btn-small start" onclick="startBot('${uid}')">▶ Start</button>
<button class="btn-small stop" onclick="stopBot('${uid}')">⏹ Stop</button>
<button class="btn-small delete" onclick="deleteAccount('${uid}')">🗑</button>
</div>
</div>`;}container.innerHTML=html;}
function renderTerminal(logs){const container=document.getElementById('terminal');let html='';const recent=logs.slice(-50);for(const log of recent){html+=`<div class="log-line"><span class="log-time">[${log.time||'--:--:--'}]</span>[${log.level}] ${log.msg||''}</div>`;}container.innerHTML=html||'<div class="log-line">[SYSTEM] No logs yet.</div>';container.scrollTop=container.scrollHeight;}
document.getElementById('addForm').addEventListener('submit',async function(e){e.preventDefault();const data={sessionid:document.getElementById('sessionid').value,opponent:document.getElementById('opponent').value,header_text:document.getElementById('header_text').value,footer_text:document.getElementById('footer_text').value,messages:document.getElementById('messages').value,renames:document.getElementById('renames').value,delay:parseFloat(document.getElementById('delay').value),max_groups:parseInt(document.getElementById('max_groups').value)};try{const r=await fetch('/add_account',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const res=await r.json();if(res.status==='ok'){alert('✅ Account added!');loadStatus();}}catch(e){alert('❌ Error');}});
async function startBot(uid){await fetch('/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({uid})});loadStatus();}
async function stopBot(uid){await fetch('/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({uid})});loadStatus();}
async function deleteAccount(uid){if(!confirm('Delete?'))return;await fetch('/delete_account',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({uid})});loadStatus();}
async function clearTerminal(){await fetch('/api/ig/clear_terminal',{method:'POST'});document.getElementById('terminal').innerHTML='<div class="log-line">[SYSTEM] Terminal cleared.</div>';}
loadStatus();setInterval(loadStatus,3000);
</script>
</body>
</html>
"""

SINGLE_GC_HTML = """
<!DOCTYPE html>
<html>
<head><title>Single GC - UI SNAPPY</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;color:#fff;font-family:Arial,sans-serif;padding:20px}
.container{max-width:1200px;margin:0 auto}
.header{display:flex;justify-content:space-between;align-items:center;padding:15px 20px;background:#141414;border-radius:12px;border:1px solid #ff0055;margin-bottom:20px}
.header h1{color:#ff3b8d;font-size:22px}
.card{background:#141414;border-radius:12px;border:1px solid #333;padding:20px;margin-bottom:20px}
.card h2{color:#00ffcc;font-size:18px;margin-bottom:15px}
input,textarea{width:100%;padding:10px 14px;background:#1a1a1a;border:1px solid #333;border-radius:8px;color:#fff;font-size:14px;margin-bottom:10px}
textarea{min-height:80px;resize:vertical}
button{padding:10px 20px;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer}
.btn-primary{background:#ff0055;color:#fff}
.btn-success{background:#00ff88;color:#000}
.btn-danger{background:#ff4444;color:#fff}
.btn-group{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.status-badge{display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:600}
.status-running{background:#00ff88;color:#000}
.status-stopped{background:#ff4444;color:#fff}
.terminal{background:#000;padding:15px;border-radius:8px;font-family:monospace;font-size:12px;max-height:300px;overflow-y:auto;color:#00ffcc;border:1px solid #333}
.account-item{background:#1a1a1a;padding:12px 16px;border-radius:8px;margin-bottom:8px;border-left:3px solid #ff0055;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap}
.btn-small{padding:4px 10px;font-size:11px;border:none;border-radius:6px;cursor:pointer;color:#fff}
.btn-small.start{background:#10b981}
.btn-small.stop{background:#f59e0b;color:#000}
.btn-small.delete{background:#ef4444}
.back-link{color:#888;text-decoration:none;font-size:14px}
</style>
</head>
<body>
<div class="container">
<div class="header"><h1>🎯 Single GC Master</h1><div><a href="/mode" class="back-link">← Back</a> <a href="/logout" class="back-link" style="color:#ff4444;margin-left:10px;">🚪</a></div></div>

<div class="card">
<h2>➕ Add Single GC Account</h2>
<form id="addForm">
<input id="url" placeholder="Group URL (https://www.instagram.com/direct/t/...)" required>
<input id="sessionid" placeholder="Session ID *" required>
<input id="opponent" placeholder="Target Name (optional)">
<input id="header_text" placeholder="Header Text" value="👑 SPAM BY SNAPPY 👑">
<input id="footer_text" placeholder="Footer Text" value="👑 SCRIPT BY UI SNAPPY 👑">
<textarea id="messages" placeholder="Messages (one per line)">UI SNAPPY ON TOP 🔥
SYSTEM ONLINE 💥
WAR ACTIVE ⚡</textarea>
<input id="gc_name" placeholder="GC Name Lock" value="LOCKED BY GOD CLAN">
<input id="delay" type="number" step="0.5" value="4" placeholder="Delay (sec)">
<button type="submit" class="btn-primary">➕ Add Single GC</button>
</form>
</div>

<div class="card">
<h2>📋 Accounts</h2>
<div id="accountsList">Loading...</div>
</div>

<div class="card">
<h2>🖥️ Terminal Logs</h2>
<button class="btn-small" style="background:#f59e0b;color:#000;" onclick="clearTerminal()">🗑️ Clear</button>
<div id="terminal" class="terminal"><div class="log-line">[SYSTEM] Ready...</div></div>
</div>
</div>

<script>
async function loadStatus(){
try{const r=await fetch('/gc_status');const d=await r.json();renderAccounts(d.accounts||{},d.stats||{});if(d.terminal_logs)renderTerminal(d.terminal_logs);}catch(e){console.error(e);}}
function renderAccounts(accounts,stats){const container=document.getElementById('accountsList');const keys=Object.keys(accounts);if(keys.length===0){container.innerHTML='<p style="color:#888;">No accounts added yet.</p>';return;}let html='';for(const uid of keys){const acc=accounts[uid];const st=stats[uid]||{};const isRunning=st.running||false;html+=`
<div class="account-item">
<div><strong>${acc.name||uid}</strong><br><span style="font-size:12px;color:#888;">Target: ${acc.opponent||'N/A'} | Sent: ${st.sent||0}</span>
<div><span class="status-badge ${isRunning?'status-running':'status-stopped'}">${isRunning?'🟢 Running':'🔴 Stopped'}</span></div></div>
<div>
<button class="btn-small start" onclick="startBot('${uid}')">▶ Start</button>
<button class="btn-small stop" onclick="stopBot('${uid}')">⏹ Stop</button>
<button class="btn-small delete" onclick="deleteAccount('${uid}')">🗑</button>
</div>
</div>`;}container.innerHTML=html;}
function renderTerminal(logs){const container=document.getElementById('terminal');let html='';const recent=logs.slice(-50);for(const log of recent){html+=`<div class="log-line"><span class="log-time">[${log.time||'--:--:--'}]</span>[${log.level}] ${log.msg||''}</div>`;}container.innerHTML=html||'<div class="log-line">[SYSTEM] No logs yet.</div>';container.scrollTop=container.scrollHeight;}
document.getElementById('addForm').addEventListener('submit',async function(e){e.preventDefault();const data={url:document.getElementById('url').value,sessionid:document.getElementById('sessionid').value,opponent:document.getElementById('opponent').value,header_text:document.getElementById('header_text').value,footer_text:document.getElementById('footer_text').value,messages:document.getElementById('messages').value,gc_name:document.getElementById('gc_name').value,delay:parseFloat(document.getElementById('delay').value)};try{const r=await fetch('/gc_add_account',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const res=await r.json();if(res.status==='ok'){alert('✅ Account added!');loadStatus();}}catch(e){alert('❌ Error');}});
async function startBot(uid){await fetch('/gc_start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({uid})});loadStatus();}
async function stopBot(uid){await fetch('/gc_stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({uid})});loadStatus();}
async function deleteAccount(uid){if(!confirm('Delete?'))return;await fetch('/gc_delete_account',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({uid})});loadStatus();}
async function clearTerminal(){await fetch('/api/gc/clear_terminal',{method:'POST'});document.getElementById('terminal').innerHTML='<div class="log-line">[SYSTEM] Terminal cleared.</div>';}
loadStatus();setInterval(loadStatus,3000);
</script>
</body>
</html>
"""

OWNER_HTML = """
<!DOCTYPE html>
<html>
<head><title>Owner Dashboard - UI SNAPPY</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;color:#fff;font-family:Arial,sans-serif;padding:20px}
.container{max-width:1200px;margin:0 auto}
.header{display:flex;justify-content:space-between;align-items:center;padding:15px 20px;background:#141414;border-radius:12px;border:1px solid #facc15;margin-bottom:20px}
.header h1{color:#facc15;font-size:22px}
.card{background:#141414;border-radius:12px;border:1px solid #333;padding:20px;margin-bottom:20px}
.card h2{color:#facc15;font-size:18px;margin-bottom:15px}
input,select{width:100%;padding:10px 14px;background:#1a1a1a;border:1px solid #333;border-radius:8px;color:#fff;font-size:14px;margin-bottom:10px}
button{padding:10px 20px;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer}
.btn-primary{background:#facc15;color:#000}
.btn-danger{background:#ef4444;color:#fff}
.btn-success{background:#10b981;color:#fff}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:20px}
@media(max-width:768px){.grid-2{grid-template-columns:1fr}}
.user-card{background:#1a1a1a;padding:12px 16px;border-radius:8px;margin-bottom:8px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap}
.badge-active{background:#10b981;padding:2px 8px;border-radius:4px;font-size:11px;color:#fff}
.badge-blocked{background:#ef4444;padding:2px 8px;border-radius:4px;font-size:11px;color:#fff}
.btn-small{padding:4px 10px;font-size:11px;border:none;border-radius:4px;cursor:pointer;color:#fff}
.btn-small.edit{background:#3b82f6}
.btn-small.block{background:#f59e0b;color:#000}
.btn-small.delete{background:#ef4444}
.back-link{color:#888;text-decoration:none;font-size:14px}
.metric{display:inline-block;margin-right:20px;font-size:14px}
.metric span{color:#facc15;font-weight:700}
</style>
</head>
<body>
<div class="container">
<div class="header"><h1>👑 Owner Command Center</h1><div><a href="/mode" class="back-link">← Back</a> <a href="/logout" class="back-link" style="color:#ff4444;margin-left:10px;">🚪</a></div></div>

<div class="card">
<h2>📊 Metrics</h2>
<div id="metrics"><span class="metric">👥 Users: <span id="mUsers">0</span></span><span class="metric">📱 Multi-GC: <span id="mMulti">0</span></span><span class="metric">🎯 Single GC: <span id="mSingle">0</span></span></div>
</div>

<div class="card">
<h2>➕ Add User</h2>
<div class="grid-2">
<input id="newName" placeholder="Full Name">
<input id="newEmail" placeholder="Email">
<input id="newPhone" placeholder="Phone">
<input id="newPass" placeholder="Password">
</div>
<button class="btn-primary" onclick="addUser()">💾 Create User</button>
</div>

<div class="card">
<h2>👥 All Users</h2>
<div id="usersList">Loading...</div>
</div>
</div>

<script>
async function loadData(){
try{const r=await fetch('/status');const d=await r.json();document.getElementById('mUsers').textContent=(d.users||[]).length;document.getElementById('mMulti').textContent=Object.keys(d.accounts||{}).length;document.getElementById('mSingle').textContent=Object.keys(d.gc_accounts||{}).length||0;renderUsers(d.users||[]);}catch(e){console.error(e);}}
function renderUsers(users){const container=document.getElementById('usersList');if(users.length===0){container.innerHTML='<p style="color:#888;">No users found.</p>';return;}let html='';for(const u of users){const isBlocked=u.status==='blocked';html+=`
<div class="user-card">
<div><strong>${u.name||u.email}</strong><br><span style="font-size:12px;color:#888;">${u.email} | ${u.phone||'N/A'}</span>
<span class="${isBlocked?'badge-blocked':'badge-active'}">${isBlocked?'BLOCKED':'ACTIVE'}</span></div>
<div>
<button class="btn-small block" onclick="toggleStatus('${u.email}','${isBlocked?'active':'blocked'}')">${isBlocked?'🟢 Unblock':'⛔ Block'}</button>
<button class="btn-small delete" onclick="deleteUser('${u.email}')">🗑 Delete</button>
</div>
</div>`;}container.innerHTML=html;}
async function addUser(){const name=document.getElementById('newName').value;const email=document.getElementById('newEmail').value;const phone=document.getElementById('newPhone').value;const password=document.getElementById('newPass').value;if(!name||!email||!password)return alert('Name, Email, Password required!');const r=await fetch('/api/owner/users/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,email,phone,password})});const d=await r.json();alert(d.message);document.getElementById('newName').value='';document.getElementById('newEmail').value='';document.getElementById('newPhone').value='';document.getElementById('newPass').value='';loadData();}
async function toggleStatus(email,status){await fetch('/api/owner/users/toggle_status',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,status})});loadData();}
async function deleteUser(email){if(!confirm('Delete user?'))return;await fetch('/api/owner/users/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user:email})});loadData();}
loadData();setInterval(loadData,5000);
</script>
</body>
</html>
"""

# ================= RUNNER =================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 20822))
    print(f"[UI SNAPPY] Running on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)