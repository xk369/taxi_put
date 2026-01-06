import random
import pdfrw
from datetime import datetime, timedelta
import pytz
import logging
import os

logger = logging.getLogger(__name__)

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False
    logger.error("PyMuPDF не установлен. Конвертация PDF в JPG недоступна. Установите: pip install PyMuPDF")

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    logger.error("Pillow не установлен. Конвертация PDF в JPG недоступна. Установите: pip install Pillow")

class PDFFiller:
    def __init__(self, font_name="Helvetica", font_size=10, field_font_sizes=None):
        """
        Инициализация PDFFiller с настройками шрифта
        
        Args:
            font_name: Название шрифта (Helvetica, Times-Roman, Courier, Arial и т.д.)
            font_size: Размер шрифта по умолчанию (по умолчанию 10)
            field_font_sizes: Словарь с индивидуальными размерами для каждого поля
                             Например: {'start_date': 12, 'serial_number': 10}
        """
        self.template_path = None
        self.font_name = font_name
        self.font_size = font_size
        self.field_font_sizes = field_font_sizes or {}
    
    def set_font(self, font_name, font_size=None):
        """
        Устанавливает шрифт для заполнения полей
        
        Args:
            font_name: Название шрифта (Helvetica, Times-Roman, Courier, Arial, DejaVuSans и т.д.)
            font_size: Размер шрифта (если None, остается текущий)
        
        Доступные стандартные шрифты PDF:
        - Helvetica (без засечек, самый популярный)
        - Times-Roman (с засечками)
        - Courier (моноширинный)
        - Symbol (символы)
        - ZapfDingbats (символы)
        """
        self.font_name = font_name
        if font_size is not None:
            self.font_size = font_size
        logger.info(f"Шрифт установлен: {font_name}, размер: {self.font_size}")
    
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
            
            # Функция для извлечения имени поля
            def get_field_name(field):
                """Извлекает имя поля из объекта pdfrw"""
                if hasattr(field, 'T') and field.T:
                    field_name_raw = str(field.T)
                    # Убираем скобки если есть
                    if field_name_raw.startswith('(') and field_name_raw.endswith(')'):
                        return field_name_raw[1:-1]
                    return field_name_raw
                return None
            
            # Собираем все поля из всех страниц
            all_fields = {}
            for page_num, page in enumerate(template.pages):
                if page.Annots:
                    for field in page.Annots:
                        field_name = get_field_name(field)
                        if field_name:
                            field_name_normalized = field_name.strip().lower()
                            all_fields[field_name] = {
                                'field': field,
                                'normalized': field_name_normalized,
                                'page': page_num
                            }
                            logger.info(f"Найдено поле на странице {page_num + 1}: '{field_name}' (нормализовано: '{field_name_normalized}')")
            
            # Также проверяем поля формы через AcroForm (если есть)
            if hasattr(template.Root, 'AcroForm') and template.Root.AcroForm:
                if hasattr(template.Root.AcroForm, 'Fields') and template.Root.AcroForm.Fields:
                    def process_form_fields(fields, parent_name=''):
                        """Рекурсивно обрабатывает поля формы"""
                        for field in fields:
                            field_name = get_field_name(field)
                            if field_name:
                                full_name = f"{parent_name}.{field_name}" if parent_name else field_name
                                field_name_normalized = full_name.strip().lower()
                                if full_name not in all_fields:
                                    all_fields[full_name] = {
                                        'field': field,
                                        'normalized': field_name_normalized,
                                        'page': None
                                    }
                                    logger.info(f"Найдено поле формы: '{full_name}' (нормализовано: '{field_name_normalized}')")
                            # Обрабатываем вложенные поля
                            if hasattr(field, 'Kids') and field.Kids:
                                process_form_fields(field.Kids, parent_name=field_name if field_name else parent_name)
                    
                    process_form_fields(template.Root.AcroForm.Fields)
            
            logger.info(f"Всего найдено полей: {len(all_fields)}")
            logger.info(f"Доступные данные для заполнения: {list(times.keys())}")
            
            # Заполняем поля
            filled_count = 0
            for field_name, field_info in all_fields.items():
                field = field_info['field']
                field_name_normalized = field_info['normalized']
                
                # Ищем соответствие в данных (проверяем точное совпадение и нормализованное)
                matched_key = None
                for key in times.keys():
                    key_normalized = key.lower()
                    # Проверяем точное совпадение, нормализованное совпадение и частичное совпадение
                    if (field_name == key or 
                        field_name_normalized == key_normalized or
                        field_name_normalized.endswith('.' + key_normalized) or
                        field_name_normalized.startswith(key_normalized + '.')):
                        matched_key = key
                        break
                
                if matched_key:
                    field_value = str(times[matched_key])
                    
                    # Обновляем значение поля
                    field.update(pdfrw.PdfDict(V=field_value))
                    
                    # Определяем размер шрифта для этого поля
                    field_font_size = self.field_font_sizes.get(matched_key, self.font_size)
                    
                    # Устанавливаем шрифт через DA (Default Appearance)
                    da_string = f"/{self.font_name} {field_font_size} Tf 0 g"
                    field.update(pdfrw.PdfDict(DA=da_string))
                    
                    # Устанавливаем выравнивание текста
                    if not hasattr(field, 'Q') or field.Q is None:
                        field.update(pdfrw.PdfDict(Q=0))
                    
                    # Убеждаемся, что поле не только для чтения
                    if hasattr(field, 'Ff'):
                        # Снимаем флаг ReadOnly если он установлен
                        ff_value = field.Ff if field.Ff else 0
                        field.update(pdfrw.PdfDict(Ff=ff_value & ~1))  # Убираем бит ReadOnly
                    
                    filled_count += 1
                    logger.info(f"✓ Заполнено поле '{field_name}' → '{matched_key}' = '{field_value}'")
                else:
                    logger.warning(f"⚠ Поле '{field_name}' не найдено в данных для заполнения")
            
            logger.info(f"Заполнено полей: {filled_count} из {len(all_fields)}")
            
            # Сохраняем PDF с заполненными полями
            pdfrw.PdfWriter().write(output_path, template)
            logger.info("PDF успешно сохранен")
            
            # 🔥 ВАЖНО: Flatten полей формы - встраиваем значения в визуальное содержимое страницы
            # Без этого поля формы не будут видны при конвертации в JPG
            if HAS_FITZ:
                try:
                    logger.info("Выполняем flatten полей формы...")
                    pdf_doc = fitz.open(output_path)
                    
                    for page_num in range(len(pdf_doc)):
                        page = pdf_doc[page_num]
                        widgets = page.widgets()
                        
                        if widgets:
                            logger.info(f"Найдено {len(widgets)} виджетов на странице {page_num + 1}")
                            
                            for widget in widgets:
                                field_name = widget.field_name
                                field_value = widget.field_value
                                
                                if field_value:
                                    logger.debug(f"Обрабатываем поле '{field_name}' = '{field_value}'")
                                    
                                    # Получаем координаты и параметры поля
                                    rect = widget.rect
                                    
                                    # Определяем размер шрифта
                                    font_size = self.font_size
                                    if field_name in self.field_font_sizes:
                                        font_size = self.field_font_sizes[field_name]
                                    
                                    # Вставляем текст на страницу в позицию поля
                                    # Используем нижний левый угол с небольшим отступом
                                    text_point = fitz.Point(rect.x0 + 2, rect.y1 - 3)
                                    
                                    try:
                                        page.insert_text(
                                            text_point,
                                            str(field_value),
                                            fontsize=font_size,
                                            fontname=self.font_name,
                                            color=(0, 0, 0),  # Черный цвет
                                            render_mode=0  # Заполнение (fill)
                                        )
                                        logger.debug(f"Текст '{field_value}' вставлен в поле '{field_name}'")
                                    except Exception as e:
                                        logger.warning(f"Не удалось вставить текст в поле '{field_name}': {e}")
                            
                            # Удаляем виджеты после вставки текста
                            page.delete_widgets()
                            logger.info(f"Виджеты удалены со страницы {page_num + 1}")
                    
                    # Сохраняем обновленный PDF
                    pdf_doc.save(output_path, incremental=False, encryption=fitz.PDF_ENCRYPT_KEEP)
                    pdf_doc.close()
                    logger.info("Flatten выполнен успешно - поля формы встроены в визуальное содержимое")
                except Exception as e:
                    logger.error(f"Ошибка при flatten PDF: {e}", exc_info=True)
                    logger.warning("Продолжаем без flatten - поля формы могут не отображаться в JPG")
            else:
                logger.warning("PyMuPDF не доступен, flatten пропущен. Поля формы могут не отображаться в JPG.")
            
            return output_path
            
        except Exception as e:
            logger.error(f"Ошибка в fill_pdf: {e}")
            raise
    
    def pdf_to_jpg(self, pdf_path, jpg_path=None, dpi=200):
        """
        Конвертирует PDF в JPG изображение
        
        Args:
            pdf_path: Путь к PDF файлу
            jpg_path: Путь для сохранения JPG (если None, создается автоматически)
            dpi: Разрешение изображения (по умолчанию 200)
        
        Returns:
            str: Путь к созданному JPG файлу
        """
        if not HAS_FITZ:
            raise ImportError("PyMuPDF не установлен. Установите его: pip install PyMuPDF")
        
        if not HAS_PIL:
            raise ImportError("Pillow не установлен. Установите его: pip install Pillow")
        
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF файл не найден: {pdf_path}")
        
        try:
            # Открываем PDF
            pdf_document = fitz.open(pdf_path)
            
            # Если JPG путь не указан, создаем автоматически
            if jpg_path is None:
                jpg_path = pdf_path.replace('.pdf', '.jpg')
            
            # Конвертируем первую страницу (или все страницы, если их несколько)
            # Для многостраничного PDF создаем одно изображение со всеми страницами
            images = []
            for page_num in range(len(pdf_document)):
                page = pdf_document[page_num]
                # Рендерим страницу как изображение с заданным DPI
                mat = fitz.Matrix(dpi / 72, dpi / 72)  # 72 - стандартный DPI PDF
                pix = page.get_pixmap(matrix=mat)
                images.append(pix)
            
            pdf_document.close()
            
            # Используем PIL для надежного сохранения в JPG
            # (уже импортирован в начале файла)
            
            if len(images) == 1:
                # Конвертируем одну страницу в PIL Image и сохраняем как JPG
                pix = images[0]
                pil_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                pil_img.save(jpg_path, 'JPEG', quality=95, optimize=True)
                logger.info(f"PDF конвертирован в JPG: {jpg_path} (размер: {os.path.getsize(jpg_path)} байт)")
            else:
                # Если несколько страниц - объединяем вертикально
                total_height = sum(img.height for img in images)
                max_width = max(img.width for img in images)
                
                # Создаем новое изображение для всех страниц
                combined_image = Image.new('RGB', (max_width, total_height), 'white')
                y_offset = 0
                for img in images:
                    pil_img = Image.frombytes("RGB", [img.width, img.height], img.samples)
                    combined_image.paste(pil_img, (0, y_offset))
                    y_offset += img.height
                
                combined_image.save(jpg_path, 'JPEG', quality=95, optimize=True)
                logger.info(f"PDF ({len(images)} страниц) конвертирован в JPG: {jpg_path} (размер: {os.path.getsize(jpg_path)} байт)")
            
            return jpg_path
            
        except Exception as e:
            logger.error(f"Ошибка при конвертации PDF в JPG: {e}")
            raise