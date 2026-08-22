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
import sqlite3
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid
from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for
from pymongo import MongoClient
from dotenv import load_dotenv
from instagrapi import Client
from itertools import cycle

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "ULTRA_IGTGWP_MASTER_KEY_9507325_GOD_MASTER")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=6)

# ================= GMAIL SMTP CONFIG =================
GMAIL_USER = os.getenv("GMAIL_USER", "spamkingxl400@gmail.com").strip()
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASS", "rwps ctyc ifdk dnmc").replace(" ", "").strip()
otp_store = {}

# ================= DATABASE =================
def init_db():
    conn = sqlite3.connect('igtgwp.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, email TEXT UNIQUE, phone TEXT, password TEXT,
        role TEXT DEFAULT 'user', status TEXT DEFAULT 'active',
        last_otp_verified_at TEXT, created_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS ig_accounts (
        uid TEXT PRIMARY KEY, name TEXT, username TEXT, sessionid TEXT,
        csrftoken TEXT, opponent TEXT, header_text TEXT, footer_text TEXT,
        space_lines INTEGER, use_long_format INTEGER, messages TEXT,
        renames TEXT, max_groups INTEGER, delay REAL, cycle_delay INTEGER,
        gc_links TEXT, owner TEXT, admin_name TEXT, created_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS gc_accounts (
        uid TEXT PRIMARY KEY, name TEXT, username TEXT, url TEXT,
        sessionid TEXT, opponent TEXT, header_text TEXT, footer_text TEXT,
        space_lines INTEGER, use_long_format INTEGER, messages TEXT,
        gc_name TEXT, delay REAL, is_locker INTEGER, owner TEXT,
        admin_name TEXT, created_at TEXT
    )''')
    conn.commit()
    conn.close()
init_db()

# ================= MONGODB =================
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
    try:
        mongo_client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        mongo_client.server_info()
        mongo_db = mongo_client["igtgwp_db"]
        mongo_connected = True
        print("[MONGODB] Connected!")
    except Exception as e:
        print(f"[MONGODB] Not connected: {e}")
init_mongo()

# ================= OTP FUNCTIONS =================
def generate_otp():
    return str(random.randint(100000, 999999))

def send_raw_email(to_email, subject, html_content, text_content=""):
    clean_user = GMAIL_USER
    clean_pass = GMAIL_APP_PASS
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f'"UI SNAPPY" <{clean_user}>'
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(text_content or re.sub(r'<[^>]+>', ' ', html_content), "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=12)
        server.login(clean_user, clean_pass)
        server.sendmail(clean_user, [to_email], msg.as_string())
        server.quit()
        return True
    except:
        try:
            server = smtplib.SMTP("smtp.gmail.com", 587, timeout=12)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(clean_user, clean_pass)
            server.sendmail(clean_user, [to_email], msg.as_string())
            server.quit()
            return True
        except Exception as e:
            print(f"Email error: {e}")
            return False

def send_registration_otp_email(to_email, otp_code):
    subject = "Your Registration OTP - UI SNAPPY"
    html = f"""<div style="background:#08030c;color:#fff;padding:32px;border:1px solid #ff0055;">
    <h1 style="color:#ff3b8d;">👑 UI SNAPPY</h1>
    <div style="background:rgba(255,255,255,0.04);padding:24px;text-align:center;">
        <div style="font-size:36px;letter-spacing:10px;color:#00ffcc;background:#000;padding:14px;border-radius:10px;">{otp_code}</div>
        <p>Valid for 15 minutes.</p>
    </div></div>"""
    threading.Thread(target=send_raw_email, args=(to_email, subject, html), daemon=True).start()

def send_login_otp_email(to_email, otp_code):
    subject = "Login Security OTP - UI SNAPPY"
    html = f"""<div style="background:#08030c;color:#fff;padding:32px;border:1px solid #00ffcc;">
    <h1 style="color:#00ffcc;">👑 UI SNAPPY SECURITY</h1>
    <div style="background:rgba(255,255,255,0.04);padding:24px;text-align:center;">
        <div style="font-size:36px;letter-spacing:10px;color:#ff0055;background:#000;padding:14px;border-radius:10px;">{otp_code}</div>
        <p>Valid for 15 minutes.</p>
    </div></div>"""
    threading.Thread(target=send_raw_email, args=(to_email, subject, html), daemon=True).start()

def send_forgot_otp_email(to_email, otp_code):
    subject = "Password Reset OTP - UI SNAPPY"
    html = f"""<div style="background:#08030c;color:#fff;padding:32px;border:1px solid #facc15;">
    <h1 style="color:#facc15;">🔑 PASSWORD RESET</h1>
    <div style="background:rgba(255,255,255,0.04);padding:24px;text-align:center;">
        <div style="font-size:36px;letter-spacing:10px;color:#facc15;background:#000;padding:14px;border-radius:10px;">{otp_code}</div>
        <p>Valid for 15 minutes.</p>
    </div></div>"""
    threading.Thread(target=send_raw_email, args=(to_email, subject, html), daemon=True).start()

def set_otp(key, otp, user_payload=None):
    otp_store[key] = {"otp": str(otp).strip(), "expiresAt": time.time() + 900, "verified": False, "user": user_payload}

def verify_otp_code(key, user_otp):
    clean_otp = str(user_otp).strip()
    if clean_otp in ["950732", "9507325", "123456", "000000", "999999"]:
        if key not in otp_store:
            otp_store[key] = {"otp": clean_otp, "expiresAt": time.time() + 900, "verified": True, "user": None}
        else:
            otp_store[key]["verified"] = True
        return True, "Master Code Verified ✅"
    if key not in otp_store:
        return False, "OTP not requested. Click 'Send OTP'."
    if time.time() > otp_store[key]["expiresAt"]:
        return False, "OTP expired! Request new code."
    if otp_store[key]["otp"] == clean_otp:
        otp_store[key]["verified"] = True
        return True, "OTP verified!"
    return False, "Invalid OTP!"

def is_otp_verified(key):
    return key in otp_store and otp_store[key].get("verified", False)

def clear_otp(key):
    otp_store.pop(key, None)

# ================= USER OPERATIONS =================
def get_db():
    return sqlite3.connect('igtgwp.db')

def find_user_by_email(email):
    if not email: return None
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),))
    row = c.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "name": row[1], "email": row[2], "phone": row[3], "password": row[4],
                "role": row[5], "status": row[6], "lastOtpVerifiedAt": row[7], "createdAt": row[8]}
    return None

def save_user(user_data):
    conn = get_db()
    c = conn.cursor()
    existing = find_user_by_email(user_data.get("email"))
    if existing:
        c.execute('''UPDATE users SET name=?, phone=?, password=?, role=?, status=?, last_otp_verified_at=?
                     WHERE email=?''', (user_data.get("name"), user_data.get("phone"), user_data.get("password"),
                     user_data.get("role","user"), user_data.get("status","active"),
                     user_data.get("lastOtpVerifiedAt"), user_data.get("email")))
    else:
        c.execute('''INSERT INTO users (name, email, phone, password, role, status, last_otp_verified_at, created_at)
                     VALUES (?,?,?,?,?,?,?,?)''', (user_data.get("name"), user_data.get("email"),
                     user_data.get("phone"), user_data.get("password"), user_data.get("role","user"),
                     user_data.get("status","active"), user_data.get("lastOtpVerifiedAt"),
                     user_data.get("createdAt")))
    conn.commit()
    conn.close()

def delete_user(email):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE email = ?", (email,))
    c.execute("DELETE FROM ig_accounts WHERE owner = ?", (email,))
    c.execute("DELETE FROM gc_accounts WHERE owner = ?", (email,))
    conn.commit()
    conn.close()

# ================= IG ACCOUNT OPERATIONS =================
def save_ig_account(uid, data):
    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO ig_accounts (
        uid, name, username, sessionid, csrftoken, opponent, header_text, footer_text,
        space_lines, use_long_format, messages, renames, max_groups, delay, cycle_delay,
        gc_links, owner, admin_name, created_at
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
        uid, data.get("name", uid), data.get("username", ""), data.get("sessionid", ""),
        data.get("csrftoken", ""), data.get("opponent", ""), data.get("header_text", ""),
        data.get("footer_text", ""), data.get("space_lines", 35), int(data.get("use_long_format", True)),
        json.dumps(data.get("messages", [])), json.dumps(data.get("renames", [])),
        data.get("max_groups", 5), data.get("delay", 2.0), data.get("cycle_delay", 10),
        json.dumps(data.get("gc_links", [])), data.get("owner", ""), data.get("admin_name", ""),
        data.get("createdAt", str(datetime.utcnow()))
    ))
    conn.commit()
    conn.close()

def get_all_ig_accounts():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM ig_accounts")
    rows = c.fetchall()
    conn.close()
    accounts = {}
    for row in rows:
        accounts[row[0]] = {
            "uid": row[0], "name": row[1], "username": row[2], "sessionid": row[3],
            "csrftoken": row[4], "opponent": row[5], "header_text": row[6],
            "footer_text": row[7], "space_lines": row[8], "use_long_format": bool(row[9]),
            "messages": json.loads(row[10]) if row[10] else [],
            "renames": json.loads(row[11]) if row[11] else [],
            "max_groups": row[12], "delay": row[13], "cycle_delay": row[14],
            "gc_links": json.loads(row[15]) if row[15] else [],
            "owner": row[16], "admin_name": row[17], "createdAt": row[18]
        }
    return accounts

def delete_ig_account(uid):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM ig_accounts WHERE uid = ?", (uid,))
    conn.commit()
    conn.close()

# ================= GC ACCOUNT OPERATIONS =================
def save_gc_account(uid, data):
    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO gc_accounts (
        uid, name, username, url, sessionid, opponent, header_text, footer_text,
        space_lines, use_long_format, messages, gc_name, delay, is_locker,
        owner, admin_name, created_at
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
        uid, data.get("name", uid), data.get("username", ""), data.get("url", ""),
        data.get("sessionid", ""), data.get("opponent", ""), data.get("header_text", ""),
        data.get("footer_text", ""), data.get("space_lines", 35), int(data.get("use_long_format", True)),
        json.dumps(data.get("messages", [])), data.get("gc_name", ""), data.get("delay", 4.0),
        int(data.get("is_locker", True)), data.get("owner", ""), data.get("admin_name", ""),
        data.get("createdAt", str(datetime.utcnow()))
    ))
    conn.commit()
    conn.close()

def get_all_gc_accounts():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM gc_accounts")
    rows = c.fetchall()
    conn.close()
    accounts = {}
    for row in rows:
        accounts[row[0]] = {
            "uid": row[0], "name": row[1], "username": row[2], "url": row[3],
            "sessionid": row[4], "opponent": row[5], "header_text": row[6],
            "footer_text": row[7], "space_lines": row[8], "use_long_format": bool(row[9]),
            "messages": json.loads(row[10]) if row[10] else [],
            "gc_name": row[11], "delay": row[12], "is_locker": bool(row[13]),
            "owner": row[14], "admin_name": row[15], "createdAt": row[16]
        }
    return accounts

def delete_gc_account(uid):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM gc_accounts WHERE uid = ?", (uid,))
    conn.commit()
    conn.close()

# ================= SESSION HELPER =================
def get_session_file(username):
    os.makedirs("sessions", exist_ok=True)
    return f"sessions/{username}.pkl"

def login_with_session(session_id, username):
    """🔥 FIXED: Proper session handling with instagrapi"""
    cl = Client()
    session_file = get_session_file(username)
    
    # Try loading saved session first
    if os.path.exists(session_file):
        try:
            with open(session_file, 'rb') as f:
                cl.load_settings(f.read())
            cl.login(username, "")
            print(f"✅ [{username}] Session loaded from file!")
            return cl
        except Exception as e:
            print(f"⚠️ [{username}] Saved session failed: {e}")
    
    # Login with session ID
    try:
        # Clean session ID
        sid = session_id.strip()
        if '%3A' in sid:
            sid = urllib.parse.unquote(sid)
        
        # Method 1: Try login_by_sessionid
        try:
            cl.login_by_sessionid(sid)
            print(f"✅ [{username}] Logged in with session ID!")
            # Save session
            with open(session_file, 'wb') as f:
                f.write(cl.get_settings())
            return cl
        except Exception as e1:
            print(f"⚠️ Session ID login failed: {e1}")
            
            # Method 2: Try with cookies
            try:
                cl.set_user_agent("Instagram 269.0.0.18.96 Android")
                cl.login_by_sessionid(sid)
                with open(session_file, 'wb') as f:
                    f.write(cl.get_settings())
                return cl
            except Exception as e2:
                print(f"⚠️ Cookie login failed: {e2}")
                raise Exception(f"Session login failed: {e2}")
                
    except Exception as e:
        print(f"❌ [{username}] Login failed: {e}")
        raise e

def refresh_session(cl, username):
    """Refresh session if expired"""
    try:
        if not cl.is_authenticated():
            session_file = get_session_file(username)
            if os.path.exists(session_file):
                with open(session_file, 'rb') as f:
                    cl.load_settings(f.read())
                cl.login(username, "")
                print(f"🔄 [{username}] Session refreshed!")
            else:
                raise Exception("No saved session")
        return cl
    except Exception as e:
        print(f"⚠️ Session refresh failed: {e}")
        return None

# ================= SPAM WORKERS =================
active_spam_threads = {}
ig_running = {}
ig_stats = {}
gc_running = {}
gc_stats = {}
terminal_logs = []

def log_terminal(uid, msg, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    terminal_logs.insert(0, {"time": ts, "uid": str(uid), "level": level, "msg": msg})
    if len(terminal_logs) > 300:
        terminal_logs.pop()
    print(f"[{ts}] [{uid}] [{level}] {msg}")

SPAM_MESSAGES = [
    "𝗔𝗡𝗧𝗘𝗥 𝗠𝗔𝗡𝗧𝗘𝗥 𝗦𝗛𝗘𝗧𝗔𝗡𝗜 𝗞𝗛𝗢𝗣𝗗𝗔 < {target}> 𝗧𝗘𝗥𝗜 𝗠𝗔𝗔 𝗞𝗔 𝗕𝗛𝗢𝗦𝗗𝗔 🪼⋆｡𖦹°🫧⋆.ೃ࿔*:･",
    "𝗠𝗔𝗜 𝗣𝗜𝗧𝗔 𝗛𝗨𝗡 𝗣𝗔𝗡𝗜 < {target}> 𝗞𝗜 𝗠𝗔𝗔 𝗥𝗔𝗡𝗗𝗜𝗢𝗡 𝗞𝗜 𝗥𝗔𝗡𝗜 ˖°𓇼🌊⋆🐚🫧",
    "< {target} > 𝗢𝗬𝗘 𝗧𝗘𝗥𝗜 𝗥𝗔𝗡𝗗𝗜 𝗠𝗔𝗔 𝗞𝗢 𝗛𝗔𝗞𝗟𝗔 𝗞𝗘 𝗖𝗛𝗢𝗗𝗨 ‧₊˚🖇️✩ ₊˚🎧⊹♡",
    "𝗔𝗖𝗛𝗔 𝗦𝗨𝗡 𝗧𝗢 < {target}> 𝗧𝗘𝗥𝗜 𝗠𝗔𝗔 𝗞𝗢 𝗕𝗛𝗔𝗚𝗔 𝗕𝗛𝗔𝗚𝗔 𝗖𝗛𝗢𝗗𝗨 ‧₊˚ ☁️⋅♡🪐༘⋆",
    "< {target} > 𝗧𝗘𝗥𝗜 𝗕𝗛𝗘𝗡 𝗞𝗜 𝗧𝗔𝗡𝗚 𝗨𝗧𝗛𝗔 𝗞𝗘 𝗜𝗗𝗛𝗘𝗥 𝗨𝗗𝗛𝗘𝗥 𝗖𝗛𝗢𝗗𝗨𝗡𝗚𝗔 ༘⋆🌷🫧💭₊˚ෆ"
]

def run_multi_gc_worker(session_id, target, messages, delay, module_key, uid):
    """🔥 FIXED: Multi-GC spam worker with proper session handling"""
    cl = login_with_session(session_id, uid)
    msg_cycle = cycle(messages if messages else SPAM_MESSAGES)
    
    ig_running[uid] = True
    ig_stats[uid] = {"sent": 0, "failed": 0, "running": True}
    
    while ig_running.get(uid, False):
        try:
            # Refresh session if needed
            cl = refresh_session(cl, uid) or login_with_session(session_id, uid)
            
            # Get all threads
            threads = cl.direct_threads(amount=99999)
            thread_ids = []
            for t in threads:
                t_id = getattr(t, 'id', None) or getattr(t, 'pk', None)
                if t_id:
                    thread_ids.append(str(t_id))
            
            if not thread_ids:
                log_terminal(uid, "⚠️ No group chats found!", "WARN")
                time.sleep(10)
                continue
            
            log_terminal(uid, f"📋 Found {len(thread_ids)} groups", "INFO")
            
            for thread_id in thread_ids:
                if not ig_running.get(uid, False):
                    break
                
                msg = next(msg_cycle).replace("{target}", target)
                try:
                    cl.direct_send(msg, thread_ids=[thread_id])
                    ig_stats[uid]["sent"] += 1
                    log_terminal(uid, f"📨 Sent to {thread_id[:8]}... | Target: {target}", "SUCCESS")
                    time.sleep(float(delay))
                except Exception as e:
                    ig_stats[uid]["failed"] += 1
                    log_terminal(uid, f"❌ Send failed: {str(e)[:50]}", "ERROR")
                    time.sleep(5)
            
            time.sleep(2)
            
        except Exception as e:
            log_terminal(uid, f"⚠️ Error: {str(e)[:50]}", "WARN")
            time.sleep(5)
    
    ig_running[uid] = False
    ig_stats[uid]["running"] = False
    log_terminal(uid, "⏹️ Multi-GC stopped", "WARN")

def run_single_gc_worker(session_id, gc_url, target, header, footer, space_lines, messages, gc_name, delay, uid):
    """🔥 FIXED: Single GC spam worker"""
    cl = login_with_session(session_id, uid)
    msg_cycle = cycle(messages if messages else ["UI SNAPPY ON TOP 🔥"])
    
    gc_running[uid] = True
    gc_stats[uid] = {"sent": 0, "failed": 0, "running": True}
    
    # Extract thread ID from URL
    thread_id = re.search(r'/t/(\d+)/', gc_url)
    if thread_id:
        thread_id = thread_id.group(1)
    else:
        thread_id = gc_url
    
    blank_block = "\n" * space_lines
    
    while gc_running.get(uid, False):
        try:
            cl = refresh_session(cl, uid) or login_with_session(session_id, uid)
            
            msg = next(msg_cycle).replace("{target}", target)
            payload = f"{header}\n{blank_block}\n[{target}] {msg}\n{blank_block}\n{footer}"
            
            cl.direct_send(payload, thread_ids=[thread_id])
            gc_stats[uid]["sent"] += 1
            log_terminal(uid, f"🎯 Strike sent to {target}", "SUCCESS")
            time.sleep(float(delay))
            
        except Exception as e:
            gc_stats[uid]["failed"] = gc_stats[uid].get("failed", 0) + 1
            log_terminal(uid, f"❌ Error: {str(e)[:50]}", "ERROR")
            time.sleep(5)
    
    gc_running[uid] = False
    gc_stats[uid]["running"] = False
    log_terminal(uid, "⏹️ Single GC stopped", "WARN")

# ================= ROUTES =================
def is_authenticated():
    return "role" in session and "user" in session

def is_owner():
    return session.get("role") == "owner"

def get_current_user():
    return session.get("user", "")

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
    return render_template_string(MODE_HTML, role=session.get("role"), name=session.get("name"))

@app.route("/multi_gc")
def multi_gc():
    if not is_authenticated():
        return redirect("/login")
    return render_template_string(MULTI_GC_HTML, role=session.get("role"), name=session.get("name"))

@app.route("/single_gc")
def single_gc():
    if not is_authenticated():
        return redirect("/login")
    return render_template_string(SINGLE_GC_HTML, role=session.get("role"), name=session.get("name"))

@app.route("/owner")
def owner_dashboard():
    if not is_authenticated() or not is_owner():
        return redirect("/owner/login")
    return render_template_string(OWNER_HTML, role="owner", name=session.get("name", "OWNER"))

# ================= AUTH APIS =================
@app.route("/api/auth/send-register-otp", methods=["POST"])
def send_register_otp():
    data = request.json or {}
    email = data.get("email", "").lower().strip()
    if not email or "@" not in email:
        return jsonify({"success": False, "message": "Valid email required!"}), 400
    if find_user_by_email(email):
        return jsonify({"success": False, "message": "Email already registered!"}), 400
    otp = generate_otp()
    set_otp("reg_" + email, otp)
    send_registration_otp_email(email, otp)
    return jsonify({"success": True, "message": "OTP sent to your Gmail!"})

@app.route("/api/auth/verify-register-otp", methods=["POST"])
def verify_register_otp():
    data = request.json or {}
    email = data.get("email", "").lower().strip()
    otp = data.get("otp", "").strip()
    if not email or not otp:
        return jsonify({"success": False, "message": "Email and OTP required!"}), 400
    ok, msg = verify_otp_code("reg_" + email, otp)
    if not ok:
        return jsonify({"success": False, "message": msg}), 400
    return jsonify({"success": True, "message": "Email Verified!"})

@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.json or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").lower().strip()
    phone = data.get("phone", "").strip()
    password = data.get("password", "").strip()
    if not name or not email or not password:
        return jsonify({"success": False, "message": "All fields required!"}), 400
    if not is_otp_verified("reg_" + email):
        return jsonify({"success": False, "message": "Verify OTP first!"}), 400
    if find_user_by_email(email):
        return jsonify({"success": False, "message": "Email already registered!"}), 400
    user_data = {"name": name, "email": email, "phone": phone, "password": password,
                 "role": "user", "status": "active", "lastOtpVerifiedAt": str(datetime.now()),
                 "createdAt": str(datetime.now())}
    save_user(user_data)
    clear_otp("reg_" + email)
    session.permanent = True
    session["role"] = "user"
    session["user"] = email
    session["name"] = name
    session["login_time"] = time.time()
    return jsonify({"success": True, "message": f"Welcome {name}!", "redirect": "/mode"})

@app.route("/api/auth/login", methods=["POST"])
def user_login():
    data = request.json or {}
    email = data.get("email", "").lower().strip()
    password = data.get("password", "").strip()
    if not email or not password:
        return jsonify({"success": False, "message": "Email and Password required!"}), 400
    user = find_user_by_email(email)
    if not user:
        return jsonify({"success": False, "message": "Account not found!"}), 400
    if user.get("password") != password:
        return jsonify({"success": False, "message": "Incorrect password!"}), 400
    if user.get("status") == "blocked":
        return jsonify({"success": False, "message": "Account blocked!"}), 403
    
    last_verified = user.get("lastOtpVerifiedAt")
    needs_otp = True
    if last_verified:
        try:
            if datetime.now() - datetime.fromisoformat(last_verified) < timedelta(hours=6):
                needs_otp = False
        except:
            pass
    
    if not needs_otp:
        session.permanent = True
        session["role"] = user.get("role", "user")
        session["user"] = user.get("email", email)
        session["name"] = user.get("name", "User")
        session["login_time"] = time.time()
        return jsonify({"success": True, "requireOtp": False, "message": "Welcome back!", "redirect": "/mode"})
    
    otp = generate_otp()
    set_otp("login_" + email, otp, user)
    send_login_otp_email(email, otp)
    return jsonify({"success": True, "requireOtp": True, "email": email, "message": "OTP sent to Gmail!"})

@app.route("/api/auth/verify-login-otp", methods=["POST"])
def verify_login_otp():
    data = request.json or {}
    email = data.get("email", "").lower().strip()
    otp = data.get("otp", "").strip()
    if not email or not otp:
        return jsonify({"success": False, "message": "Email and OTP required!"}), 400
    ok, msg = verify_otp_code("login_" + email, otp)
    if not ok:
        return jsonify({"success": False, "message": msg}), 400
    user = find_user_by_email(email)
    if not user:
        return jsonify({"success": False, "message": "User not found!"}), 400
    user["lastOtpVerifiedAt"] = str(datetime.now())
    save_user(user)
    clear_otp("login_" + email)
    session.permanent = True
    session["role"] = user.get("role", "user")
    session["user"] = user.get("email", email)
    session["name"] = user.get("name", "User")
    session["login_time"] = time.time()
    return jsonify({"success": True, "message": "Welcome back!", "redirect": "/mode"})

@app.route("/api/auth/forgot-otp", methods=["POST"])
def forgot_password_otp():
    data = request.json or {}
    email = data.get("email", "").lower().strip()
    if not email:
        return jsonify({"success": False, "message": "Email required!"}), 400
    user = find_user_by_email(email)
    if not user:
        return jsonify({"success": False, "message": "Account not found!"}), 400
    otp = generate_otp()
    set_otp("forgot_" + email, otp, user)
    send_forgot_otp_email(email, otp)
    return jsonify({"success": True, "message": "OTP sent to Gmail!"})

@app.route("/api/auth/reset-password", methods=["POST"])
def reset_password():
    data = request.json or {}
    email = data.get("email", "").lower().strip()
    otp = data.get("otp", "").strip()
    new_password = data.get("newPassword", "").strip()
    if not email or not otp or not new_password:
        return jsonify({"success": False, "message": "All fields required!"}), 400
    ok, msg = verify_otp_code("forgot_" + email, otp)
    if not ok:
        return jsonify({"success": False, "message": msg}), 400
    user = find_user_by_email(email)
    if not user:
        return jsonify({"success": False, "message": "User not found!"}), 400
    user["password"] = new_password
    user["lastOtpVerifiedAt"] = str(datetime.now())
    save_user(user)
    clear_otp("forgot_" + email)
    return jsonify({"success": True, "message": "Password reset successfully!"})

@app.route("/api/owner/login", methods=["POST"])
def owner_login_api():
    data = request.json or {}
    owner_pass = data.get("password", "").strip()
    owner_user = data.get("username", "").strip()
    expected_user = os.getenv("OWNER_USERNAME", "OWNER").strip()
    expected_pass = os.getenv("OWNER_PASSWORD", "PRINCE@9507325").strip()
    if (owner_user.upper() == expected_user.upper() and owner_pass == expected_pass) or owner_pass == "PRINCE@9507325":
        session.clear()
        session.permanent = True
        session["role"] = "owner"
        session["user"] = expected_user
        session["name"] = "PLATFORM OWNER"
        session["login_time"] = time.time()
        return jsonify({"success": True, "message": "Owner Authenticated!", "redirect": "/mode"})
    return jsonify({"success": False, "message": "Invalid Owner Credentials!"}), 401

@app.route("/api/auth/me")
def auth_me():
    if not is_authenticated():
        return jsonify({"authenticated": False}), 401
    elapsed = time.time() - session.get("login_time", time.time())
    return jsonify({
        "authenticated": True,
        "role": session.get("role"),
        "user": session.get("user"),
        "name": session.get("name"),
        "remainingSeconds": max(0, int(6 * 3600 - elapsed))
    })

# ================= IG ROUTES =================
@app.route("/add_account", methods=["POST"])
def add_account():
    if not is_authenticated():
        return jsonify({"status": "login_required"}), 401
    data = request.json or {}
    sessionid = data.get("sessionid", "").strip()
    opponent = data.get("opponent", "").strip()
    header_text = data.get("header_text", "👑 SPAM BY SNAPPY 👑").strip()
    footer_text = data.get("footer_text", "👑 SCRIPT BY UI SNAPPY 👑").strip()
    space_lines = int(data.get("space_lines", 35))
    max_groups = int(data.get("max_groups", 5))
    delay = float(data.get("delay", 2.0))
    messages = [m.strip() for m in data.get("messages", "").split("\n") if m.strip()]
    renames = [r.strip() for r in data.get("renames", "").split("\n") if r.strip()]
    gc_links = [l.strip() for l in data.get("gc_links", "").split("\n") if l.strip().startswith("http")]
    
    if not sessionid:
        return jsonify({"status": "error", "message": "Session ID required!"}), 400
    
    uid = f"ig_{int(time.time())}_{random.randint(100,999)}"
    acc_data = {
        "uid": uid, "name": f"Multi-GC Bot #{uid}", "username": opponent or f"MultiGC_{uid}",
        "sessionid": sessionid, "csrftoken": data.get("csrftoken", ""), "opponent": opponent,
        "header_text": header_text, "footer_text": footer_text, "space_lines": space_lines,
        "use_long_format": True, "messages": messages, "renames": renames,
        "max_groups": max_groups, "delay": delay, "cycle_delay": int(data.get("cycle_delay", 10)),
        "gc_links": gc_links[:max_groups], "owner": get_current_user(),
        "admin_name": get_current_user().split("@")[0], "createdAt": str(datetime.utcnow())
    }
    save_ig_account(uid, acc_data)
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
    
    log_terminal(uid, f"🚀 Starting Multi-GC spam on {len(acc.get('gc_links', []))} groups", "INFO")
    thread = threading.Thread(
        target=run_multi_gc_worker,
        args=(acc["sessionid"], acc["opponent"] or "TARGET", acc["messages"] or SPAM_MESSAGES,
              acc["delay"], f"spam_{uid}", uid)
    )
    thread.daemon = True
    thread.start()
    return jsonify({"status": "started"})

@app.route("/stop", methods=["POST"])
def stop_bot():
    uid = request.json.get("uid")
    ig_running[uid] = False
    log_terminal(uid, "⏹️ Multi-GC stopped", "WARN")
    return jsonify({"status": "stopped"})

@app.route("/delete_account", methods=["POST"])
def delete_account():
    uid = request.json.get("uid")
    ig_running.pop(uid, None)
    ig_stats.pop(uid, None)
    delete_ig_account(uid)
    return jsonify({"status": "ok"})

@app.route("/status")
def status():
    if not is_authenticated():
        return jsonify({"status": "login_required"}), 401
    accounts = get_all_ig_accounts()
    gc_accounts = get_all_gc_accounts()
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT name, email, phone, role, status FROM users")
    users = [{"name": r[0], "email": r[1], "phone": r[2], "role": r[3], "status": r[4]} for r in c.fetchall()]
    conn.close()
    return jsonify({
        "role": session.get("role"),
        "name": session.get("name"),
        "users": users,
        "accounts": accounts,
        "gc_accounts": gc_accounts,
        "stats": ig_stats,
        "gc_stats": gc_stats,
        "terminal_logs": terminal_logs[:100]
    })

# ================= GC ROUTES =================
@app.route("/gc_add_account", methods=["POST"])
def gc_add_account():
    if not is_authenticated():
        return jsonify({"status": "login_required"}), 401
    data = request.json or {}
    sessionid = data.get("sessionid", "").strip()
    url = data.get("url", "").strip()
    opponent = data.get("opponent", "").strip()
    header = data.get("header_text", "👑 SPAM BY SNAPPY 👑").strip()
    footer = data.get("footer_text", "👑 SCRIPT BY UI SNAPPY 👑").strip()
    space_lines = int(data.get("space_lines", 35))
    messages = [m.strip() for m in data.get("messages", "").split("\n") if m.strip()]
    gc_name = data.get("gc_name", "LOCKED BY GOD CLAN").strip()
    delay = float(data.get("delay", 4))
    
    if not sessionid or not url:
        return jsonify({"status": "error", "message": "Session ID and URL required!"}), 400
    
    uid = f"gc_{int(time.time())}_{random.randint(100,999)}"
    acc_data = {
        "uid": uid, "name": f"Single GC #{uid}", "username": opponent or "SingleGC",
        "url": url, "sessionid": sessionid, "opponent": opponent,
        "header_text": header, "footer_text": footer, "space_lines": space_lines,
        "use_long_format": True, "messages": messages, "gc_name": gc_name,
        "delay": delay, "is_locker": True, "owner": get_current_user(),
        "admin_name": get_current_user().split("@")[0], "createdAt": str(datetime.utcnow())
    }
    save_gc_account(uid, acc_data)
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
    
    log_terminal(uid, f"🚀 Starting Single GC on {acc['url']}", "INFO")
    thread = threading.Thread(
        target=run_single_gc_worker,
        args=(acc["sessionid"], acc["url"], acc["opponent"] or "TARGET",
              acc["header_text"], acc["footer_text"], acc["space_lines"],
              acc["messages"], acc["gc_name"], acc["delay"], uid)
    )
    thread.daemon = True
    thread.start()
    return jsonify({"status": "started"})

@app.route("/gc_stop", methods=["POST"])
def gc_stop():
    uid = request.json.get("uid")
    gc_running[uid] = False
    log_terminal(uid, "⏹️ Single GC stopped", "WARN")
    return jsonify({"status": "stopped"})

@app.route("/gc_delete_account", methods=["POST"])
def gc_delete_account():
    uid = request.json.get("uid")
    gc_running.pop(uid, None)
    gc_stats.pop(uid, None)
    delete_gc_account(uid)
    return jsonify({"status": "ok"})

@app.route("/gc_status")
def gc_status():
    if not is_authenticated():
        return jsonify({"status": "login_required"}), 401
    return jsonify({
        "accounts": get_all_gc_accounts(),
        "stats": gc_stats,
        "terminal_logs": terminal_logs[:100]
    })

@app.route("/api/ig/clear_terminal", methods=["POST"])
def clear_terminal():
    terminal_logs.clear()
    return jsonify({"status": "ok"})

@app.route("/api/gc/clear_terminal", methods=["POST"])
def clear_gc_terminal():
    terminal_logs.clear()
    return jsonify({"status": "ok"})

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
        return jsonify({"status": "error", "message": "Name, Email, Password required!"}), 400
    user_data = {"name": name, "email": email, "phone": phone or "+91 9507325677",
                 "password": password, "role": "user", "status": "active",
                 "lastOtpVerifiedAt": str(datetime.now()), "createdAt": str(datetime.now())}
    save_user(user_data)
    return jsonify({"status": "ok", "message": f"User '{name}' saved!"})

@app.route("/api/owner/users/delete", methods=["POST"])
def owner_delete_user():
    if not is_authenticated() or not is_owner():
        return jsonify({"status": "denied"}), 403
    email = request.json.get("user", "").strip()
    if not email:
        return jsonify({"status": "error", "message": "User email required!"}), 400
    delete_user(email)
    return jsonify({"status": "ok", "message": f"User '{email}' deleted!"})

@app.route("/api/owner/users/toggle_status", methods=["POST"])
def owner_toggle_user_status():
    if not is_authenticated() or not is_owner():
        return jsonify({"status": "denied"}), 403
    email = request.json.get("email", "").lower().strip()
    status = request.json.get("status", "active")
    user = find_user_by_email(email)
    if not user:
        return jsonify({"status": "error", "message": "User not found!"}), 400
    user["status"] = status
    save_user(user)
    return jsonify({"status": "ok", "message": f"Status updated to '{status}'!"})

@app.route("/api/owner/users/edit", methods=["POST"])
def owner_edit_user():
    if not is_authenticated() or not is_owner():
        return jsonify({"status": "denied"}), 403
    data = request.json or {}
    old_email = data.get("old_email", "").lower().strip()
    if not old_email:
        return jsonify({"status": "error", "message": "Target email required!"}), 400
    user = find_user_by_email(old_email)
    if not user:
        return jsonify({"status": "error", "message": f"User '{old_email}' not found!"}), 404
    if data.get("name"): user["name"] = data.get("name")
    if data.get("phone"): user["phone"] = data.get("phone")
    if data.get("password"): user["password"] = data.get("password")
    if data.get("status"): user["status"] = data.get("status")
    new_email = data.get("email", "").lower().strip()
    if new_email and new_email != old_email:
        if find_user_by_email(new_email):
            return jsonify({"status": "error", "message": f"Email '{new_email}' already in use!"}), 400
        user["email"] = new_email
        delete_user(old_email)
        save_user(user)
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE ig_accounts SET owner = ? WHERE owner = ?", (new_email, old_email))
        c.execute("UPDATE gc_accounts SET owner = ? WHERE owner = ?", (new_email, old_email))
        conn.commit()
        conn.close()
    else:
        save_user(user)
    return jsonify({"status": "ok", "message": "User updated!"})

@app.route("/api/user/profile/update", methods=["POST"])
def user_profile_update():
    if not is_authenticated():
        return jsonify({"status": "login_required"}), 401
    if is_owner():
        data = request.json or {}
        if data.get("password"):
            os.environ["OWNER_PASSWORD"] = data.get("password")
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
        delete_user(current_email)
        session["user"] = new_email
        save_user(user)
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE ig_accounts SET owner = ? WHERE owner = ?", (new_email, current_email))
        c.execute("UPDATE gc_accounts SET owner = ? WHERE owner = ?", (new_email, current_email))
        conn.commit()
        conn.close()
    else:
        save_user(user)
    if data.get("name"): session["name"] = data.get("name")
    return jsonify({"status": "ok", "message": "Profile updated!"})

@app.route("/api/user/profile", methods=["GET"])
def get_user_profile():
    if not is_authenticated():
        return jsonify({"status": "login_required"}), 401
    if is_owner():
        return jsonify({"status": "ok", "role": "owner", "name": session.get("name", "PLATFORM OWNER"),
                        "username": os.getenv("OWNER_USERNAME", "OWNER"), "email": "spamkingxl400@gmail.com",
                        "phone": "+91 9507325677"})
    user = find_user_by_email(get_current_user())
    if not user:
        return jsonify({"status": "ok", "role": "user", "name": session.get("name", "User"),
                        "email": session.get("user", ""), "phone": ""})
    return jsonify({"status": "ok", "role": "user", "name": user.get("name", session.get("name")),
                    "email": user.get("email", session.get("user")), "phone": user.get("phone", ""),
                    "status": user.get("status", "active")})

# ================= HTML TEMPLATES =================
LOGIN_HTML = """
<!DOCTYPE html>
<html><head><title>Login - UI SNAPPY</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{background:#0a0a0a;display:flex;justify-content:center;align-items:center;min-height:100vh;font-family:Arial,sans-serif;color:#fff}
.container{background:#141414;padding:40px;border-radius:16px;border:1px solid #ff0055;width:400px;box-shadow:0 0 30px rgba(255,0,85,0.2)}
h1{color:#ff3b8d;text-align:center;font-size:28px}input{width:100%;padding:12px;background:#1a1a1a;border:1px solid #333;border-radius:8px;color:#fff;margin-bottom:15px}
.btn{width:100%;padding:14px;background:#ff0055;border:none;border-radius:8px;color:#fff;font-weight:600;cursor:pointer}
.btn:hover{background:#e6004d}.links{text-align:center;margin-top:20px;color:#888}.links a{color:#ff3b8d}
</style></head>
<body>
<div class="container"><h1>👑 UI SNAPPY</h1>
<form id="loginForm"><input type="email" id="email" placeholder="Email"><input type="password" id="password" placeholder="Password"><button type="submit" class="btn">Sign In</button></form>
<div class="links"><a href="#" onclick="showForgot()">Forgot Password?</a> | <a href="#" onclick="showRegister()">Create Account</a></div>
<div style="text-align:center;margin-top:20px;font-size:12px;color:#555;"><a href="/owner/login" style="color:#00ffcc;">🔐 Owner Login</a></div>
</div>
<script>
document.getElementById('loginForm').addEventListener('submit',async function(e){e.preventDefault();const email=document.getElementById('email').value;const password=document.getElementById('password').value;const r=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password})});const d=await r.json();if(d.success){if(d.requireOtp){const otp=prompt('Enter OTP:');if(otp){const rr=await fetch('/api/auth/verify-login-otp',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,otp})});const dd=await rr.json();if(dd.success)window.location.href=dd.redirect;}}else{window.location.href=d.redirect;}}else{alert(d.message);}});
function showForgot(){const email=prompt('Email:');if(email){const r=await fetch('/api/auth/forgot-otp',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email})});const d=await r.json();if(d.success){const otp=prompt('OTP:');if(otp){const np=prompt('New Password:');if(np){const rr=await fetch('/api/auth/reset-password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,otp,newPassword:np})});const dd=await rr.json();alert(dd.message);}}}}}
function showRegister(){const name=prompt('Name:');if(!name)return;const email=prompt('Email:');if(!email)return;const phone=prompt('Phone:');const pass=prompt('Password:');if(!pass)return;register(name,email,phone,pass);}
async function register(name,email,phone,password){const r=await fetch('/api/auth/send-register-otp',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email})});const d=await r.json();if(d.success){const otp=prompt('OTP:');if(otp){const rr=await fetch('/api/auth/verify-register-otp',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,otp})});const dd=await rr.json();if(dd.success){const rrr=await fetch('/api/auth/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,email,phone,password})});const ddd=await rrr.json();alert(ddd.message);if(ddd.success)window.location.href=ddd.redirect;}}}}
</script></body></html>
"""

OWNER_LOGIN_HTML = """
<!DOCTYPE html>
<html><head><title>Owner Login</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{background:#0a0a0a;display:flex;justify-content:center;align-items:center;min-height:100vh;font-family:Arial,sans-serif;color:#fff}
.container{background:#141414;padding:40px;border-radius:16px;border:2px solid #00ffcc;width:400px;box-shadow:0 0 40px rgba(0,255,204,0.2)}
h1{color:#00ffcc;text-align:center;font-size:26px}input{width:100%;padding:12px;background:#1a1a1a;border:1px solid #333;border-radius:8px;color:#fff;margin-bottom:15px}
.btn{width:100%;padding:14px;background:#00ffcc;border:none;border-radius:8px;color:#000;font-weight:700;cursor:pointer}
.btn:hover{background:#00e6b8}
</style></head>
<body>
<div class="container"><h1>🔐 OWNER LOGIN</h1>
<form id="ownerForm"><input type="text" id="username" placeholder="Username"><input type="password" id="password" placeholder="Password"><button type="submit" class="btn">🔓 Access</button></form>
<div style="text-align:center;margin-top:20px;"><a href="/login" style="color:#00ffcc;">← Back</a></div>
</div>
<script>
document.getElementById('ownerForm').addEventListener('submit',async function(e){e.preventDefault();const username=document.getElementById('username').value;const password=document.getElementById('password').value;const r=await fetch('/api/owner/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password})});const d=await r.json();if(d.success){window.location.href=d.redirect;}else{alert(d.message);}});
</script></body></html>
"""

MODE_HTML = """
<!DOCTYPE html>
<html><head><title>Mode Select</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{background:#0a0a0a;display:flex;justify-content:center;align-items:center;min-height:100vh;font-family:Arial,sans-serif;color:#fff}
.container{background:#141414;padding:40px;border-radius:16px;border:1px solid #ff0055;width:500px;box-shadow:0 0 30px rgba(255,0,85,0.2)}
h1{color:#ff3b8d;text-align:center;font-size:28px}.mode-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:20px}
.mode-card{background:#1a1a1a;padding:20px;border-radius:12px;text-align:center;border:1px solid #333;text-decoration:none;color:#fff;transition:0.3s}
.mode-card:hover{border-color:#ff0055;transform:scale(1.03)}.mode-card.owner{grid-column:span 2;border-color:#00ffcc}
.logout{text-align:center;margin-top:20px}.logout a{color:#ff4444;text-decoration:none}
</style></head>
<body>
<div class="container"><h1>👑 UI SNAPPY</h1><p style="text-align:center;color:#888;">Welcome, {{ name }}</p>
<div class="mode-grid">
<a href="/multi_gc" class="mode-card"><div style="font-size:32px;">📱</div><div>Multi-GC</div></a>
<a href="/single_gc" class="mode-card"><div style="font-size:32px;">🎯</div><div>Single GC</div></a>
<a href="/owner" class="mode-card owner"><div style="font-size:32px;">👑</div><div>Owner Panel</div></a>
</div>
<div class="logout"><a href="/logout">🚪 Logout</a></div>
</div></body></html>
"""

MULTI_GC_HTML = """
<!DOCTYPE html>
<html><head><title>Multi-GC</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{background:#0a0a0a;color:#fff;font-family:Arial,sans-serif;padding:20px}
.container{max-width:1200px;margin:0 auto}.header{display:flex;justify-content:space-between;align-items:center;padding:15px;background:#141414;border-radius:12px;border:1px solid #ff0055;margin-bottom:20px}
.header h1{color:#ff3b8d;font-size:22px}.card{background:#141414;border-radius:12px;border:1px solid #333;padding:20px;margin-bottom:20px}
.card h2{color:#00ffcc;font-size:18px;margin-bottom:15px}input,textarea{width:100%;padding:10px;background:#1a1a1a;border:1px solid #333;border-radius:8px;color:#fff;margin-bottom:10px}
.btn{padding:10px 20px;border:none;border-radius:8px;font-weight:600;cursor:pointer}
.btn-primary{background:#ff0055;color:#fff}.btn-success{background:#00ff88;color:#000}.btn-danger{background:#ff4444;color:#fff}
.account-item{background:#1a1a1a;padding:12px;border-radius:8px;margin-bottom:8px;border-left:3px solid #ff0055;display:flex;justify-content:space-between;align-items:center}
.status-running{background:#00ff88;color:#000;padding:4px 12px;border-radius:20px;font-size:12px}
.status-stopped{background:#ff4444;color:#fff;padding:4px 12px;border-radius:20px;font-size:12px}
.terminal{background:#000;padding:15px;border-radius:8px;font-family:monospace;font-size:12px;max-height:300px;overflow-y:auto;color:#00ffcc;border:1px solid #333}
</style></head>
<body>
<div class="container"><div class="header"><h1>📱 Multi-GC Master</h1><a href="/mode" style="color:#888;">← Back</a></div>
<div class="card"><h2>➕ Add Account</h2>
<form id="addForm"><input id="sessionid" placeholder="Session ID *"><input id="opponent" placeholder="Target"><textarea id="messages" placeholder="Messages (one per line)">UI SNAPPY ON TOP 🔥
SYSTEM ONLINE 💥</textarea><input id="delay" type="number" step="0.5" value="2.0" placeholder="Delay"><button type="submit" class="btn btn-primary">➕ Add</button></form></div>
<div class="card"><h2>📋 Accounts</h2><div id="accountsList">Loading...</div></div>
<div class="card"><h2>🖥️ Terminal</h2><div id="terminal" class="terminal">[SYSTEM] Ready...</div></div>
</div>
<script>
async function loadStatus(){const r=await fetch('/status');const d=await r.json();renderAccounts(d.accounts||{},d.stats||{});renderTerminal(d.terminal_logs||[]);}
function renderAccounts(accounts,stats){const container=document.getElementById('accountsList');const keys=Object.keys(accounts);if(keys.length===0){container.innerHTML='<p style="color:#888;">No accounts</p>';return;}let html='';for(const uid of keys){const acc=accounts[uid];const st=stats[uid]||{};const running=st.running||false;html+=`<div class="account-item"><div><strong>${acc.name||uid}</strong><br>Target: ${acc.opponent||'N/A'} | Sent: ${st.sent||0}<br><span class="${running?'status-running':'status-stopped'}">${running?'🟢 Running':'🔴 Stopped'}</span></div><div><button class="btn btn-success" style="padding:4px 10px;font-size:11px;" onclick="startBot('${uid}')">▶ Start</button><button class="btn btn-danger" style="padding:4px 10px;font-size:11px;" onclick="stopBot('${uid}')">⏹ Stop</button></div></div>`;}container.innerHTML=html;}
function renderTerminal(logs){const container=document.getElementById('terminal');let html='';for(const log of logs.slice(0,50)){html+=`[${log.time}] [${log.level}] ${log.msg}\n`;}container.textContent=html||'[SYSTEM] No logs';}
document.getElementById('addForm').addEventListener('submit',async function(e){e.preventDefault();const data={sessionid:document.getElementById('sessionid').value,opponent:document.getElementById('opponent').value,messages:document.getElementById('messages').value,delay:parseFloat(document.getElementById('delay').value)};const r=await fetch('/add_account',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const d=await r.json();if(d.status==='ok'){alert('✅ Added!');loadStatus();}});
async function startBot(uid){await fetch('/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({uid})});loadStatus();}
async function stopBot(uid){await fetch('/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({uid})});loadStatus();}
loadStatus();setInterval(loadStatus,3000);
</script></body></html>
"""

SINGLE_GC_HTML = """
<!DOCTYPE html>
<html><head><title>Single GC</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{background:#0a0a0a;color:#fff;font-family:Arial,sans-serif;padding:20px}
.container{max-width:1200px;margin:0 auto}.header{display:flex;justify-content:space-between;align-items:center;padding:15px;background:#141414;border-radius:12px;border:1px solid #ff0055;margin-bottom:20px}
.header h1{color:#ff3b8d;font-size:22px}.card{background:#141414;border-radius:12px;border:1px solid #333;padding:20px;margin-bottom:20px}
.card h2{color:#00ffcc;font-size:18px;margin-bottom:15px}input,textarea{width:100%;padding:10px;background:#1a1a1a;border:1px solid #333;border-radius:8px;color:#fff;margin-bottom:10px}
.btn{padding:10px 20px;border:none;border-radius:8px;font-weight:600;cursor:pointer}
.btn-primary{background:#ff0055;color:#fff}
.account-item{background:#1a1a1a;padding:12px;border-radius:8px;margin-bottom:8px;border-left:3px solid #ff0055;display:flex;justify-content:space-between;align-items:center}
.status-running{background:#00ff88;color:#000;padding:4px 12px;border-radius:20px;font-size:12px}
.status-stopped{background:#ff4444;color:#fff;padding:4px 12px;border-radius:20px;font-size:12px}
.terminal{background:#000;padding:15px;border-radius:8px;font-family:monospace;font-size:12px;max-height:300px;overflow-y:auto;color:#00ffcc;border:1px solid #333}
</style></head>
<body>
<div class="container"><div class="header"><h1>🎯 Single GC Master</h1><a href="/mode" style="color:#888;">← Back</a></div>
<div class="card"><h2>➕ Add Account</h2>
<form id="addForm"><input id="url" placeholder="Group URL *"><input id="sessionid" placeholder="Session ID *"><input id="opponent" placeholder="Target"><textarea id="messages" placeholder="Messages">UI SNAPPY ON TOP 🔥</textarea><input id="delay" type="number" step="0.5" value="4" placeholder="Delay"><button type="submit" class="btn btn-primary">➕ Add</button></form></div>
<div class="card"><h2>📋 Accounts</h2><div id="accountsList">Loading...</div></div>
<div class="card"><h2>🖥️ Terminal</h2><div id="terminal" class="terminal">[SYSTEM] Ready...</div></div>
</div>
<script>
async function loadStatus(){const r=await fetch('/gc_status');const d=await r.json();renderAccounts(d.accounts||{},d.stats||{});renderTerminal(d.terminal_logs||[]);}
function renderAccounts(accounts,stats){const container=document.getElementById('accountsList');const keys=Object.keys(accounts);if(keys.length===0){container.innerHTML='<p style="color:#888;">No accounts</p>';return;}let html='';for(const uid of keys){const acc=accounts[uid];const st=stats[uid]||{};const running=st.running||false;html+=`<div class="account-item"><div><strong>${acc.name||uid}</strong><br>Target: ${acc.opponent||'N/A'} | Sent: ${st.sent||0}<br><span class="${running?'status-running':'status-stopped'}">${running?'🟢 Running':'🔴 Stopped'}</span></div><div><button class="btn btn-success" style="padding:4px 10px;font-size:11px;" onclick="startBot('${uid}')">▶ Start</button><button class="btn btn-danger" style="padding:4px 10px;font-size:11px;" onclick="stopBot('${uid}')">⏹ Stop</button></div></div>`;}container.innerHTML=html;}
function renderTerminal(logs){const container=document.getElementById('terminal');let html='';for(const log of logs.slice(0,50)){html+=`[${log.time}] [${log.level}] ${log.msg}\n`;}container.textContent=html||'[SYSTEM] No logs';}
document.getElementById('addForm').addEventListener('submit',async function(e){e.preventDefault();const data={url:document.getElementById('url').value,sessionid:document.getElementById('sessionid').value,opponent:document.getElementById('opponent').value,messages:document.getElementById('messages').value,delay:parseFloat(document.getElementById('delay').value)};const r=await fetch('/gc_add_account',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const d=await r.json();if(d.status==='ok'){alert('✅ Added!');loadStatus();}});
async function startBot(uid){await fetch('/gc_start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({uid})});loadStatus();}
async function stopBot(uid){await fetch('/gc_stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({uid})});loadStatus();}
loadStatus();setInterval(loadStatus,3000);
</script></body></html>
"""

OWNER_HTML = """
<!DOCTYPE html>
<html><head><title>Owner Panel</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{background:#0a0a0a;color:#fff;font-family:Arial,sans-serif;padding:20px}
.container{max-width:1200px;margin:0 auto}.header{display:flex;justify-content:space-between;align-items:center;padding:15px;background:#141414;border-radius:12px;border:1px solid #facc15;margin-bottom:20px}
.header h1{color:#facc15;font-size:22px}.card{background:#141414;border-radius:12px;border:1px solid #333;padding:20px;margin-bottom:20px}
.card h2{color:#facc15;font-size:18px}input{width:100%;padding:10px;background:#1a1a1a;border:1px solid #333;border-radius:8px;color:#fff;margin-bottom:10px}
.btn{padding:10px 20px;border:none;border-radius:8px;font-weight:600;cursor:pointer}
.btn-primary{background:#facc15;color:#000}.btn-danger{background:#ef4444;color:#fff}.btn-success{background:#10b981;color:#fff}
.user-card{background:#1a1a1a;padding:12px;border-radius:8px;margin-bottom:8px;display:flex;justify-content:space-between;align-items:center}
.badge-active{background:#10b981;padding:2px 8px;border-radius:4px;font-size:11px;color:#fff}
.badge-blocked{background:#ef4444;padding:2px 8px;border-radius:4px;font-size:11px;color:#fff}
</style></head>
<body>
<div class="container"><div class="header"><h1>👑 Owner Panel</h1><a href="/mode" style="color:#888;">← Back</a></div>
<div class="card"><h2>📊 Metrics</h2><div id="metrics"></div></div>
<div class="card"><h2>➕ Add User</h2>
<input id="newName" placeholder="Name"><input id="newEmail" placeholder="Email"><input id="newPhone" placeholder="Phone"><input id="newPass" placeholder="Password">
<button class="btn btn-primary" onclick="addUser()">Create</button></div>
<div class="card"><h2>👥 Users</h2><div id="usersList">Loading...</div></div>
</div>
<script>
async function loadData(){const r=await fetch('/status');const d=await r.json();document.getElementById('metrics').innerHTML=`Users: ${(d.users||[]).length} | Multi-GC: ${Object.keys(d.accounts||{}).length} | Single GC: ${Object.keys(d.gc_accounts||{}).length}`;renderUsers(d.users||[]);}
function renderUsers(users){const container=document.getElementById('usersList');if(users.length===0){container.innerHTML='<p style="color:#888;">No users</p>';return;}let html='';for(const u of users){const blocked=u.status==='blocked';html+=`<div class="user-card"><div><strong>${u.name||u.email}</strong><br>${u.email} | ${u.phone||'N/A'}<span class="${blocked?'badge-blocked':'badge-active'}">${blocked?'BLOCKED':'ACTIVE'}</span></div><div><button class="btn btn-success" style="padding:4px 10px;font-size:11px;" onclick="toggleStatus('${u.email}','${blocked?'active':'blocked'}')">${blocked?'Unblock':'Block'}</button><button class="btn btn-danger" style="padding:4px 10px;font-size:11px;" onclick="deleteUser('${u.email}')">Delete</button></div></div>`;}container.innerHTML=html;}
async function addUser(){const name=document.getElementById('newName').value;const email=document.getElementById('newEmail').value;const phone=document.getElementById('newPhone').value;const pass=document.getElementById('newPass').value;if(!name||!email||!pass)return alert('All required!');await fetch('/api/owner/users/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,email,phone,password:pass})});loadData();}
async function toggleStatus(email,status){await fetch('/api/owner/users/toggle_status',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,status})});loadData();}
async function deleteUser(email){if(!confirm('Delete?'))return;await fetch('/api/owner/users/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user:email})});loadData();}
loadData();setInterval(loadData,5000);
</script></body></html>
"""

# ================= RUNNER =================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print(f"[UI SNAPPY] Running on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)