import logging
from telegram import Update
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
)
from datetime import datetime
import sqlite3
from threading import Lock
from googletrans import Translator, LANGUAGES

# Initialize translator
translator = Translator()

# Database setup
DB_NAME = 'group_manager.db'
db_lock = Lock()

# Supported languages
SUPPORTED_LANGS = {
    'en': 'English',
    'id': 'Indonesian',
    'my': 'Myanmar'
}

# Bot configuration
TOKEN = "YOUR_BOT_TOKEN"
ADMINS = [123456789]  # Replace with your admin IDs
LOG_CHANNEL = -1001234567890  # Replace with your log channel ID

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class GroupManager:
    def __init__(self):
        self._init_db()
        self.updater = Updater(TOKEN, use_context=True)
        self.dispatcher = self.updater.dispatcher
        
        # Add handlers
        self._add_handlers()
        
    def _init_db(self):
        with db_lock:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS groups (
                    group_id INTEGER PRIMARY KEY,
                    group_name TEXT,
                    auto_translate BOOLEAN DEFAULT 0,
                    source_langs TEXT DEFAULT 'en,id',
                    target_lang TEXT DEFAULT 'my'
                )
            ''')
            conn.commit()
            conn.close()
    
    def _add_handlers(self):
        # Admin commands
        admin_filter = Filters.user(ADMINS)
        self.dispatcher.add_handler(CommandHandler("ban", self.ban_user, filters=admin_filter))
        self.dispatcher.add_handler(CommandHandler("translate", self.toggle_translation, filters=admin_filter))
        
        # Translation handler
        self.dispatcher.add_handler(MessageHandler(
            Filters.text & Filters.group & ~Filters.command,
            self.handle_translation
        ))
    
    def _get_group_settings(self, group_id):
        with db_lock:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM groups WHERE group_id = ?', (group_id,))
            result = cursor.fetchone()
            conn.close()
            
            if not result:
                # Default settings
                return {
                    'group_id': group_id,
                    'auto_translate': False,
                    'source_langs': ['en', 'id'],
                    'target_lang': 'my'
                }
            
            return {
                'group_id': result[0],
                'group_name': result[1],
                'auto_translate': bool(result[2]),
                'source_langs': result[3].split(','),
                'target_lang': result[4]
            }
    
    def _update_group_settings(self, group_id, settings):
        with db_lock:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO groups 
                (group_id, group_name, auto_translate, source_langs, target_lang)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                group_id,
                settings.get('group_name', ''),
                int(settings.get('auto_translate', False)),
                ','.join(settings.get('source_langs', ['en', 'id'])),
                settings.get('target_lang', 'my')
            ))
            conn.commit()
            conn.close()
    
    def detect_language(self, text):
        try:
            detection = translator.detect(text)
            return detection.lang
        except Exception as e:
            logger.error(f"Language detection error: {e}")
            return None
    
    def translate_text(self, text, src_lang, dest_lang):
        try:
            translation = translator.translate(text, src=src_lang, dest=dest_lang)
            return translation.text
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return None
    
    def handle_translation(self, update: Update, context: CallbackContext):
        """Handle automatic message translation"""
        group_id = update.effective_chat.id
        message = update.effective_message
        settings = self._get_group_settings(group_id)
        
        # Skip if translation is disabled
        if not settings['auto_translate']:
            return
        
        # Skip if message is empty or too short
        if not message.text or len(message.text.strip()) < 5:
            return
        
        # Detect source language
        src_lang = self.detect_language(message.text)
        if not src_lang or src_lang not in settings['source_langs']:
            return
        
        # Skip if already in target language
        if src_lang == settings['target_lang']:
            return
        
        # Perform translation
        translated = self.translate_text(
            message.text,
            src_lang,
            settings['target_lang']
        )
        
        if translated:
            # Send translation as a reply
            reply_text = (
                f"🌐 Translated from {SUPPORTED_LANGS.get(src_lang, src_lang)} to "
                f"{SUPPORTED_LANGS.get(settings['target_lang'], settings['target_lang'])}:\n\n"
                f"{translated}"
            )
            message.reply_text(reply_text)
    
    def toggle_translation(self, update: Update, context: CallbackContext):
        """Toggle automatic translation in the group"""
        group_id = update.effective_chat.id
        settings = self._get_group_settings(group_id)
        
        # Toggle the setting
        new_setting = not settings['auto_translate']
        settings['auto_translate'] = new_setting
        
        # Update group name if available
        if update.effective_chat.title:
            settings['group_name'] = update.effective_chat.title
        
        self._update_group_settings(group_id, settings)
        
        status = "enabled" if new_setting else "disabled"
        update.message.reply_text(
            f"🌍 Auto-translation has been {status}.\n"
            f"Currently translating from: {', '.join(settings['source_langs'])}\n"
            f"Target language: {settings['target_lang']}"
        )
    
    def ban_user(self, update: Update, context: CallbackContext):
        """Ban a user from the group"""
        if not update.message.reply_to_message:
            update.message.reply_text("Please reply to the user's message to ban them.")
            return
        
        user = update.message.reply_to_message.from_user
        chat_id = update.message.chat.id
        
        try:
            context.bot.ban_chat_member(chat_id, user.id)
            update.message.reply_text(f"🚫 User {user.mention_html()} has been banned.")
        except Exception as e:
            logger.error(f"Error banning user: {e}")
            update.message.reply_text("Failed to ban user. I might not have admin privileges.")

    def run(self):
        """Run the bot"""
        self.updater.start_polling()
        self.updater.idle()

if __name__ == '__main__':
    # Install required packages: pip install googletrans==4.0.0-rc1
    bot = GroupManager()
    bot.run()