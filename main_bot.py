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

# ==========================================
# 👑 বটের ডাইরেক্ট কনফিগারেশন সমূহ
# ==========================================
ADMIN_ID = 6394277892
DATA_FILE = 'bot_data.json'
db_lock = threading.Lock()  # 🔒 রেলওয়ে ক্র্যাশ ফিক্সের জন্য থ্রেড লক

# --- ১ নম্বর বট (কাস্টমার ইনবক্স ও ওটিপি বট) ---
BOT_TOKEN_1 = '8632560684:AAFTRnXnAinthypH2Ja7U6kj0FyR4-5kpqo' 
GROUP_ID_1 = '-1003919009698' 
PANEL_TOKEN_1 = 'Q1ZXQjRSQn5zVlhDZm2FaEljjnRbi5iHW4J0gX5PhUGDImhFYHiQ'
API_URL_1 = 'http://51.77.216.195/crapi/konek/viewstats'

bot = telebot.TeleBot(BOT_TOKEN_1, threaded=False)
processed_sms = set()

# --- ২ নম্বর নতুন বট (গ্রুপ এসএমএস ফরোয়ার্ডার + ইনবক্স ব্যাকআপ) ---
BOT_TOKEN_2 = '8861443748:AAHSx7yHrRPIyzTq0fazbYwynzP3ON4-UqQ'
API_URL_2 = 'http://147.135.212.197/crapi/had/viewstats'
PANEL_TOKEN_2 = 'RVRVSjRSQlp8ioJzZ3JXSHh_jl91VIKHSnZQYnyUa3hSmE-Ch4SS'

bot2 = telebot.TeleBot(BOT_TOKEN_2, threaded=False)
processed_sms_bot2 = set()

# HTTP সেশন অপটিমাইজেশন (রেলওয়ে সার্ভারের জন্য নিরাপদ)
session = requests.Session()

# ==========================================
# 💾 ডাটাবেজ ম্যানেজমেন্ট ফাংশনস (ক্র্যাশ প্রুফ লক সহ)
# ==========================================
def load_db():
    with db_lock:  # ফাইল লক নিশ্চিত করা হচ্ছে
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, 'r') as f: 
                    return json.load(f)
        except Exception as e: 
            print(f"⚠️ Read DB Error: {e}")
        
        default_db = {"users": {}, "stock": {}, "mapping": {}, "prices": {}}
        try:
            with open(DATA_FILE, 'w') as f: 
                json.dump(default_db, f, indent=4)
        except: 
            pass
        return default_db

def save_db(data):
    with db_lock:  # ফাইল রাইট করার সময় লক করা হচ্ছে যাতে ডেটা করাপ্ট না হয়
        try:
            with open(DATA_FILE, 'w') as f: 
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"⚠️ Save DB Error: {e}")

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

# ==========================================
# 🚀 ফাংশন: ইউজার ম্যাপিং এবং ইনবক্স ডেলিভারি ইঞ্জিন
# ==========================================
def process_and_deliver_inbox(bot_instance, api_clean_num, num, otp_msg, raw_srv, code):
    db = load_db()
    target_uid = None
    
    for s_num, mapped_uid in list(db.get("mapping", {}).items()):
        db_clean_num = re.sub(r'\D', '', str(s_num))
        if (db_clean_num in api_clean_num) or (api_clean_num in db_clean_num) or (api_clean_num[-9:] == db_clean_num[-9:]):
            target_uid = str(mapped_uid)
            break
            
    if target_uid:
        c_code = "Unknown"
        price_keys = sorted(list(db.get("prices", {}).keys()), key=len, reverse=True)
        for pk in price_keys:
            if api_clean_num.startswith(pk):
                c_code = pk
                break
                
        commission = float(db.get("prices", {}).get(c_code, 0.0))
        
        if target_uid in db["users"]:
            if db["users"][target_uid].get("status") != 'allowed':
                return
                
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
            
            inbox_text = (f"🎯 **SMS RECEIVED IN YOUR NUMBER!**\n\n"
                         f"👤 **Number:** `{num}`\n"
                         f"🏢 **Service:** `{raw_srv}`\n"
                         f"💬 **Message:** {otp_msg}\n"
                         f"🔑 **Code:** `{code}`\n"
                         f"🎁 **Commission:** `+{commission} $`")
            
            try: 
                sent_inbox = bot.send_message(int(target_uid), inbox_text, parse_mode='Markdown')
                db["users"][target_uid]["last_pinned_msg_id"] = sent_inbox.message_id
            except Exception as inbox_err:
                print(f"❌ Inbox Send Failed to {target_uid}: {inbox_err}")
            
            save_db(db)

