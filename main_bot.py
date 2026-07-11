import telebot
from telebot import types
import requests
import time
import os
import json
import threading
import re
import io
import gc
from datetime import datetime, timedelta

# --- DIRECT CONFIG ---
BOT_TOKEN = '8632560684:AAFTRnXnAinthypH2Ja7U6kj0FyR4-5kpqo' 
ADMIN_ID = 6394277892
GROUP_ID = '-1003919009698' 

# 🔗 PANEL 1 CONFIG (Old)
PANEL_TOKEN_1 = 'Q1ZXQjRSQn5zVlhDZm2FaEljjnRbi5iHW4J0gX5PhUGDImhFYHiQ'
API_URL_1 = 'http://51.77.216.195/crapi/konek/viewstats'

# 🔗 PANEL 2 CONFIG (New)
API_URL_2 = 'http://147.135.212.197/crapi/had/viewstats?token=RVRVSjRSQlp8ioJzZ3JXSHh_jl91VIKHSnZQYnyUa3hSmE-Ch4SS&records=25'

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
processed_sms = set()
DATA_FILE = 'bot_data.json'

def load_db():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f: return json.load(f)
    except Exception as e: 
        print(f"DB Load Error: {e}")
    default_db = {"users": {}, "stock": {}, "mapping": {}, "prices": {}}
    try:
        with open(DATA_FILE, 'w') as f: json.dump(default_db, f, indent=4)
    except: pass
    return default_db

def save_db(data):
    try:
        with open(DATA_FILE, 'w') as f: json.dump(data, f, indent=4)
    except Exception as e:
        print(f"DB Save Error: {e}")

def get_user(u_id, username="Unknown"):
    db = load_db()
    uid_str = str(u_id)
    
    if int(u_id) == ADMIN_ID:
        db["users"][uid_str] = {"status": "allowed", "balance": 9999.0, "stats": {}, "history": {}, "last_pinned_msg_id": None}
        db["users"][uid_str]["username"] = username
        save_db(db)
        return db["users"][uid_str]
        
    if uid_str not in db["users"]:
        db["users"][uid_str] = {"status": "pending", "balance": 0.0, "stats": {}, "history": {}, "last_pinned_msg_id": None}
    db["users"][uid_str]["username"] = username
    save_db(db)
    return db["users"][uid_str]

def extract_otp(message):
    try:
        otp_match = re.search(r'\b\d{4,8}\b', message)
        if otp_match: return otp_match.group(0)
    except: pass
    return "N/A"

