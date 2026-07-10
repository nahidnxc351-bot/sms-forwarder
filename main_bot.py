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
PANEL_TOKEN = 'Q1ZXQjRSQn5zVlhDZm2FaEljjnRbi5iHW4J0gX5PhUGDImhFYHiQ'
API_URL = 'http://51.77.216.195/crapi/konek/viewstats'

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
processed_sms = set()
DATA_FILE = 'bot_data.json'

# Global temporary holding matrix for numbers pending admin release approval
PENDING_PACKS = {}

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
        db["users"][uid_str] = {"status": "allowed", "balance": 9999.0, "stats": {}, "history": {}}
        db["users"][uid_str]["username"] = username
        save_db(db)
        return db["users"][uid_str]
        
    if uid_str not in db["users"]:
        db["users"][uid_str] = {"status": "pending", "balance": 0.0, "stats": {}, "history": {}}
    db["users"][uid_str]["username"] = username
    save_db(db)
    return db["users"][uid_str]

def extract_otp(message):
    try:
        otp_match = re.search(r'\b\d{4,8}\b', message)
        if otp_match: return otp_match.group(0)
    except: pass
    return "N/A"

# --- CORE FORWARDER ENGINE ---
def sms_forwarder_loop():
    global processed_sms
    while True:
        try:
            with requests.get(f"{API_URL}?token={PANEL_TOKEN}", timeout=15) as res:
                if res.status_code == 200:
                    data = res.json()
                    if data.get('status') == 'success':
                        sms_list = data.get('data', [])
                        
                        if len(processed_sms) > 3000:
                            processed_sms.clear()
                            
                        for sms in reversed(sms_list):
                            num = str(sms.get('num', '')).strip()
                            msg_id = f"{num}_{sms.get('dt')}"
                            
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
                                
                                # Dynamic Prefix extraction based on registered prices database keys
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
                                    db["users"][target_uid]["history"][today]["earn"] = round(float(db["users"][target_uid]["history"][today].get("earn", 0.0)) + commission, 4)
                                    save_db(db)
                                    
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
                                    try: bot.send_message(int(target_uid), inbox_text, parse_mode='Markdown')
                                    except: pass
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

# --- BUY LOGIC WITH CHOSEN 10/20/50/100 CAP SYSTEM ---
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
        for size in [10, 20, 50, 100]:
            if avail >= size:
                admin_label = " ⏳ (Admin Approval Required)" if size == 100 else ""
                markup.add(types.InlineKeyboardButton(f"📁 Get {size} Numbers (.txt){admin_label}", callback_data=f"pullfile_{country}_{size}"))
        
        if avail > 0 and avail not in [10, 20, 50, 100]:
            markup.add(types.InlineKeyboardButton(f"📁 Get Remaining [{avail}] (.txt)", callback_data=f"pullfile_{country}_{avail}"))
            
        bot.edit_message_text(f"🌍 **Country:** `{country}`\n🔢 **Available:** `{avail}`\n\nSelect package pack size options below:", 
                              chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)
    except: pass

@bot.callback_query_handler(func=lambda call: call.data.startswith('pullfile_'))
def deliver_file_callback(call):
    global PENDING_PACKS
    try:
        parts = call.data.split('_')
        country, count = parts[1], int(parts[2])
        u_id = call.from_user.id
        u_name = call.from_user.username or call.from_user.first_name
        
        db = load_db()
        if len(db["stock"].get(country, [])) < count:
            bot.answer_callback_query(call.id, "❌ Stock changed, package choice size unavailable!", show_alert=True)
            return
            
        selected = db["stock"][country][:count]
        db["stock"][country] = db["stock"][country][count:]
        save_db(db)
        
        if count == 100:
            pack_id = f"pack_{u_id}_{int(time.time())}"
            PENDING_PACKS[pack_id] = {
                "user_id": u_id,
                "country": country,
                "numbers": selected
            }
            
            try: bot.delete_message(call.message.chat.id, call.message.message_id)
            except: pass
            
            bot.send_message(call.message.chat.id, "⏳ **Your request for [100 Numbers Pack] is sent to Admin for approval!**\nOnce approved, the file will be dropped into your chat loop instantly.")
            
            adm_markup = types.InlineKeyboardMarkup()
            adm_markup.add(
                types.InlineKeyboardButton("🟢 Approve Pack", callback_data=f"apk_approve_{pack_id}"),
                types.InlineKeyboardButton("❌ Deny Pack", callback_data=f"apk_deny_{pack_id}")
            )
            bot.send_message(ADMIN_ID, f"⚠️ **100 NUMBERS FILE REQUEST**\n\n👤 **User:** {u_name}\n🆔 **ID:** `{u_id}`\n🌍 **Country:** `{country}`\n\nAuthorize bulk export dispatch approval?", reply_markup=adm_markup)
            return

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

