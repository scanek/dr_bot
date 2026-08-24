import os
import json
from datetime import datetime, time
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import pytz
import logging
from functools import wraps

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()

BOT_TOKEN = os.getenv('BIRTHDAY_BOT_TOKEN')
CHANNEL_ID = os.getenv('BIRTHDAY_CHANNEL_ID')
ADMIN_IDS_STR = os.getenv('ADMIN_IDS', '')
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_STR.split(',') if x.strip().isdigit()]

BIRTHDAYS_FILE = 'birthdays.json'
TIMEZONE = pytz.timezone('Europe/Moscow')

if not BOT_TOKEN:
    raise ValueError("BIRTHDAY_BOT_TOKEN не задан в .env файле")
if not CHANNEL_ID:
    raise ValueError("BIRTHDAY_CHANNEL_ID не задан в .env файле")

def check_admin(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if not ADMIN_IDS:
            logger.warning(f"ADMIN_IDS не настроен! Пользователь {user_id} обратился к боту.")
            await update.message.reply_text(
                f"⚠️ Бот не настроен.\nВаш Telegram ID: <code>{user_id}</code>\n"
                f"Добавьте его в переменную ADMIN_IDS в файле .env и перезапустите бота.",
                parse_mode='HTML'
            )
            return
        if user_id not in ADMIN_IDS:
            logger.warning(f"Неавторизованный доступ от {user_id}")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

def today_str() -> str:
    return datetime.now(TIMEZONE).strftime('%d-%m')

def is_valid_date(date_str: str) -> bool:
    try:
        datetime.strptime(date_str, '%d-%m')
        return True
    except ValueError:
        return False

def load_birthdays() -> list:
    if not os.path.exists(BIRTHDAYS_FILE):
        return []
    try:
        with open(BIRTHDAYS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Ошибка при загрузке {BIRTHDAYS_FILE}: {e}")
        return []

def save_birthdays(birthdays: list):
    try:
        with open(BIRTHDAYS_FILE, 'w', encoding='utf-8') as f:
            json.dump(birthdays, f, ensure_ascii=False, indent=4)
    except OSError as e:
        logger.error(f"Ошибка при сохранении {BIRTHDAYS_FILE}: {e}")
        raise

def find_birthdays_by_name(query: str, birthdays: list) -> list:
    query = query.strip().lower()
    return [entry for entry in birthdays if query in entry["name"].lower()]

@check_admin
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ['/add_birthday', '/delete_birthday'],
        ['/edit_birthday', '/view_birthdays'],
        ['/check_birthdays']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=False, resize_keyboard=True)
    await update.message.reply_text('👋 Привет! Выберите действие:', reply_markup=reply_markup)

@check_admin
async def add_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        'Введите данные в формате:\n\n<code>Имя Фамилия ДД-ММ</code>\n\nПример: Иван Петров 09-11',
        parse_mode='HTML'
    )

@check_admin
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text:
        return
    try:
        if ' ' not in text:
            raise ValueError("Не хватает данных.")
        *name_parts, date_str = text.rsplit(maxsplit=1)
        name = ' '.join(name_parts).strip()
        if not name:
            raise ValueError("Имя не указано.")
        if not is_valid_date(date_str):
            raise ValueError("Неверный формат даты.")
        birthdays = load_birthdays()
        for entry in birthdays:
            if entry["name"] == name and entry["date"] == date_str:
                await update.message.reply_text(f'⚠️ День рождения для {name} ({date_str}) уже существует.')
                return
        birthdays.append({"name": name, "date": date_str})
        save_birthdays(birthdays)
        await update.message.reply_text(f'✅ День рождения для <b>{name}</b> ({date_str}) добавлен!', parse_mode='HTML')
    except ValueError:
        if any(char.isdigit() for char in text):
            await update.message.reply_text(
                '❌ Неверный формат.\nВведите: <code>Имя Фамилия ДД-ММ</code>\nПример: Мария Иванова 09-11',
                parse_mode='HTML'
            )
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
        await update.message.reply_text('Произошла внутренняя ошибка. Попробуйте позже.')

@check_admin
async def view_birthdays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    birthdays = load_birthdays()
    if not birthdays:
        await update.message.reply_text('📅 Пока нет сохранённых дней рождения.')
        return
    response = '\n'.join([f'🎂 <b>{entry["name"]}</b> — {entry["date"]}' for entry in birthdays])
    await update.message.reply_text(response, parse_mode='HTML')