# --- PANEL 1 FORWARDER ENGINE ---
def sms_forwarder_loop_1():
    global processed_sms
    while True:
        try:
            with requests.get(f"{API_URL_1}?token={PANEL_TOKEN_1}", timeout=15) as res:
                if res.status_code == 200:
                    data = res.json()
                    if data.get('status') == 'success':
                        sms_list = data.get('data', [])
                        
                        if len(processed_sms) > 3000:
                            processed_sms.clear()
                            
                        for sms in reversed(sms_list):
                            num = str(sms.get('num', '')).strip()
                            msg_id = f"p1_{num}_{sms.get('dt')}"
                            
                            if msg_id not in processed_sms:
                                processed_sms.add(msg_id)
                                
                                db = load_db()
                                target_uid = None
                                
                                for s_num, mapped_uid in list(db.get("mapping", {}).items()):
                                    if s_num in num or num in s_num:
                                        target_uid = str(mapped_uid)
                                        break
                                        
                                if not target_uid:
                                    continue
                                    
                                otp_msg = sms.get('message', '')
                                raw_srv = str(sms.get('cli', 'Unknown')).strip()
                                clean_num = re.sub(r'\D', '', num)
                                
                                c_code = "Unknown"
                                price_keys = sorted(list(db.get("prices", {}).keys()), key=len, reverse=True)
                                for pk in price_keys:
                                    if clean_num.startswith(pk):
                                        c_code = pk
                                        break
                                        
                                commission = float(db.get("prices", {}).get(c_code, 0.0))
                                
                                if target_uid in db["users"]:
                                    if db["users"][target_uid].get("status") != 'allowed':
                                        continue
                                        
                                    today = datetime.now().strftime('%Y-%m-%d')
                                    db["users"][target_uid]["balance"] = round(float(db["users"][target_uid].get("balance", 0.0)) + commission, 4)
                                    
                                    if "stats" not in db["users"][target_uid]: db["users"][target_uid]["stats"] = {}
                                    db["users"][target_uid]["stats"][c_code] = db["users"][target_uid]["stats"].get(c_code, 0) + 1
                                    
                                    if "history" not in db["users"][target_uid] or isinstance(db["users"][target_uid]["history"], list):
                                        db["users"][target_uid]["history"] = {}
                                        
                                    if today not in db["users"][target_uid]["history"]:
                                        db["users"][target_uid]["history"][today] = {"count": 0, "earn": 0.0}
                                        
                                    db["users"][target_uid]["history"][today]["count"] += 1
                                    db["users"][target_uid]["history"][today]["earn"] = round(float(db["users"][target_uid].get("history"][today].get("earn", 0.0)) + commission, 4)
                                    
                                    code = extract_otp(otp_msg)
                                    
                                    group_text = (f"📩 **NEW SMS RECEIVED!**\n\n"
                                                 f"👤 **Number:** `{num}`\n"
                                                 f"🏢 **Service:** `{raw_srv[:2]}***`\n"
                                                 f"💬 **Message:** {otp_msg}\n"
                                                 f"🔑 **OTP:** `{code}`")
                                    try: bot.send_message(GROUP_ID, group_text, parse_mode='Markdown')
                                    except: pass
                                    
                                    inbox_text = (f"🎯 **SMS RECEIVED IN YOUR NUMBER!**\n\n"
                                                 f"👤 **Number:** `{num}`\n"
                                                 f"🏢 **Service:** `{raw_srv}`\n"
                                                 f"💬 **Message:** {otp_msg}\n"
                                                 f"🔑 **Code:** `{code}`\n"
                                                 f"🎁 **Commission:** `+{commission} $`")
                                    
                                    try: 
                                        old_msg_id = db["users"][target_uid].get("last_pinned_msg_id")
                                        if old_msg_id:
                                            try: bot.delete_message(chat_id=int(target_uid), message_id=old_msg_id)
                                            except: pass
                                        
                                        sent_inbox = bot.send_message(int(target_uid), inbox_text, parse_mode='Markdown')
                                        db["users"][target_uid]["last_pinned_msg_id"] = sent_inbox.message_id
                                    except: 
                                        pass
                                    
                                    save_db(db)
            # মেমোরি রিলিজ করা
            gc.collect()
            time.sleep(10) # সেফটি ডিলে বাড়ানো হলো
        except Exception as e:
            print(f"Panel 1 Loop Error: {e}")
            time.sleep(10) # এরর খেলেও ১০ সেকেন্ড থামবে (ক্র্যাশ প্রতিরোধ করবে)

