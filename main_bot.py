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
    except: pass
    default_db = {"users": {}, "stock": {}, "mapping": {}, "prices": {}}
    try:
        with open(DATA_FILE, 'w') as f: json.dump(default_db, f, indent=4)
    except: pass
    return default_db

def save_db(data):
    try:
        with open(DATA_FILE, 'w') as f: json.dump(data, f, indent=4)
    except: pass

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
            del data
            gc.collect()
            time.sleep(5)
        except Exception as e:
            time.sleep(5)

# 🆕 --- PANEL 2 FORWARDER ENGINE (New API) ---
def sms_forwarder_loop_2():
    global processed_sms
    while True:
        try:
            # নতুন ফুল API URL দিয়ে রিকোয়েস্ট পাঠানো হচ্ছে
            with requests.get(API_URL_2, timeout=15) as res:
                if res.status_code == 200:
                    data = res.json()
                    if data.get('status') == 'success':
                        sms_list = data.get('data', [])
                        
                        if len(processed_sms) > 3000:
                            processed_sms.clear()
                            
                        for sms in reversed(sms_list):
                            num = str(sms.get('num', '')).strip()
                            # প্যানেল ১ ও ২ এর আইডি আলাদা রাখার জন্য 'p2_' প্রিফিক্স ব্যবহার করা হয়েছে
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
            del data
            gc.collect()
            time.sleep(5)
        except Exception as e:
            time.sleep(5)

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

