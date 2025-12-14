import random
import pdfrw
from datetime import datetime, timedelta
import pytz
import logging
import os

logger = logging.getLogger(__name__)

class PDFFiller:
    def __init__(self):
        self.template_path = None
    
    def find_driver_template(self, telegram_id, templates_dir="templates"):
        """Находит файл водителя по Telegram ID в имени файла"""
        if not os.path.exists(templates_dir):
            logger.error(f"Папка {templates_dir} не существует")
            return None
        
        # Простой поиск по имени файла
        expected_filename = f"driver_{telegram_id}.pdf"
        file_path = os.path.join(templates_dir, expected_filename)
        
        if os.path.exists(file_path):
            logger.info(f"Найден шаблон для ID {telegram_id}: {expected_filename}")
            return file_path
        else:
            logger.warning(f"Шаблон для ID {telegram_id} не найден")
            return None
    
    def generate_serial_number(self):
        """Генерирует серию и номер путевого листа"""
        series = str(random.randint(100000, 999999))
        number = str(random.randint(1000000, 9999999))
        serial_number = f"{series} - {number}"
        logger.info(f"Сгенерирован номер путевого листа: {serial_number}")
        return serial_number
    
    def format_time(self, time_str):
        """Форматирует время в стандартный вид ЧЧ:MM"""
        hours, minutes = map(int, time_str.split(':'))
        return f"{hours:02d}:{minutes:02d}"
    
    def calculate_times(self, start_time_str):
        """Рассчитывает все времена на основе времени начала смены"""
        try:
            formatted_start_time = self.format_time(start_time_str)
            logger.info(f"Расчет времен для: {start_time_str} → {formatted_start_time}")
            
            now = datetime.now(pytz.timezone('Europe/Moscow'))
            current_date = now.date()
            
            start_hour, start_minute = map(int, formatted_start_time.split(':'))
            start_time = now.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
            
            times = {
                'start_date': current_date.strftime('%d.%m.%Y'),
                'start_time': formatted_start_time,
                'med_time': (start_time + timedelta(minutes=5)).strftime('%H:%M'),
                'tech_time': (start_time + timedelta(minutes=15)).strftime('%H:%M'),
                'departure_time': (start_time + timedelta(minutes=21)).strftime('%H:%M'),
                'end_time': (start_time + timedelta(hours=9)).strftime('%H:%M')
            }
            
            end_datetime = start_time + timedelta(hours=9)
            times['end_date'] = end_datetime.strftime('%d.%m.%Y')
            
            times['med_date'] = (start_time + timedelta(minutes=5)).strftime('%d.%m.%Y')
            times['tech_date'] = (start_time + timedelta(minutes=15)).strftime('%d.%m.%Y') 
            times['departure_date'] = (start_time + timedelta(minutes=21)).strftime('%d.%m.%Y')
            
            logger.info(f"Рассчитанные времена: {times}")
            return times
            
        except Exception as e:
            logger.error(f"Ошибка в calculate_times: {e}")
            raise
    
    def fill_pdf(self, start_time_str, odometer_value, output_path):
        """Заполняет PDF шаблон данными"""
        try:
            if not self.template_path:
                raise ValueError("Шаблон не установлен")
            
            logger.info(f"Начало заполнения PDF: время={start_time_str}, одометр={odometer_value}")
            
            serial_number = self.generate_serial_number()
            times = self.calculate_times(start_time_str)
            
            times['odometr'] = str(odometer_value)
            times['serial_number'] = serial_number
            
            logger.info(f"Все данные для заполнения: {times}")
            
            if not os.path.exists(self.template_path):
                raise FileNotFoundError(f"Шаблон не найден: {self.template_path}")
            
            template = pdfrw.PdfReader(self.template_path)
            
            # Заполняем поля
            for page in template.pages:
                if page.Annots:
                    for field in page.Annots:
                        if hasattr(field, 'T') and field.T:
                            field_name = field.T[1:-1] if field.T.startswith('(') else field.T
                            if field_name in times:
                                field_value = times[field_name]
                                field.update(pdfrw.PdfDict(V=field_value))
            
            pdfrw.PdfWriter().write(output_path, template)
            logger.info("PDF успешно сохранен")
            return output_path
            
        except Exception as e:
            logger.error(f"Ошибка в fill_pdf: {e}")
            raise