# ==========================================
# 🚀 রাস্তা ১: বট ১-এর মেইন ফরোয়ার্ডার লুপ
# ==========================================
def sms_forwarder_loop():
    global processed_sms
    print("🚀 Bot 1 Forwarder Loop Started...")
    while True:
        try:
            res = session.get(f"{API_URL_1}?token={PANEL_TOKEN_1}", timeout=10)
            if res.status_code == 200:
                data = res.json()
                if data.get('status') == 'success':
                    sms_list = data.get('data', [])
                    
                    if len(processed_sms) > 2000:
                        processed_sms.clear()
                        
                    for sms in reversed(sms_list):
                        num = str(sms.get('num', '')).strip()
                        msg_id = f"{num}_{sms.get('dt')}"
                        
                        if msg_id not in processed_sms:
                            processed_sms.add(msg_id)
                            
                            api_clean_num = re.sub(r'\D', '', num)
                            otp_msg = sms.get('message', '')
                            raw_srv = str(sms.get('cli', 'Unknown')).strip()
                            code = extract_otp(otp_msg)
                            
                            group_text = (f"📩 **NEW SMS RECEIVED!**\n\n"
                                         f"👤 **Number:** `{num}`\n"
                                         f"🏢 **Service:** `{raw_srv[:2]}***`\n"
                                         f"💬 **Message:** {otp_msg}\n"
                                         f"🔑 **OTP:** `{code}`")
                            try: bot.send_message(GROUP_ID_1, group_text, parse_mode='Markdown')
                            except: pass
                            
                            process_and_deliver_inbox(bot, api_clean_num, num, otp_msg, raw_srv, code)
            time.sleep(4)
        except Exception as e:
            print(f"⚠️ Loop 1 Exception Reset: {e}")
            time.sleep(5)

# ==========================================
# 🚀 রাস্তা ২: বট ২-এর নতুন ফরোয়ার্ডার লুপ
# ==========================================
def new_bot_sms_loop():
    global processed_sms_bot2
    print("🚀 Bot 2 Forwarder Loop Started...")
    while True:
        try:
            res = session.get(f"{API_URL_2}?token={PANEL_TOKEN_2}&records=25", timeout=10)
            if res.status_code == 200:
                data = res.json()
                if data.get('status') == 'success':
                    sms_list = data.get('data', [])
                    
                    if len(processed_sms_bot2) > 2000:
                        processed_sms_bot2.clear()
                        
                    for sms in reversed(sms_list):
                        num = str(sms.get('num', '')).strip()
                        msg_id = f"{num}_{sms.get('dt')}"
                        
                        if msg_id not in processed_sms_bot2:
                            processed_sms_bot2.add(msg_id)
                            
                            api_clean_num = re.sub(r'\D', '', num)
                            otp_msg = sms.get('message', '')
                            service_name = sms.get('service') or sms.get('cli') or 'Unknown'
                            service_name = str(service_name).strip()
                            code = extract_otp(otp_msg)
                            
                            group_text = (f"🎯 **NEW SMS RECEIVED!**\n\n"
                                         f"👤 **Number:** `{num}`\n"
                                         f"🏢 **Service:** `{service_name}`\n"
                                         f"💬 **Message:** {otp_msg}\n"
                                         f"🔑 **Code:** `{code}`")
                            try:
                                bot2.send_message(GROUP_ID_1, group_text, parse_mode='Markdown')
                            except:
                                pass
                                
                            process_and_deliver_inbox(bot, api_clean_num, num, otp_msg, service_name, code)
            time.sleep(4)
        except Exception as e:
            print(f"⚠️ Loop 2 Exception Reset: {e}")
            time.sleep(5)

# ==========================================
# ⌨️ কিবোর্ড বিল্ডার্স ও ইউজার হ্যান্ডলারস
# ==========================================
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🛒 Buy Numbers"), types.KeyboardButton("📊 Stock Status"))
    markup.add(types.KeyboardButton("📝 My History"), types.KeyboardButton("🌍 Country Stats"))
    markup.add(types.KeyboardButton("💰 Balance"), types.KeyboardButton("💸 Withdraw"))
    return markup

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