# --- BROADCAST COMMAND ---
@bot.message_handler(commands=['broadcast'])
def handle_admin_broadcast(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        broadcast_text = message.text.replace('/broadcast', '').strip()
        if not broadcast_text:
            bot.reply_to(message, "❌ **ফরম্যাট ভুল!**\n\nকমান্ডের সাথে আপনার মেসেজটি লিখুন।\nযেমন: `/broadcast Burundi নতুন নাম্বার স্টক করা হয়েছে!`")
            return
            
        db = load_db()
        users_data = db.get("users", {})
        if not users_data:
            bot.reply_to(message, "❌ বটের ডাটাবেজে কোনো ইউজার খুঁজে পাওয়া যায়নি।")
            return
            
        bot.reply_to(message, f"📢 {len(users_data)} জন ইউজারের ইনবক্সে নোটিশ পাঠানো প্রসেস শুরু হচ্ছে...")
        success_count = 0
        
        for u_id_str, info in users_data.items():
            try:
                bot.send_message(chat_id=int(u_id_str), text=broadcast_text, parse_mode='HTML')
                success_count += 1
            except:
                pass
                
        bot.send_message(ADMIN_ID, f"✅ **ব্রডকাস্ট সম্পন্ন!**\n🎯 সফলভাবে {success_count} জন ইউজারের ইনবক্সে মেসেজ পাঠানো হয়েছে।")
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ Broadcast Error: {e}")

# --- DELETE STOCK ---
@bot.message_handler(commands=['delete'])
def admin_delete_stock_menu(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        db = load_db()
        stock = db.get("stock", {})
        active_countries = [c for c, nums in stock.items() if len(nums) > 0]
        
        if not active_countries:
            bot.send_message(message.chat.id, "📂 **বর্তমানে ডাটাবেজে ডিলিট করার মতো কোনো একটিভ স্টক ফাইল নেই।**")
            return
            
        markup = types.InlineKeyboardMarkup()
        for country in active_countries:
            markup.add(types.InlineKeyboardButton(f"🗑️ Delete {country} [{len(stock[country])} lines]", callback_data=f"adm_del_{country}"))
            
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
            if k in db["mapping"]:
                del db["mapping"][k]
                
        save_db(db)
        bot.answer_callback_query(call.id, f"🗑️ Stock & Mappings deleted!", show_alert=True)
        bot.edit_message_text(f"✅ **Stock Successfully Deleted!**\n🌍 Name: `{country_target}`", chat_id=call.message.chat.id, message_id=call.message.message_id)
    except: pass

# --- OTHER MENUS ---
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
        if not has_stock:
            res = "❌ **দুঃখিত, বর্তমানে কোনো স্টক খালি নেই।**"
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
        
        report_text = "📊 **YOUR 10 DAYS OTP & REVENUE REPORT**\n━━━━━━━━━━━━━━━━━━━━\n"
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
                    
        if not has_records:
            report_text += "❌ No records found."
        else:
            report_text += f"━━━━━━━━━━━━━━━━━━━━\n✅ **Total OTPs:** `{total_otps}`\n💰 **Total Earned:** `{round(total_revenue, 4)}` $"
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
            res += f"📍 **Code +{cc}:** `{count}` successful verifications\n"
        bot.send_message(message.chat.id, res, parse_mode='Markdown')
    except: pass

@bot.message_handler(func=lambda m: m.text == "💸 Withdraw")
def withdraw_msg(message):
    try:
        user = get_user(message.from_user.id)
        if user["balance"] <= 0:
            bot.send_message(message.chat.id, f"❌ **Insufficient balance to withdraw. Balance:** `{user['balance']}` $")
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
        bot.send_message(ADMIN_ID, f"📥 **WITHDRAW REQUEST**\n\n👤 User: {message.from_user.first_name}\n🆔 ID: `{u_id}`\n💰 Amount: `{current_bal}` $\n📝 Details: `{details}`\n\nTo Pay:\n`/pay {u_id} TxID`")
    except: pass

# --- FILE IMPORT ---
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
            bot.reply_to(message, f"✅ **STOCK LOADED BY FILE NAME!**\n🌍 Stock Allocated Name: `{c_name}`\n🔢 Total Added: `{len(cleaned_numbers)}` Numbers.")
    except: pass

# --- FIXED /addbalance SYSTEM ---
@bot.message_handler(commands=['addbalance'])
def admin_add_balance(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        match = re.match(r'/addbalance\s+(\d+)\s+([\d.]+)', message.text.strip())
        if not match:
            bot.reply_to(message, "💡 **Format:** `/addbalance USER_ID AMOUNT` \nExample: `/addbalance 6394277892 10.5`")
            return
            
        t_id = match.group(1)
        amt = float(match.group(2))
        
        db = load_db()
        if t_id in db["users"]:
            db["users"][t_id]["balance"] = round(db["users"][t_id]["balance"] + amt, 4)
            save_db(db)
            bot.reply_to(message, f"✅ **Added successfully!**\n👤 User: `{t_id}`\n💵 Balance: `{db['users'][t_id]['balance']}` $")
            try: bot.send_message(int(t_id), f"🎉 **Admin added `{amt}` $ to your balance.**")
            except: pass
        else:
            bot.reply_to(message, f"❌ User ID `{t_id}` ডেটাবেজে পাওয়া যায়নি!")
    except Exception as e:
        bot.reply_to(message, f"❌ AddBalance Engine Error: {e}")

@bot.message_handler(commands=['backup'])
def admin_selective_backup(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        db = load_db()
        users_data = db.get("users", {})
        report = "📊 CUSTOMER BALANCES & DAILY HISTORY REPORT BACKUP\n\n"
        for u_id, details in users_data.items():
            report += f"👤 User: {details.get('username', 'Unknown')} (ID: {u_id})\n💰 Balance: {details.get('balance', 0.0)} $\n"
            report += "---------------------------------------------------------\n"
        bio = io.BytesIO(report.encode('utf-8'))
        bio.name = "backup.txt"
        bot.send_document(ADMIN_ID, bio, caption="📦 **Backup Complete!**")
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

# --- WORK PERFECT /pay ---
@bot.message_handler(commands=['pay'])
def admin_pay_text(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        match = re.match(r'/pay\s+(\d+)\s+(.+)', message.text.strip())
        if not match:
            bot.reply_to(message, "💡 **Format:** `/pay USER_ID TxID` \nExample: `/pay 6394277892 bkash-123456`")
            return
        t_id = match.group(1)
        tx_id = match.group(2)
        user_msg = f"✅ **WITHDRAW PAID SUCCESSFUL**\n━━━━━━━━━━━━━━━━━━━━\n🔔 **Status:** PAID\n🆔 **TxID:** `{tx_id}`"
        try: 
            bot.send_message(int(t_id), user_msg, parse_mode='Markdown')
            bot.reply_to(message, f"🚀 Withdraw Paid Successfully To `{t_id}`.")
        except: pass
    except: pass

@bot.message_handler(content_types=['photo'])
def admin_photo_payout(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        caption = message.caption.strip() if message.caption else None
        if caption and caption.isdigit():
            user_msg = "✅ **WITHDRAW PAID SUCCESSFUL**\n━━━━━━━━━━━━━━━━━━━━\n📸 **Payment Proof Screenshot:**"
            try: bot.send_photo(int(caption), message.photo[-1].file_id, caption=user_msg, parse_mode='Markdown')
            except: pass
            bot.reply_to(message, f"🚀 Sent to `{caption}`.")
    except: pass

# --- INITIALIZER POLLING RUNNER ---
if __name__ == '__main__':
    load_db()
    
    # 🧵 প্রথম প্যানেলের থ্রেড চালু করা হলো
    t1 = threading.Thread(target=sms_forwarder_loop_1, daemon=True)
    t1.start()
    
    # 🧵 দ্বিতীয় নতুন প্যানেলের থ্রেড চালু করা হলো
    t2 = threading.Thread(target=sms_forwarder_loop_2, daemon=True)
    t2.start()
    
    while True:
        try: 
            bot.polling(none_stop=True, timeout=40, long_polling_timeout=20)
        except: 
            time.sleep(5)
