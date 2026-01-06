import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from pdf_handler import PDFFiller
import os
import tempfile
try:
    from config import PDF_FONT_NAME, PDF_FONT_SIZE, PDF_FIELD_FONT_SIZES
except ImportError:
    PDF_FONT_NAME = 'Helvetica'
    PDF_FONT_SIZE = 10
    PDF_FIELD_FONT_SIZES = {}

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TaxiBot:
    def __init__(self, token):
        self.application = Application.builder().token(token).build()
        # Инициализируем PDFFiller с настройками шрифта из config
        self.pdf_filler = PDFFiller(
            font_name=PDF_FONT_NAME, 
            font_size=PDF_FONT_SIZE,
            field_font_sizes=PDF_FIELD_FONT_SIZES
        )
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
        """Генерирует путевой лист и отправляет как JPG"""
        pdf_path = None
        jpg_path = None
        try:
            # Создаем временный файл для PDF
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                pdf_path = tmp_file.name
            
            logger.info(f"Создан временный PDF файл: {pdf_path}")
            
            # Заполняем PDF с персональным шаблоном
            self.pdf_filler.fill_pdf(
                user_state['start_time'],
                user_state['odometer'],
                pdf_path
            )
            
            logger.info(f"PDF заполнен, начинаем конвертацию в JPG")
            
            # Конвертируем PDF в JPG
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_jpg:
                jpg_path = tmp_jpg.name
            
            logger.info(f"Создан временный JPG файл: {jpg_path}")
            
            # Конвертируем PDF в JPG
            self.pdf_filler.pdf_to_jpg(pdf_path, jpg_path)
            
            # Проверяем, что JPG файл создан
            if not os.path.exists(jpg_path):
                raise FileNotFoundError(f"JPG файл не был создан: {jpg_path}")
            
            file_size = os.path.getsize(jpg_path)
            logger.info(f"JPG файл создан, размер: {file_size} байт")
            
            # Отправляем JPG как фото
            with open(jpg_path, 'rb') as jpg_file:
                await update.message.reply_photo(
                    photo=jpg_file,
                    caption="✅ Ваш путевой лист готов!"
                )
            
            logger.info("JPG успешно отправлен пользователю")
            
            # Удаляем временные файлы
            if pdf_path and os.path.exists(pdf_path):
                os.unlink(pdf_path)
            if jpg_path and os.path.exists(jpg_path):
                os.unlink(jpg_path)
            
        except Exception as e:
            logger.error(f"Error generating waybill: {e}", exc_info=True)
            error_msg = f"❌ Ошибка при генерации путевого листа: {str(e)}\n\nПроверьте логи для подробностей."
            await update.message.reply_text(error_msg)
            
            # Очистка в случае ошибки
            if pdf_path and os.path.exists(pdf_path):
                try:
                    os.unlink(pdf_path)
                except:
                    pass
            if jpg_path and os.path.exists(jpg_path):
                try:
                    os.unlink(jpg_path)
                except:
                    pass

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