@bot.message_handler(commands=['setprice'])
def admin_set_price_init(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        db = load_db()
        prices = db.get("prices", {})
        
        markup = types.InlineKeyboardMarkup()
        if prices:
            for prefix, val in prices.items():
                markup.add(types.InlineKeyboardButton(f"⚙️ +{prefix} ➡️ {val} $", callback_data=f"prfx_edit_{prefix}"))
        
        markup.add(types.InlineKeyboardButton("➕ Add New Prefix", callback_data="prfx_add_new"))
        
        bot.send_message(message.chat.id, "⚙️ **[SET PRICE PANEL]**\n\nনিচের লিস্ট থেকে যে প্রিফিক্সের প্রাইস চেঞ্জ করতে চান সেটিতে ক্লিক করুন অথবা নতুন প্রিফিক্স যোগ করুন:", reply_markup=markup)
    except: pass

@bot.callback_query_handler(func=lambda call: call.data.startswith('prfx_'))
def handle_price_callback_routing(call):
    try:
        if call.from_user.id != ADMIN_ID: return
        action = call.data
        
        if action == "prfx_add_new":
            p = bot.send_message(call.message.chat.id, "⚙️ Enter the target country code prefix (e.g., `263`, `257`):", reply_markup=types.ForceReply(selective=True))
            bot.register_for_reply(p, admin_set_price_prefix_step)
        elif action.startswith("prfx_edit_"):
            prefix = action.replace("prfx_edit_", "")
            p = bot.send_message(call.message.chat.id, f"💰 **Prefix Code:** `+{prefix}`\n\nEnter the new per-SMS payout commission rate (e.g., `0.015`):", reply_markup=types.ForceReply(selective=True))
            bot.register_for_reply(p, lambda msg: admin_set_price_final_save(msg, prefix))
    except: pass

def admin_set_price_prefix_step(message):
    prefix = re.sub(r'\D', '', message.text.strip())
    if not prefix:
        bot.reply_to(message, "❌ Invalid input. Prefix text must be numbers only.")
        return
    p = bot.send_message(message.chat.id, f"💰 **Prefix Code:** `+{prefix}`\n\nEnter the per-SMS payout commission rate (e.g., `0.012`):", reply_markup=types.ForceReply(selective=True))
    bot.register_for_reply(p, lambda msg: admin_set_price_final_save(msg, prefix))

def admin_set_price_final_save(message, prefix):
    try:
        price = float(message.text.strip())
        db = load_db()
        if "prices" not in db: db["prices"] = {}
        
        db["prices"][str(prefix)] = price
        save_db(db)
        bot.reply_to(message, f"✅ **Commissions Map Configured!**\n📍 Prefix Route: `+{prefix}`\n💵 Custom Share Rate: `{price}` $")
    except:
        bot.reply_to(message, "❌ Invalid value matrix format. Price parsing dropped.")

@bot.message_handler(commands=['broadcast'])
def handle_admin_broadcast(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        broadcast_text = message.text.replace('/broadcast', '').strip()
        if not broadcast_text:
            bot.reply_to(message, "❌ **ফরম্যাট ভুল!**\n\nকমান্ডের সাথে আপনার মেসেজটি লিখুন।")
            return
            
        db = load_db()
        users_data = db.get("users", {})
        if not users_data: return
            
        bot.reply_to(message, f"📢 {len(users_data)} জন ইউজারের ইনবক্সে ব্রডকাস্ট শুরু হচ্ছে...")
        
        for u_id_str in users_data.keys():
            try: bot.send_message(chat_id=int(u_id_str), text=broadcast_text, parse_mode='HTML')
            except: pass
    except: pass

@bot.message_handler(commands=['delete'])
def admin_delete_stock_menu(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        db = load_db()
        stock = db.get("stock", {})
        active_countries = [c for c, nums in stock.items() if len(nums) > 0]
        
        if not active_countries:
            bot.send_message(message.chat.id, "📂 **বর্তমানে ডিলিট করার মতো কোনো একটিভ স্টক ফাইল নেই।**")
            return
            
        markup = types.InlineKeyboardMarkup()
        for country in active_countries:
            markup.add(types.InlineKeyboardButton(f"🗑️ Delete {country}", callback_data=f"adm_del_{country}"))
            
        bot.send_message(message.chat.id, "🛠️ **Select a country stock to completely delete:**", reply_markup=markup)
    except: pass

@bot.callback_query_handler(func=lambda call: call.data.startswith('adm_del_'))
def handle_admin_stock_wipe(call):
    try:
        if call.from_user.id != ADMIN_ID: return
        country_target = call.data.replace('adm_del_', '')
        
        db = load_db()
        numbers_in_stock = db["stock"].get(country_target, [])
        if country_target in db["stock"]:
            db["stock"][country_target] = []
            
        prefix_target = None
        if numbers_in_stock:
            first_num = re.sub(r'\D', '', str(numbers_in_stock[0]))
            price_keys = sorted(list(db.get("prices", {}).keys()), key=len, reverse=True)
            for pk in price_keys:
                if first_num.startswith(pk):
                    prefix_target = pk
                    break

        keys_to_clear = []
        for mapped_num in list(db.get("mapping", {}).keys()):
            clean_mapped = re.sub(r'\D', '', str(mapped_num))
            if mapped_num in numbers_in_stock:
                keys_to_clear.append(mapped_num)
            elif prefix_target and clean_mapped.startswith(prefix_target):
                keys_to_clear.append(mapped_num)
                
        for k in keys_to_clear:
            if k in db["mapping"]: del db["mapping"][k]
                
        save_db(db)
        bot.edit_message_text(f"✅ **Stock Successfully Deleted!**\n🌍 Name: `{country_target}`", chat_id=call.message.chat.id, message_id=call.message.message_id)
    except: pass

@bot.message_handler(func=lambda m: m.text == "📊 Stock Status")
def current_stock_status_msg(message):
    try:
        db = load_db()
        stock = db.get("stock", {})
        res = "📊 **Current Stock Status:**\n━━━━━━━━━━━━━━━━━━━━\n"
        has_stock = False
        for country, nums in stock.items():
            if len(nums) > 0:
                res += f"🌍 **{country}:** `{len(nums)}` numbers available\n"
                has_stock = True
        if not has_stock: res = "❌ **দুঃখিত, বর্তমানে কোনো স্টক খালি নেই।**"
        bot.send_message(message.chat.id, res, parse_mode='Markdown')
    except: pass

@bot.message_handler(func=lambda m: m.text == "💰 Balance")
def check_bal_msg(message):
    try:
        user = get_user(message.from_user.id)
        bot.send_message(message.chat.id, f"💵 **Your Balance:** `{user['balance']}` **$**", parse_mode='Markdown')
    except: pass

@bot.message_handler(func=lambda m: m.text == "📝 My History")
def check_history_msg(message):
    try:
        u_id = str(message.from_user.id)
        db = load_db()
        history_logs = db["users"].get(u_id, {}).get("history", {})
        
        report_text = "📊 **YOUR 10 DAYS OTP REPORT**\n━━━━━━━━━━━━━━━━━━━━\n"
        total_otps, total_revenue = 0, 0.0
        has_records = False
        
        for i in range(10):
            date_check = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            if date_check in history_logs:
                log_node = history_logs[date_check]
                count, earn = log_node.get("count", 0), log_node.get("earn", 0.0)
                if count > 0:
                    report_text += f"📅 `{date_check}` ➡️ `{count}` OTPs [ Income: `+{earn}` $ ]\n"
                    total_otps += count
                    total_revenue += earn
                    has_records = True
                    
        if not has_records: report_text += "❌ No records found."
        else: report_text += f"━━━━━━━━━━━━━━━━━━━━\n✅ **Total OTPs:** `{total_otps}`\n💰 **Total Earned:** `{round(total_revenue, 4)}` $"
        bot.send_message(message.chat.id, report_text, parse_mode='Markdown')
    except: pass

@bot.message_handler(func=lambda m: m.text == "🌍 Country Stats")
def stats_msg(message):
    try:
        user = get_user(message.from_user.id)
        if not user.get("stats"):
            bot.send_message(message.chat.id, "📊 **No country statistics logs recorded.**")
            return
        res = "🌍 **YOUR OTP COUNTS:**\n━━━━━━━━━━━━━━━━━━━━\n"
        for cc, count in user["stats"].items():
            res += f"📍 **Code +{cc}:** `{count}` verifications\n"
        bot.send_message(message.chat.id, res, parse_mode='Markdown')
    except: pass

@bot.message_handler(func=lambda m: m.text == "💸 Withdraw")
def withdraw_msg(message):
    try:
        user = get_user(message.from_user.id)
        if user["balance"] <= 0:
            bot.send_message(message.chat.id, f"❌ **Insufficient balance. Balance:** `{user['balance']}` $")
            return
        p = bot.send_message(message.chat.id, "💸 **Withdraw Panel**\n\nReply directly with your bKash Number / Binance ID:", reply_markup=types.ForceReply(selective=True))
        bot.register_for_reply(p, handle_withdraw_input)
    except: pass

def handle_withdraw_input(message):
    try:
        u_id = message.from_user.id
        db = load_db()
        current_bal = db["users"].get(str(u_id), {}).get("balance", 0.0)
        if current_bal <= 0: return
        details = message.text.strip()
        db["users"][str(u_id)]["balance"] = 0.0
        save_db(db)
        bot.send_message(message.chat.id, "⏳ **Withdraw request sent to Admin.**")
        bot.send_message(ADMIN_ID, f"📥 **WITHDRAW REQUEST**\n\n👤 User: {message.from_user.first_name}\n🆔 ID: `{u_id}`\n💰 Amount: `{current_bal}` $\n📝 Details: `{details}`")
    except: pass

@bot.message_handler(content_types=['document'])
def handle_admin_txt_upload(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        if message.document.file_name.endswith('.txt'):
            raw_title = os.path.splitext(message.document.file_name)[0]
            c_name = re.sub(r'\s*\(\d+\)\s*', '', raw_title).strip()
            
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            content = downloaded_file.decode('utf-8')
            
            lines = content.strip().split('\n')
            cleaned_numbers = [re.sub(r'\D', '', l) for l in lines if re.sub(r'\D', '', l)]
            if not cleaned_numbers: return
                
            db = load_db()
            if "stock" not in db: db["stock"] = {}
            if c_name not in db["stock"]: db["stock"][c_name] = []
            
            db["stock"][c_name].extend(cleaned_numbers)
            save_db(db)
            bot.reply_to(message, f"✅ **STOCK LOADED!**\n🌍 Stock Allocated Name: `{c_name}`\n🔢 Total Added: `{len(cleaned_numbers)}` Numbers.")
    except: pass

@bot.message_handler(commands=['addbalance'])
def admin_add_balance(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        match = re.match(r'/addbalance\s+(\d+)\s+([\d.]+)', message.text.strip())
        if not match: return
        t_id, amt = match.group(1), float(match.group(2))
        
        db = load_db()
        if t_id in db["users"]:
            db["users"][t_id]["balance"] = round(db["users"][t_id]["balance"] + amt, 4)
            save_db(db)
            bot.reply_to(message, f"✅ **Balance Added!** Payout: `{db['users'][t_id]['balance']}` $")
    except: pass

@bot.message_handler(commands=['allow', 'ban', 'unban'])
def admin_status_management(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        cmd = message.text.split(' ')[0].replace('/', '')
        t_id = message.text.split(' ')[1].strip()
        db = load_db()
        if t_id in db["users"]:
            db["users"][t_id]["status"] = "allowed" if cmd in ['allow', 'unban'] else "banned"
            save_db(db)
            bot.reply_to(message, f"✅ Action Complete: {cmd}")
    except: pass

# ==========================================
# ⚙️ মেইন রানার এবং মাল্টিথ্রেডিং কন্ট্রোলার
# ==========================================
if __name__ == '__main__':
    load_db()
    
    t1 = threading.Thread(target=sms_forwarder_loop, daemon=True)
    t1.start()
    
    t2 = threading.Thread(target=new_bot_sms_loop, daemon=True)
    t2.start()
    
    print("🤖 রেলওয়ে প্রোটেক্টেড মাল্টি-থ্রেড মোড চালু হয়েছে।")
    
    # পোলিং ক্র্যাশ রিকভারি লুপ (Anti-Crash Engine)
    while True:
        try: 
            bot.polling(none_stop=True, timeout=60, long_polling_timeout=30)
        except Exception as ex: 
            print(f"⚠️ Polling Engine Restating due to connection drop... {ex}")
            time.sleep(5)
