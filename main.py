import os
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

from video_engine import burn_captions_to_video

# --- Web Server for Render Health Checks ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Auto Captions Engine is Active!")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"Health check server running on port {port}")
    server.serve_forever()

# --- Conversation Flow Mapping States ---
VIDEO_WAIT, CAPTION_WAIT = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 **Welcome to the Auto-Caption Video Generator Bot!**\n\n"
        "I will hardcode your custom text directly onto your video clip.\n\n"
        "👉 **Please upload your VIDEO file first** (Max 30 seconds):"
    )
    return VIDEO_WAIT

async def handle_video_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video = update.message.video
    
    # Check 30-second duration safety limit for free tier RAM protection
    if video.duration > 30:
        await update.message.reply_text("⚠️ *The video is too long.* Please send a short video under 30 seconds.")
        return VIDEO_WAIT
        
    context.user_data['target_video_id'] = video.file_id
    await update.message.reply_text(
        "✅ **Video clip received!**\n\n"
        "Now, type and send me the exact text/captions you want burned onto this video:"
    )
    return CAPTION_WAIT

async def handle_caption_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caption_words = update.message.text
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_video")
    status_msg = await update.message.reply_text("⏳ *Processing frames and embedding custom auto-captions... Please wait.*")
    
    video_id = context.user_data.get('target_video_id')
    
    input_vid = f"raw_{update.message.message_id}.mp4"
    output_vid = f"captioned_{update.message.message_id}.mp4"
    
    try:
        # Download video clip locally
        tg_file = await context.bot.get_file(video_id)
        await tg_file.download_to_drive(input_vid)
        
        # Execute the MoviePy rendering logic
        loop = asyncio.get_event_loop()
        success, error_log = await loop.run_in_executor(
            None, burn_captions_to_video, input_vid, caption_words, output_vid
        )
        
        if success:
            with open(output_vid, 'rb') as video_out:
                await update.message.reply_video(
                    video=video_out,
                    caption="🔥 Here is your auto-captioned video clip!"
                )
        else:
            await update.message.reply_text(f"Processing error: {error_log}")
            
    except Exception as e:
        print(f"Pipeline failure: {e}")
        await update.message.reply_text("❌ Failed to process video frame sequences.")
    finally:
        await status_msg.delete()
        # Storage clean up loops
        for f in (input_vid, output_vid):
            if os.path.exists(f):
                os.remove(f)
                
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Process canceled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def main():
    TOKEN = os.environ.get("TELEGRAM_TOKEN")
    if not TOKEN:
        raise ValueError("Missing TELEGRAM_TOKEN parameter environment setup.")

    threading.Thread(target=run_health_server, daemon=True).start()

    app = Application.builder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start), MessageHandler(filters.VIDEO, start)],
        states={
            VIDEO_WAIT: [MessageHandler(filters.VIDEO, handle_video_input)],
            CAPTION_WAIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_caption_text)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    app.add_handler(conv_handler)
    print("Auto-caption video engine polling live...")
    
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        while True:
            await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
