import os
import time
import requests
import schedule
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EVOLUTION_API_URL = os.environ.get("EVOLUTION_API_URL", "http://localhost:8081")
EVOLUTION_API_KEY = os.environ.get("EVOLUTION_API_KEY", "")
INSTANCE_NAME = os.environ.get("INSTANCE_NAME", "FatQulBot")
TARGET_PHONE = os.environ.get("TARGET_PHONE", "")

def send_whatsapp_message(message: str):
    if not TARGET_PHONE:
        logger.warning("No TARGET_PHONE configured. Cannot send message.")
        return
        
    url = f"{EVOLUTION_API_URL}/message/sendText/{INSTANCE_NAME}"
    headers = {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "number": TARGET_PHONE,
        "text": message
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        logger.info("Message sent successfully")
    except Exception as e:
        logger.error(f"Failed to send message: {e}")

def daily_report():
    logger.info("Generating daily report...")
    # Here we would connect to SQLite /app/user_data/tradesv3.sqlite to calculate daily PnL
    message = "📈 *FatQul AI Trader - Daily Report*\n\nStatus: Running (Dry-Run)\nActive Pairs: 0\nDaily PNL: 0.00 IDR"
    send_whatsapp_message(message)

if __name__ == "__main__":
    logger.info("Starting FatQul WhatsApp Bot Service...")
    
    # Schedule daily report at 20:00 WIB
    schedule.every().day.at("20:00").do(daily_report)
    
    send_whatsapp_message("🚀 FatQul AI Trader WhatsApp Service Started.")
    
    while True:
        schedule.run_pending()
        time.sleep(60)