# --- BULK PACKS APPROVAL HANDLERS ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('apk_'))
def handle_admin_bulk_pack_decision(call):
    global PENDING_PACKS
    try:
        if call.from_user.id != ADMIN_ID: return
        action = "approve" if "approve" in call.data else "deny"
        pack_id = call.data.replace('apk_approve_', '').replace('apk_deny_', '')
        
        if pack_id not in PENDING_PACKS:
            bot.answer_callback_query(call.id, "❌ Error: Session expired!", show_alert=True)
            return
            
        meta = PENDING_PACKS[pack_id]
        u_id = meta["user_id"]
        country = meta["country"]
        numbers = meta["numbers"]
        
        db = load_db()
        
        if action == "approve":
            for num in numbers:
                db["mapping"][str(num)] = u_id
            save_db(db)
            
            file_data = "\n".join(numbers)
            bio = io.BytesIO(file_data.encode('utf-8'))
            bio.name = f"{country}_100_approved_numbers.txt"
            
            try: bot.send_document(int(u_id), bio, caption=f"🎉 **Admin approved your request!**\nHere are your `100` numbers for `{country}`.")
            except: pass
            bot.edit_message_text(f"✅ **Bulk Pack Approved!**\nFile successfully delivered to User ID: `{u_id}`", chat_id=call.message.chat.id, message_id=call.message.message_id)
        else:
            if country not in db["stock"]: db["stock"][country] = []
            db["stock"][country].extend(numbers)
            save_db(db)
            try: bot.send_message(int(u_id), f"❌ **Your request for 100 Numbers file for {country} was denied by the Admin.**")
            except: pass
            bot.edit_message_text(f"❌ **Bulk Pack Denied!**\nStock array rolled back successfully for `{country}`.", chat_id=call.message.chat.id, message_id=call.message.message_id)
            
        del PENDING_PACKS[pack_id]
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ Pack Approval Handler Core Exception: {e}")

# --- ACTIVE STOCK MANAGER COMMANDS (/delete & Inline Hooks) ---
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
            
        bot.send_message(message.chat.id, "🛠️ **Select a country stock to completely delete and stop inbox forwarding:**", reply_markup=markup)
    except: pass

@bot.callback_query_handler(func=lambda call: call.data.startswith('adm_del_'))
def handle_admin_stock_wipe(call):
    try:
        if call.from_user.id != ADMIN_ID: return
        country_target = call.data.replace('adm_del_', '')
        
        db = load_db()
        
        # ১. স্টক থেকে ওই দেশের নম্বর রিমুভ করা
        numbers_in_stock = db["stock"].get(country_target, [])
        if country_target in db["stock"]:
            db["stock"][country_target] = []
            
        # ২. ডাইনামিক প্রিফিক্স ডিটেকশন (যাতে কাস্টমারের অলরেডি নামানো ফাইলের ম্যাপিংও ডিলিট হয়)
        prefix_target = None
        if numbers_in_stock:
            first_num = re.sub(r'\D', '', str(numbers_in_stock[0]))
            price_keys = sorted(list(db.get("prices", {}).keys()), key=len, reverse=True)
            for pk in price_keys:
                if first_num.startswith(pk):
                    prefix_target = pk
                    break

        # ৩. ম্যাপিং তালিকা ক্লিন করা
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
        bot.answer_callback_query(call.id, f"🗑️ Stock & Mappings for {country_target} deleted!", show_alert=True)
        bot.edit_message_text(f"✅ **Stock Successfully Deleted!**\n🌍 Name: `{country_target}`\n❌ SMS routing and dynamic files for this prefix has been disconnected safely.", chat_id=call.message.chat.id, message_id=call.message.message_id)
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ Wipe runtime logic failure: {e}")

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
        bot.send_message(ADMIN_ID, f"📥 **WITHDRAW REQUEST**\n\n👤 User: {message.from_user.first_name}\n🆔 ID: `{u_id}`\n💰 Amount: `{current_bal}` $\n📝 Details: `{details}`\n\nTo Pay: `/pay {u_id} TxID` or caption photo with `{u_id}`")
    except: pass

