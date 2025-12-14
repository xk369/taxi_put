import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from pdf_handler import PDFFiller
import os
import tempfile

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TaxiBot:
    def __init__(self, token):
        self.application = Application.builder().token(token).build()
        self.pdf_filler = PDFFiller()  # Без статического шаблона
        self.user_data = {}
        
        self.setup_handlers()
    
    def setup_handlers(self):
        """Настройка обработчиков команд"""
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user_id = str(update.effective_user.id)  # Важно: str для сравнения
        
        # 🔥 НОВЫЙ ФУНКЦИОНАЛ: ищем шаблон по Telegram ID
        template_path = self.pdf_filler.find_driver_template(user_id)
        
        if not template_path:
            await update.message.reply_text(
                "❌ Ваш персональный шаблон не найден!\n"
                "Обратитесь к администратору для настройки."
            )
            return
        
        # Устанавливаем найденный шаблон
        self.pdf_filler.template_path = template_path
        
        self.user_data[user_id] = {
            'step': 'waiting_time',
            'template_path': template_path
        }
        
        await update.message.reply_text(
            "🚖 Добро пожаловать!\n\n"
            "Введите время начала смены в формате ЧЧ:MM\n"
            "Например: 08:00 или 13:21"
        )
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка сообщений от пользователя"""
        user_id = str(update.effective_user.id)
        text = update.message.text.strip()
        
        if user_id not in self.user_data:
            await update.message.reply_text("❌ Напишите /start для начала работы")
            return
        
        user_state = self.user_data[user_id]
        
        if user_state['step'] == 'waiting_time':
            if self.validate_time_format(text):
                user_state['start_time'] = text
                user_state['step'] = 'waiting_odometer'
                await update.message.reply_text(
                    f"⏱ Время принято: {text}\n\n"
                    "Теперь введите показания одометра (пробег):"
                )
            else:
                await update.message.reply_text(
                    "❌ Неверный формат времени!\n"
                    "Введите время в формате ЧЧ:MM (например: 08:00 или 13:21)"
                )
        
        elif user_state['step'] == 'waiting_odometer':
            if text.isdigit():
                user_state['odometer'] = text
                await self.generate_waybill(update, user_state)
                user_state['step'] = 'waiting_time'  # Сброс только шага
            else:
                await update.message.reply_text("❌ Пробег должен быть числом!")
    
    async def generate_waybill(self, update: Update, user_state):
        """Генерирует путевой лист"""
        try:
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                output_path = tmp_file.name
            
            # Заполняем PDF с персональным шаблоном
            self.pdf_filler.fill_pdf(
                user_state['start_time'],
                user_state['odometer'],
                output_path
            )
            
            with open(output_path, 'rb') as pdf_file:
                await update.message.reply_document(
                    document=pdf_file,
                    filename=f"waybill_{user_state['start_time'].replace(':', '')}.pdf",
                    caption="✅ Ваш путевой лист готов!"
                )
            
            os.unlink(output_path)
            
        except Exception as e:
            logger.error(f"Error generating waybill: {e}")
            await update.message.reply_text("❌ Ошибка при генерации путевого листа")

    def validate_time_format(self, time_str):
        """Проверяет формат времени"""
        try:
            time_str = time_str.strip()
            if ':' not in time_str:
                return False
            
            parts = time_str.split(':')
            if len(parts) != 2:
                return False
            
            hours, minutes = map(int, parts)
            return 0 <= hours <= 23 and 0 <= minutes <= 59
            
        except:
            return False

def main():
    BOT_TOKEN = "8157322601:AAFRQwyE_Hu8PwluDxWDNkAO2MigR1pTt4o"
    
    # 🔥 ИЗМЕНЕНИЕ: передаем только токен, без шаблона
    bot = TaxiBot(BOT_TOKEN)
    
    print("Бот запущен...")
    bot.application.run_polling()

if __name__ == "__main__":
    main()