# --- PANEL 2 FORWARDER ENGINE (New API) ---
def sms_forwarder_loop_2():
    global processed_sms
    while True:
        try:
            with requests.get(API_URL_2, timeout=15) as res:
                if res.status_code == 200:
                    data = res.json()
                    if data.get('status') == 'success':
                        sms_list = data.get('data', [])
                        
                        if len(processed_sms) > 3000:
                            processed_sms.clear()
                            
                        for sms in reversed(sms_list):
                            num = str(sms.get('num', '')).strip()
                            msg_id = f"p2_{num}_{sms.get('dt')}"
                            
                            if msg_id not in processed_sms:
                                processed_sms.add(msg_id)
                                
                                db = load_db()
                                target_uid = None
                                
                                for s_num, mapped_uid in list(db.get("mapping", {}).items()):
                                    if s_num in num or num in s_num:
                                        target_uid = str(mapped_uid)
                                        break
                                        
                                if not target_uid:
                                    continue
                                    
                                otp_msg = sms.get('message', '')
                                raw_srv = str(sms.get('cli', 'Unknown')).strip()
                                clean_num = re.sub(r'\D', '', num)
                                
                                c_code = "Unknown"
                                price_keys = sorted(list(db.get("prices", {}).keys()), key=len, reverse=True)
                                for pk in price_keys:
                                    if clean_num.startswith(pk):
                                        c_code = pk
                                        break
                                        
                                commission = float(db.get("prices", {}).get(c_code, 0.0))
                                
                                if target_uid in db["users"]:
                                    if db["users"][target_uid].get("status") != 'allowed':
                                        continue
                                        
                                    today = datetime.now().strftime('%Y-%m-%d')
                                    db["users"][target_uid]["balance"] = round(float(db["users"][target_uid].get("balance", 0.0)) + commission, 4)
                                    
                                    if "stats" not in db["users"][target_uid]: db["users"][target_uid]["stats"] = {}
                                    db["users"][target_uid]["stats"][c_code] = db["users"][target_uid]["stats"].get(c_code, 0) + 1
                                    
                                    if "history" not in db["users"][target_uid] or isinstance(db["users"][target_uid]["history"], list):
                                        db["users"][target_uid]["history"] = {}
                                        
                                    if today not in db["users"][target_uid]["history"]:
                                        db["users"][target_uid]["history"][today] = {"count": 0, "earn": 0.0}
                                        
                                    db["users"][target_uid]["history"][today]["count"] += 1
                                    db["users"][target_uid]["history"][today]["earn"] = round(float(db["users"][target_uid].get("history"][today].get("earn", 0.0)) + commission, 4)
                                    
                                    code = extract_otp(otp_msg)
                                    
                                    group_text = (f"📩 **NEW SMS RECEIVED!**\n\n"
                                                 f"👤 **Number:** `{num}`\n"
                                                 f"🏢 **Service:** `{raw_srv[:2]}***`\n"
                                                 f"💬 **Message:** {otp_msg}\n"
                                                 f"🔑 **OTP:** `{code}`")
                                    try: bot.send_message(GROUP_ID, group_text, parse_mode='Markdown')
                                    except: pass
                                    
                                    inbox_text = (f"🎯 **SMS RECEIVED IN YOUR NUMBER!**\n\n"
                                                 f"👤 **Number:** `{num}`\n"
                                                 f"🏢 **Service:** `{raw_srv}`\n"
                                                 f"💬 **Message:** {otp_msg}\n"
                                                 f"🔑 **Code:** `{code}`\n"
                                                 f"🎁 **Commission:** `+{commission} $`")
                                    
                                    try: 
                                        old_msg_id = db["users"][target_uid].get("last_pinned_msg_id")
                                        if old_msg_id:
                                            try: bot.delete_message(chat_id=int(target_uid), message_id=old_msg_id)
                                            except: pass
                                        
                                        sent_inbox = bot.send_message(int(target_uid), inbox_text, parse_mode='Markdown')
                                        db["users"][target_uid]["last_pinned_msg_id"] = sent_inbox.message_id
                                    except: 
                                        pass
                                    
                                    save_db(db)
            gc.collect()
            time.sleep(10) # সেফটি ডিলে বাড়ানো হলো
        except Exception as e:
            print(f"Panel 2 Loop Error: {e}")
            time.sleep(10) # এরর খেলেও ১০ সেকেন্ড থামবে (ক্র্যাশ প্রতিরোধ করবে)

# --- KEYBOARD BUILDERS ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🛒 Buy Numbers"), types.KeyboardButton("📊 Stock Status"))
    markup.add(types.KeyboardButton("📝 My History"), types.KeyboardButton("🌍 Country Stats"))
    markup.add(types.KeyboardButton("💰 Balance"), types.KeyboardButton("💸 Withdraw"))
    return markup

# --- USER START TRIGGER ---
@bot.message_handler(commands=['start'])
def start_cmd(message):
    try:
        u_id = message.from_user.id
        u_name = message.from_user.username or message.from_user.first_name
        user = get_user(u_id, u_name)
        
        if user["status"] == 'banned':
            bot.send_message(message.chat.id, "❌ **You are banned from this bot.**")
            return
            
        if user["status"] == 'pending' and u_id != ADMIN_ID:
            bot.send_message(message.chat.id, "⏳ **Your account is PENDING. Waiting for Admin approval.**")
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🟢 Approve User", callback_data=f"btn_allow_{u_id}"))
            try: bot.send_message(ADMIN_ID, f"🔔 **NEW USER SIGNUP:** {u_name}\n🆔 ID: `{u_id}`\n\nClick the button below to approve:", reply_markup=markup)
            except: pass
            return

        welcome_msg = (f"🔥 **WELCOME TO NUMBER FILES BOT** 🔥\n\n"
                       f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                       f"👑 **MY OWNER IS NAHID HASAN**\n"
                       f"💥 **HE IS THE STEP-FATHER OF EVERY MOTHERFUCKER**\n"
                       f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                       f"💡 *Use the menu buttons below to manage your operations:*")
        bot.send_message(message.chat.id, welcome_msg, parse_mode='Markdown', reply_markup=main_menu())
    except: pass

