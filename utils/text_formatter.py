"""
Утилита для форматирования и структурирования длинных текстов

Автоматически разбивает длинные тексты на читабельные части,
добавляет форматирование и пагинацию.
"""
import re
from typing import List, Tuple


def format_text(text: str, max_length: int = 3500) -> List[str]:
    """
    Форматирует текст и разбивает его на части для отправки в Telegram
    
    Args:
        text: Исходный текст
        max_length: Максимальная длина одной части (по умолчанию 3500 символов)
    
    Returns:
        Список отформатированных частей текста
    """
    if not text:
        return []
    
    # Улучшаем форматирование текста
    formatted_text = improve_formatting(text)
    
    # Разбиваем на части по логическим границам
    parts = split_text_smart(formatted_text, max_length)
    
    return parts


def improve_formatting(text: str) -> str:
    """
    Улучшает форматирование текста для лучшей читаемости
    
    - Добавляет форматирование заголовков
    - Улучшает списки
    - Добавляет отступы для абзацев
    """
    if not text:
        return text
    
    lines = text.split('\n')
    formatted_lines = []
    
    for line in lines:
        line = line.strip()
        if not line:
            formatted_lines.append('')
            continue
        
        # Определяем тип строки
        # Списки (начинаются с цифры, дефиса, точки) - обрабатываем первыми
        if is_list_item(line):
            # Убираем маркеры списка если они есть
            cleaned_line = re.sub(r'^[-*+•]\s*', '', line)
            cleaned_line = re.sub(r'^\d+[\.\)]\s*', '', cleaned_line)
            formatted_lines.append(f"  • {cleaned_line}")
        # Заголовки (короткие строки, часто с заглавной буквы)
        elif is_heading(line):
            formatted_lines.append(f"\n<b>{line}</b>\n")
        # Обычный текст
        else:
            formatted_lines.append(line)
    
    # Объединяем строки
    result = '\n'.join(formatted_lines)
    
    # Убираем множественные пустые строки (максимум 2 подряд)
    result = re.sub(r'\n{3,}', '\n\n', result)
    
    return result.strip()


def is_heading(line: str) -> bool:
    """
    Определяет, является ли строка заголовком
    
    Заголовки обычно:
    - Короткие (до 60 символов)
    - Не заканчиваются точкой
    - Часто содержат заглавные буквы
    """
    if len(line) > 60:
        return False
    
    if line.endswith(('.', '!', '?')):
        return False
    
    # Если строка короткая и содержит много заглавных букв
    uppercase_ratio = sum(1 for c in line if c.isupper()) / len(line) if line else 0
    if uppercase_ratio > 0.3 and len(line) < 40:
        return True
    
    # Если строка очень короткая (менее 30 символов) и не заканчивается точкой
    if len(line) < 30 and not line.endswith('.'):
        return True
    
    return False


def is_list_item(line: str) -> bool:
    """Определяет, является ли строка элементом списка"""
    # Убираем начальные пробелы для проверки
    stripped = line.lstrip()
    
    # Начинается с цифры и точки/скобки
    if re.match(r'^\d+[\.\)]', stripped):
        return True
    
    # Начинается с дефиса, звездочки или плюса
    if re.match(r'^[-*+•]', stripped):
        return True
    
    return False


def split_text_smart(text: str, max_length: int) -> List[str]:
    """
    Умное разбиение текста на части по логическим границам
    
    Разбивает текст не просто по символам, а по:
    - Абзацам (двойной перенос строки)
    - Предложениям (точка + пробел)
    - Словам (если очень длинное предложение)
    """
    if len(text) <= max_length:
        return [text]
    
    parts = []
    current_part = ""
    
    # Разбиваем по абзацам (двойной перенос строки)
    paragraphs = text.split('\n\n')
    
    for paragraph in paragraphs:
        # Если добавление абзаца не превысит лимит
        if len(current_part) + len(paragraph) + 2 <= max_length:
            if current_part:
                current_part += '\n\n' + paragraph
            else:
                current_part = paragraph
        else:
            # Текущая часть заполнена - сохраняем
            if current_part:
                parts.append(current_part)
            
            # Если абзац сам по себе длинный, разбиваем его
            if len(paragraph) > max_length:
                # Разбиваем по предложениям
                sentences = split_by_sentences(paragraph, max_length)
                for i, sentence_part in enumerate(sentences):
                    if i == 0:
                        current_part = sentence_part
                    else:
                        if len(current_part) + len(sentence_part) + 1 <= max_length:
                            current_part += '\n' + sentence_part
                        else:
                            parts.append(current_part)
                            current_part = sentence_part
            else:
                current_part = paragraph
    
    # Добавляем последнюю часть
    if current_part:
        parts.append(current_part)
    
    return parts if parts else [text[:max_length]]


def split_by_sentences(text: str, max_length: int) -> List[str]:
    """
    Разбивает текст по предложениям
    
    Если предложение слишком длинное, разбивает по словам
    """
    if len(text) <= max_length:
        return [text]
    
    # Разбиваем по предложениям (точка, восклицательный или вопросительный знак + пробел)
    sentences = re.split(r'([.!?]\s+)', text)
    
    # Объединяем разделители с предложениями
    result = []
    for i in range(0, len(sentences), 2):
        if i + 1 < len(sentences):
            sentence = sentences[i] + sentences[i + 1]
        else:
            sentence = sentences[i]
        
        if len(sentence) <= max_length:
            result.append(sentence)
        else:
            # Предложение слишком длинное - разбиваем по словам
            result.extend(split_by_words(sentence, max_length))
    
    return result if result else [text[:max_length]]


def split_by_words(text: str, max_length: int) -> List[str]:
    """Разбивает текст по словам"""
    if len(text) <= max_length:
        return [text]
    
    parts = []
    words = text.split()
    current_part = ""
    
    for word in words:
        if len(current_part) + len(word) + 1 <= max_length:
            if current_part:
                current_part += " " + word
            else:
                current_part = word
        else:
            if current_part:
                parts.append(current_part)
            current_part = word
    
    if current_part:
        parts.append(current_part)
    
    return parts if parts else [text[:max_length]]


def add_pagination_buttons(part_index: int, total_parts: int, material_id: int) -> List:
    """
    Создает кнопки пагинации для навигации по частям материала
    
    Args:
        part_index: Текущий индекс части (начиная с 0)
        total_parts: Общее количество частей
        material_id: ID материала
    
    Returns:
        Список кнопок для InlineKeyboardMarkup
    """
    buttons = []
    
    # Кнопки навигации (если больше одной части)
    if total_parts > 1:
        nav_buttons = []
        
        if part_index > 0:
            nav_buttons.append(
                ("◀️ Назад", f"material_page:{material_id}:{part_index - 1}")
            )
        
        nav_buttons.append(
            (f"📄 {part_index + 1}/{total_parts}", f"material_info:{material_id}")
        )
        
        if part_index < total_parts - 1:
            nav_buttons.append(
                ("Далее ▶️", f"material_page:{material_id}:{part_index + 1}")
            )
        
        buttons.append(nav_buttons)
    
    return buttons