async def check_birthdays(context: ContextTypes.DEFAULT_TYPE):
    today = today_str()
    birthdays = load_birthdays()
    today_birthdays = [entry for entry in birthdays if entry['date'] == today]
    if not today_birthdays:
        logger.info("Сегодня нет дней рождения.")
        return
    for entry in today_birthdays:
        try:
            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=(
                    f'🎉 Сегодня день рождения у <b>{entry["name"]}</b>!\n'
                    f'От лица коллектива участка брикетирования — поздравляем с Днём Рождения! 🎉'
                ),
                parse_mode='HTML'
            )
            logger.info(f"Отправлено поздравление для {entry['name']}")
        except Exception as e:
            logger.error(f"Не удалось отправить поздравление для {entry['name']}: {e}")

@check_admin
async def manual_check_birthdays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('🔄 Запускаю проверку дней рождения...')
    await check_birthdays(context)
    await update.message.reply_text('✅ Проверка дней рождения завершена.')

@check_admin
async def delete_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    birthdays = load_birthdays()
    if not birthdays:
        await update.message.reply_text("Нет записей для удаления.")
        return
    if not context.args:
        names = "\n".join([f"{i+1}. {b['name']} ({b['date']})" for i, b in enumerate(birthdays)])
        await update.message.reply_text(
            "Укажите имя для удаления (можно частично). Пример: <code>/delete_birthday Иван</code>\n\nСписок:\n" + names,
            parse_mode='HTML'
        )
        return
    name_query = " ".join(context.args)
    matches = find_birthdays_by_name(name_query, birthdays)
    if not matches:
        await update.message.reply_text(f"Не найдено записей по запросу: {name_query}")
        return
    elif len(matches) == 1:
        entry = matches[0]
        birthdays.remove(entry)
        save_birthdays(birthdays)
        await update.message.reply_text(f"✅ Запись удалена: {entry['name']} ({entry['date']})")
    else:
        names = "\n".join([f"• {b['name']} ({b['date']})" for b in matches])
        await update.message.reply_text(f"Найдено несколько совпадений. Уточните имя:\n\n{names}")

@check_admin
async def edit_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    birthdays = load_birthdays()
    if not birthdays:
        await update.message.reply_text("Нет записей для редактирования.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Используйте формат: /edit_birthday \"Имя Фамилия\" ДД-ММ\nПример: /edit_birthday \"Иван Петров\" 09-11")
        return
    raw_args = " ".join(context.args)
    try:
        if raw_args.count('"') >= 2:
            parts = []
            in_quotes = False
            current = ""
            for char in raw_args:
                if char == '"':
                    in_quotes = not in_quotes
                elif char == ' ' and not in_quotes:
                    parts.append(current)
                    current = ""
                else:
                    current += char
            parts.append(current)
            if len(parts) < 2:
                raise ValueError()
            name = parts[-2].strip()
            date_str = parts[-1].strip()
        else:
            *name_parts, date_str = raw_args.rsplit(maxsplit=1)
            name = " ".join(name_parts).strip()
    except Exception:
        await update.message.reply_text("Не удалось распознать имя и дату. Попробуйте в кавычках.")
        return
    if not is_valid_date(date_str):
        await update.message.reply_text("Неверный формат даты. Используйте ДД-ММ.")
        return
    matches = find_birthdays_by_name(name, birthdays)
    if not matches:
        await update.message.reply_text(f"Не найдено записей по имени: {name}")
        return
    elif len(matches) > 1:
        names = "\n".join([f"• {b['name']} ({b['date']})" for b in matches])
        await update.message.reply_text(f"Найдено несколько совпадений. Уточните имя:\n\n{names}")
        return
    old_entry = matches[0]
    old_entry["date"] = date_str
    save_birthdays(birthdays)
    await update.message.reply_text(f"✅ Запись обновлена!\n<b>{old_entry['name']}</b>: {date_str}", parse_mode='HTML')

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('add_birthday', add_birthday))
    application.add_handler(CommandHandler('view_birthdays', view_birthdays))
    application.add_handler(CommandHandler('check_birthdays', manual_check_birthdays))
    application.add_handler(CommandHandler('delete_birthday', delete_birthday))
    application.add_handler(CommandHandler('edit_birthday', edit_birthday))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.job_queue.run_daily(
        check_birthdays,
        time=time(hour=8, minute=0, tzinfo=TIMEZONE)
    )
    logger.info("Бот запущен. Нажмите Ctrl+C для остановки.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