# --- DYNAMIC FILE IMPORT LOOP ---
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
            
            if not cleaned_numbers:
                bot.reply_to(message, "❌ File-e kono valid number paowa jayni!")
                return
                
            db = load_db()
            if "stock" not in db: db["stock"] = {}
            if c_name not in db["stock"]: db["stock"][c_name] = []
            
            db["stock"][c_name].extend(cleaned_numbers)
            save_db(db)
            
            bot.reply_to(message, f"✅ **STOCK LOADED BY FILE NAME!**\n🌍 Stock Allocated Name: `{c_name}`\n🔢 Total Added: `{len(cleaned_numbers)}` Numbers.\n\n💡 *Note: Remotely update commissions using `/setprice` for matching prefixes.*")
    except Exception as e:
        bot.reply_to(message, f"❌ Error loading file name stream: {e}")

# --- CUSTOM DYNAMIC SETPRICE LOOP ENGINE ---
@bot.message_handler(commands=['setprice'])
def admin_set_price_init(message):
    if message.from_user.id != ADMIN_ID: return
    p = bot.send_message(message.chat.id, "⚙️ **[SET PRICE PANEL]**\n\nEnter the target country code prefix (e.g., `263`, `257`, `880`):", reply_markup=types.ForceReply(selective=True))
    bot.register_for_reply(p, admin_set_price_prefix_step)

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

# --- ADMIN AUXILIARY ACTIONS ---
@bot.message_handler(commands=['addbalance'])
def admin_add_balance(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        parts = message.text.split(' ')
        if len(parts) < 3:
            bot.reply_to(message, "💡 **Format:** `/addbalance USER_ID AMOUNT` \nExample: `/addbalance 6394277892 10`")
            return
            
        t_id = parts[1].strip()
        amt = float(parts[2].strip())
        
        db = load_db()
        if t_id in db["users"]:
            db["users"][t_id]["balance"] = round(db["users"][t_id]["balance"] + amt, 4)
            save_db(db)
            bot.reply_to(message, f"✅ **Added successfully!**\n👤 User: `{t_id}`\n💵 New Wallet Balance: `{db['users'][t_id]['balance']}` $")
            try: bot.send_message(int(t_id), f"🎉 **Admin added `{amt}` $ to your balance.**")
            except: pass
        else:
            bot.reply_to(message, "❌ User ID paowa jayni!")
    except Exception as e:
        bot.reply_to(message, f"❌ Parsing Error: {e}")

@bot.message_handler(commands=['backup'])
def admin_selective_backup(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        db = load_db()
        users_data = db.get("users", {})
        
        report = "📊 CUSTOMER BALANCES & DAILY HISTORY REPORT BACKUP\n"
        report += f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for u_id, details in users_data.items():
            username = details.get("username", "Unknown")
            balance = details.get("balance", 0.0)
            status = details.get("status", "pending")
            history = details.get("history", {})
            
            report += f"👤 User: {username} (ID: {u_id}) | Status: [{status}]\n"
            report += f"💰 Current Balance: {balance} $\n"
            report += "📅 10 Days History Logs:\n"
            
            has_history = False
            if isinstance(history, dict):
                for date_str, metrics in history.items():
                    report += f"   └── {date_str}: {metrics.get('count', 0)} OTPs | Earned: {metrics.get('earn', 0.0)} $\n"
                    has_history = True
            if not has_history:
                report += "   └── No active daily history logged.\n"
            report += "---------------------------------------------------------\n"
            
        bio = io.BytesIO(report.encode('utf-8'))
        bio.name = f"user_balances_history_backup_{datetime.now().strftime('%Y%m%d')}.txt"
        
        bot.send_document(ADMIN_ID, bio, caption="📦 **Clean Customer Report Backup Complete!**")
    except Exception as e:
        bot.reply_to(message, f"❌ Failed to parse clear backup: {e}")

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
            if cmd == 'allow':
                try: bot.send_message(int(t_id), "🎉 **Your account has been approved by the Admin!**")
                except: pass
    except: pass

@bot.message_handler(commands=['pay'])
def admin_pay_text(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        parts = message.text.split(' ', 2)
        t_id, tx_id = parts[1].strip(), parts[2].strip()
        user_msg = f"✅ **WITHDRAW PAID SUCCESSFUL**\n━━━━━━━━━━━━━━━━━━━━\n🔔 **Status:** PAID\n🆔 **TxID:** `{tx_id}`"
        try: bot.send_message(int(t_id), user_msg, parse_mode='Markdown')
        except: pass
        bot.reply_to(message, "🚀 Dispatched.")
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

# --- INITIALIZER WRAPPERS ---
if __name__ == '__main__':
    load_db()
    t = threading.Thread(target=sms_forwarder_loop, daemon=True)
    t.start()
    
    while True:
        try: bot.polling(none_stop=True, timeout=40, long_polling_timeout=20)
        except: time.sleep(5)