@bot.callback_query_handler(func=lambda call: call.data.startswith('btn_allow_'))
def handle_one_click_approval(call):
    try:
        if call.from_user.id != ADMIN_ID: return
        target_uid_str = call.data.replace('btn_allow_', '')
        db = load_db()
        if target_uid_str in db["users"]:
            db["users"][target_uid_str]["status"] = "allowed"
            save_db(db)
            bot.answer_callback_query(call.id, "✅ User Approved Successfully!")
            bot.edit_message_text(f"✅ **USER APPROVED**\n🆔 ID: `{target_uid_str}`\n\nOperation completed successfully.", chat_id=call.message.chat.id, message_id=call.message.message_id)
            try: bot.send_message(int(target_uid_str), "🎉 **Your account has been approved by the Admin!**\nUse /start to open menu options.")
            except: pass
    except: pass

# --- BUY LOGIC ---
@bot.message_handler(func=lambda m: m.text in ["🛒 Buy Numbers", "/buy"])
def buy_numbers_trigger(message):
    try:
        db = load_db()
        u_id_str = str(message.from_user.id)
        if u_id_str not in db["users"] or db["users"][u_id_str]["status"] != 'allowed': return
        
        stock = db.get("stock", {})
        active_countries = [c for c, nums in stock.items() if len(nums) > 0]
        
        if not active_countries:
            bot.send_message(message.chat.id, "❌ **দুঃখিত, বর্তমানে কোনো স্টক খালি নেই।**")
            return
            
        markup = types.InlineKeyboardMarkup()
        for country in active_countries:
            markup.add(types.InlineKeyboardButton(f"🌍 {country} ({len(stock[country])} left)", callback_data=f"selc_{country}"))
            
        bot.send_message(message.chat.id, "🎯 **Select the Country to pull numbers:**", reply_markup=markup)
    except: pass

@bot.callback_query_handler(func=lambda call: call.data.startswith('selc_'))
def country_select_callback(call):
    try:
        country = call.data.replace('selc_', '')
        db = load_db()
        avail = len(db["stock"].get(country, []))
        
        markup = types.InlineKeyboardMarkup()
        for size in [10, 50, 100]:
            if avail >= size:
                markup.add(types.InlineKeyboardButton(f"📁 Get {size} Numbers (.txt)", callback_data=f"pullfile_{country}_{size}"))
            
        bot.edit_message_text(f"🌍 **Country:** `{country}`\n🔢 **Available:** `{avail}`\n\nSelect package pack size options below:", 
                              chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)
    except: pass

@bot.callback_query_handler(func=lambda call: call.data.startswith('pullfile_'))
def deliver_file_callback(call):
    try:
        parts = call.data.split('_')
        country, count = parts[1], int(parts[2])
        u_id = call.from_user.id
        
        db = load_db()
        if len(db["stock"].get(country, [])) < count:
            bot.answer_callback_query(call.id, "❌ Stock changed, package choice size unavailable!", show_alert=True)
            return
            
        selected = db["stock"][country][:count]
        db["stock"][country] = db["stock"][country][count:]
        
        for num in selected:
            db["mapping"][str(num)] = u_id
        save_db(db)
        
        file_data = "\n".join(selected)
        bio = io.BytesIO(file_data.encode('utf-8'))
        bio.name = f"{country}_{count}_numbers.txt"
        
        try: bot.delete_message(call.message.chat.id, call.message.message_id)
        except: pass
        bot.send_document(call.message.chat.id, bio, caption=f"✅ **Delivered {count} numbers for {country}!**\n\nOTPs will hit your inbox instantly.")
    except: pass

# --- SETPRICE PANEL ---
@bot.message_handler(commands=['setprice'])
def admin_set_price_init(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        db = load_db()
        prices = db.get("prices", {})
        
        markup = types.InlineKeyboardMarkup()
        if prices:
            for prefix, val in prices.items():
                markup.add(types.InlineKeyboardButton(f"⚙️ +{prefix} ➡️ {
