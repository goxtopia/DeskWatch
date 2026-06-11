import urllib.request
import urllib.parse
import json
import threading
import time
from datetime import datetime
import logging
from backend.events import event_bus
from backend.config import load_config
from backend.db import get_today_records, get_daily_stats
from backend.health_monitor import calculate_sedentary_stats_for_today, calculate_drinking_count

logger = logging.getLogger("deskwatch.telegram")

# Global thread references
_bot_thread = None
_bot_running = False

def escape_html(text):
    if not isinstance(text, str):
        return str(text)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def send_telegram_message(token, chat_id, text):
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status == 200
    except Exception as e:
        logger.error(f"Error sending Telegram message: {e}")
        return False

def get_telegram_updates(token, offset=0):
    url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout=5"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            if response.status == 200:
                return json.loads(response.read().decode('utf-8'))
    except Exception:
        pass
    return None


def generate_today_status_message():
    config = load_config()
    records = get_today_records()
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # Get general daily stats
    stats_data = get_daily_stats(today_str)
    summary = stats_data.get("summary", {})
    
    # Compute duration
    sample_interval = config.get("sample_interval", 10)
    total_images = len(records)
    total_seconds = total_images * sample_interval
    minutes = total_seconds // 60
    hours = minutes // 60
    rem_min = minutes % 60
    duration_str = f"{hours}小时 {rem_min}分钟" if hours > 0 else f"{rem_min}分钟"
    
    # Sedentary stats
    sed_stats = calculate_sedentary_stats_for_today(records, config)
    overtime_min = sed_stats["overtime_minutes"]
    valid_breaks = sed_stats["valid_breaks"]
    
    # Drinking stats
    drinking_count = calculate_drinking_count(records, config)
    
    # Active model
    active_model = config.get("active_model", "clip").upper()
    
    # Build text
    msg = f"📊 <b>DeskWatch 今日数据日报 ({today_str})</b>\n\n"
    msg += f"🖥️ <b>当前运行模型</b>: {active_model}\n"
    msg += f"⏱️ <b>追踪时长</b>: {duration_str} ({total_images} 张图片)\n"
    msg += f"⏳ <b>久坐超时时长</b>: {overtime_min} 分钟\n"
    msg += f"🚶 <b>有效休息次数</b>: {valid_breaks} 次\n"
    msg += f"💧 <b>今日饮水次数</b>: {drinking_count} 次\n\n"
    
    msg += "📈 <b>各行为分类统计</b>:\n"
    if not summary:
        msg += "  暂无记录数据\n"
    else:
        # Sort by count descending
        sorted_summary = sorted(summary.items(), key=lambda x: x[1], reverse=True)
        for label, count in sorted_summary:
            cat_min = (count * sample_interval) // 60
            pct = (count / total_images) * 100 if total_images > 0 else 0
            escaped_label = escape_html(label)
            msg += f"  • <b>{escaped_label}</b>: {cat_min}分钟 ({pct:.1f}%)\n"
            
    return msg

def _bot_loop():
    global _bot_running
    offset = 0
    last_report_date = ""  # Format YYYY-MM-DD
    
    logger.info("Telegram bot loop entered.")
    while _bot_running:
        try:
            config = load_config()
            enabled = config.get("telegram_bot_enabled", False)
            token = config.get("telegram_bot_token", "").strip()
            chat_id = config.get("telegram_chat_id", "").strip()
            
            # Check and send Daily Report
            if enabled and token and chat_id and config.get("telegram_report_enabled", False):
                now = datetime.now()
                report_time_str = config.get("telegram_report_time", "21:00")
                try:
                    parts = report_time_str.split(":")
                    if len(parts) == 2:
                        rh, rm = map(int, parts)
                        today_str = now.strftime("%Y-%m-%d")
                        if now.hour == rh and now.minute == rm and today_str != last_report_date:
                            logger.info("Sending scheduled Telegram daily report...")
                            report_msg = generate_today_status_message()
                            send_telegram_message(token, chat_id, report_msg)
                            last_report_date = today_str
                except Exception as e:
                    logger.error(f"Error checking/sending scheduled report: {e}")

            # If bot is not enabled or token not configured, just sleep and check again
            if not enabled or not token:
                time.sleep(5)
                continue
                
            # Poll for updates
            updates = get_telegram_updates(token, offset)
            if updates and updates.get("ok"):
                for update in updates.get("result", []):
                    update_id = update.get("update_id")
                    offset = update_id + 1
                    
                    message = update.get("message")
                    if not message:
                        continue
                        
                    chat = message.get("chat", {})
                    sender_chat_id = chat.get("id")
                    text = message.get("text", "").strip()
                    
                    if text == "/start":
                        reply = f"👋 你好！我是 DeskWatch 助手。\n您的 Telegram Chat ID 是：<code>{sender_chat_id}</code>\n请将该 Chat ID 填入 DeskWatch 网页的<b>系统配置 -> Telegram配置</b>中，以启用提醒通知。"
                        send_telegram_message(token, sender_chat_id, reply)
                    elif text == "/status":
                        # If this is the configured chat_id, allow viewing stats
                        if str(sender_chat_id) == str(chat_id):
                            reply = generate_today_status_message()
                        else:
                            reply = "🔒 抱歉，您不是此 DeskWatch 实例的授权用户。请在网页上检查配置的 Chat ID。"
                        send_telegram_message(token, sender_chat_id, reply)
                        
        except Exception as e:
            logger.error(f"Exception in Telegram bot polling: {e}", exc_info=True)
            
        time.sleep(3)

def start_telegram_bot():
    global _bot_thread, _bot_running
    if _bot_running:
        return
    _bot_running = True
    _bot_thread = threading.Thread(target=_bot_loop, daemon=True)
    _bot_thread.start()
    logger.info("Telegram bot background thread started.")

def stop_telegram_bot():
    global _bot_running
    _bot_running = False
    logger.info("Telegram bot background thread stopped.")

def on_sedentary_alert(sedentary_minutes, timestamp):
    config = load_config()
    enabled = config.get("telegram_bot_enabled", False)
    token = config.get("telegram_bot_token", "").strip()
    chat_id = config.get("telegram_chat_id", "").strip()
    if enabled and token and chat_id:
        msg = f"⚠️ <b>久坐提醒</b>\n您已连续未活动超过 <b>{sedentary_minutes}</b> 分钟！\n请站起来活动一下，喝杯水或者伸展下身体。🚶‍♂️"
        send_telegram_message(token, chat_id, msg)

def init_telegram_bot():
    event_bus.subscribe("sedentary_alert", on_sedentary_alert)
    start_telegram_bot()
