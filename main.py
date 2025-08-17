import os
import json
import logging
import time
import requests
import copy
import asyncio
import sys
import hashlib
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# =====================================================================
# ФИКС ДЛЯ WINDOWS
# =====================================================================
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# =====================================================================
# ЗАГРУЗКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ
# =====================================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

print("\n" + "=" * 50)
print("Проверка загруженных переменных:")
print(f"TELEGRAM_TOKEN: {'установлен' if TELEGRAM_TOKEN else 'НЕ НАЙДЕН!'}")
print(f"GEMINI_API_KEY: {'установлен' if GEMINI_API_KEY else 'НЕ НАЙДЕН!'}")
print("=" * 50 + "\n")

if not TELEGRAM_TOKEN:
    print("❌ КРИТИЧЕСКАЯ ОШИБКА: Токен Telegram бота не найден!")
    exit(1)

if not GEMINI_API_KEY:
    print("❌ КРИТИЧЕСКАЯ ОШИБКА: Ключ Gemini API не найден!")
    exit(1)

# =====================================================================
# НАСТРОЙКА ЛОГИРОВАНИЯ
# =====================================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log', mode='a', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.INFO)
logger = logging.getLogger(__name__)

logger.info("=" * 50)
logger.info("Начало работы бота")
logger.info(f"Токен Telegram: {TELEGRAM_TOKEN[:5]}...{TELEGRAM_TOKEN[-5:]}")
logger.info(f"Ключ Gemini: {GEMINI_API_KEY[:5]}...{GEMINI_API_KEY[-5:]}")
logger.info("=" * 50)

# =====================================================================
# КОНФИГУРАЦИЯ БОТА
# =====================================================================

# Обобщенный профиль пациента
PATIENT_PROFILE = {
    "age": 69,
    "health_issues": [
        "Нарушения в опорно-двигательной системе",
        "Нарушения в лимфатической системе",
        "Дегенеративно-дистрофические изменения позвоночника",
        "Нарушение водно-электролитного баланса",
        "Жировая инфильтрация печени",
        "Дефицит цинка",
        "Атеросклеротические бляшки",
        "Недостаточность пищеварения",
        "Дефицит аминокислот"
    ],
    "dietary_recommendations": [
        "Исключить сладости и кондитерские изделия",
        "Основа рациона: тушеные овощи и салаты",
        "Рекомендуемые овощи: морковь, свекла, цветная капуста",
        "Морепродукты: рыба, морская капуста",
        "Белки: птица, рыба, нежирные сорта мяса",
        "Орехи и семена",
        "Фрукты: апельсины, персики, абрикосы",
        "Продукты с витаминами А и Е"
    ],
    "contraindications": [
        "Повышенные нагрузки на позвоночник",
        "Длительное пребывание в некачественных помещениях",
        "Иррациональный график питания"
    ],
    "key_priorities": [
        "Укрепление позвоночника и суставов",
        "Нормализация водно-электролитного баланса",
        "Восполнение дефицита аминокислот и витаминов",
        "Поддержка сердечно-сосудистой системы",
        "Контроль веса при замедленном метаболизме"
    ]
}

# Вариативные компоненты для разнообразия
DAILY_VARIATIONS = {
    "breakfast_options": [
        "овсяная каша с орехами и абрикосами",
        "омлет с цветной капустой",
        "творог с морковным салатом",
        "гречневая каша с тушеными овощами"
    ],
    "lunch_options": [
        "запеченная рыба с тушеной свеклой",
        "куриная грудка с салатом из морской капусты",
        "тушеная индейка с цветной капустой",
        "рыбные котлеты с морковным пюре"
    ],
    "dinner_options": [
        "овощной салат с орехами",
        "тушеные овощи с семенами",
        "легкий суп с морской капустой",
        "салат из свеклы с грецкими орехами"
    ],
    "activity_suggestions": [
        "легкая прогулка на свежем воздухе 20-30 минут",
        "растяжка для позвоночника (5-10 минут)",
        "дыхательные упражнения",
        "легкие упражнения для суставов",
        "плавание или аквааэробика (если есть возможность)"
    ]
}


def get_system_prompt_with_date():
    """Генерирует системный промпт с учетом текущей даты для вариативности"""
    current_date = datetime.now()
    day_of_week = current_date.strftime("%A")
    date_str = current_date.strftime("%d.%m.%Y")

    # Создаем "семя" для псевдослучайности на основе даты
    date_seed = int(current_date.strftime("%Y%m%d"))
    random.seed(date_seed)

    # Выбираем варианты на день
    breakfast = random.choice(DAILY_VARIATIONS["breakfast_options"])
    lunch = random.choice(DAILY_VARIATIONS["lunch_options"])
    dinner = random.choice(DAILY_VARIATIONS["dinner_options"])
    activity = random.choice(DAILY_VARIATIONS["activity_suggestions"])

    return (
            f"Ты - персональный ассистент-нутрициолог для пациента старшего возраста. "
            f"Сегодня {day_of_week}, {date_str}. "
            f"Основываясь на медицинском отчете, давай научно обоснованные рекомендации по питанию и образу жизни. "

            "Ключевые особенности здоровья пациента:\n"
            + "\n".join([f"  • {issue}" for issue in PATIENT_PROFILE["health_issues"]]) + "\n\n"

                                                                                          "Диетические рекомендации:\n"
            + "\n".join([f"  • {rec}" for rec in PATIENT_PROFILE["dietary_recommendations"]]) + "\n\n"

                                                                                                "Приоритеты в питании:\n"
            + "\n".join([f"  • {priority}" for priority in PATIENT_PROFILE["key_priorities"]]) + "\n\n"

                                                                                                 "Противопоказания:\n"
            + "\n".join([f"  • {contra}" for contra in PATIENT_PROFILE["contraindications"]]) + "\n\n"

                                                                                                f"Рекомендации на сегодня ({day_of_week}):\n"
                                                                                                f"  • Завтрак: {breakfast}\n"
                                                                                                f"  • Обед: {lunch}\n"
                                                                                                f"  • Ужин: {dinner}\n"
                                                                                                f"  • Активность: {activity}\n\n"

                                                                                                "Особые указания:\n"
                                                                                                "1. Все рекомендации должны учитывать возраст и текущее состояние здоровья\n"
                                                                                                "2. Предлагать щадящие физические нагрузки\n"
                                                                                                "3. Особое внимание уделять продуктам, богатым недостающими аминокислотами\n"
                                                                                                "4. Контроль калорийности из-за замедленного метаболизма\n"
                                                                                                "5. Акцент на противовоспалительные продукты\n"
                                                                                                "6. Отвечать подробно, но понятно для человека старшего возраста\n"
                                                                                                "7. Использовать смайлики для поддержки 😊\n"
                                                                                                "8. Учитывать день недели при составлении рекомендаций\n"
                                                                                                "9. Варьировать советы в зависимости от дня"
    )


# =====================================================================
# КЛАСС NUTRITION ASSISTANT
# =====================================================================

class NutritionAssistant:
    API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
    MAX_INPUT_LENGTH = 2000  # Увеличено с 500
    MAX_HISTORY_LENGTH = 10  # Максимум сообщений в истории
    SESSION_TIMEOUT = timedelta(hours=4)  # Увеличено с 2 часов

    def __init__(self):
        self.user_sessions = {}
        self.last_cleanup = datetime.now()

    def _get_user_session(self, user_id):
        if datetime.now() - self.last_cleanup > timedelta(minutes=30):
            self.cleanup_sessions()
            self.last_cleanup = datetime.now()

        if user_id not in self.user_sessions:
            # Обновляем системный промпт каждый день
            current_date = datetime.now().strftime("%Y-%m-%d")
            self.user_sessions[user_id] = {
                "history": [{
                    "role": "user",
                    "parts": [{"text": get_system_prompt_with_date()}]
                }],
                "last_interaction": datetime.now(),
                "date_created": current_date
            }
        else:
            # Проверяем, нужно ли обновить системный промпт на новый день
            session_date = self.user_sessions[user_id].get("date_created", "")
            current_date = datetime.now().strftime("%Y-%m-%d")

            if session_date != current_date:
                # Обновляем системный промпт на новый день
                self.user_sessions[user_id]["history"][0] = {
                    "role": "user",
                    "parts": [{"text": get_system_prompt_with_date()}]
                }
                self.user_sessions[user_id]["date_created"] = current_date
                logger.info(f"Обновлен системный промпт для пользователя {user_id} на {current_date}")

        return self.user_sessions[user_id]

    def _trim_history(self, history):
        """Обрезает историю, оставляя системный промпт и последние сообщения"""
        if len(history) <= self.MAX_HISTORY_LENGTH + 1:  # +1 для системного промпта
            return history

        # Оставляем системный промпт и последние MAX_HISTORY_LENGTH сообщений
        return [history[0]] + history[-(self.MAX_HISTORY_LENGTH):]

    def cleanup_sessions(self):
        now = datetime.now()
        inactive_users = []

        for user_id, session in self.user_sessions.items():
            if now - session["last_interaction"] > self.SESSION_TIMEOUT:
                inactive_users.append(user_id)

        for user_id in inactive_users:
            del self.user_sessions[user_id]
            logger.info(f"Очищена сессия пользователя {user_id}")

    async def process_image(self, user_id, file_path):
        """Обрабатывает изображение еды"""
        try:
            import base64

            with open(file_path, "rb") as image_file:
                image_data = base64.b64encode(image_file.read()).decode('utf-8')

            session = self._get_user_session(user_id)
            history = copy.deepcopy(session["history"])
            history = self._trim_history(history)

            # Добавляем изображение и запрос на анализ
            history.append({
                "role": "user",
                "parts": [
                    {
                        "text": "Проанализируй это блюдо с точки зрения моей диеты. Подходит ли оно мне? Что можно улучшить?"},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": image_data
                        }
                    }
                ]
            })

            request_body = {
                "contents": history,
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 1024,
                },
                "safetySettings": [
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
                ]
            }

            response = requests.post(
                self.API_URL,
                headers={
                    'Content-Type': 'application/json',
                    'X-goog-api-key': GEMINI_API_KEY
                },
                json=request_body,
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                if 'candidates' in data and data['candidates']:
                    assistant_response = data['candidates'][0]['content']['parts'][0]['text']

                    # Обновляем историю
                    session["history"].append({
                        "role": "user",
                        "parts": [{"text": "Пользователь отправил фото еды для анализа"}]
                    })
                    session["history"].append({
                        "role": "model",
                        "parts": [{"text": assistant_response}]
                    })
                    session["history"] = self._trim_history(session["history"])
                    session["last_interaction"] = datetime.now()

                    return assistant_response

            return "Не удалось проанализировать изображение. Попробуйте еще раз. 📸"

        except Exception as e:
            logger.error(f"Ошибка обработки изображения: {str(e)}")
            return "Произошла ошибка при анализе изображения. 😕"

    def get_response(self, user_id, user_input):
        try:
            if len(user_input) > self.MAX_INPUT_LENGTH:
                user_input = user_input[:self.MAX_INPUT_LENGTH] + "..."
                logger.warning(f"Ввод пользователя {user_id} обрезан до {self.MAX_INPUT_LENGTH} символов")

            session = self._get_user_session(user_id)
            history = copy.deepcopy(session["history"])
            history = self._trim_history(history)

            history.append({
                "role": "user",
                "parts": [{"text": user_input}]
            })

            request_body = {
                "contents": history,
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 1024,
                },
                "safetySettings": [
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
                ]
            }

            logger.debug(f"Отправка запроса к Gemini API: {json.dumps(request_body, ensure_ascii=False)[:200]}...")

            response = requests.post(
                self.API_URL,
                headers={
                    'Content-Type': 'application/json',
                    'X-goog-api-key': GEMINI_API_KEY
                },
                json=request_body,
                timeout=30
            )

            logger.info(f"Статус ответа Gemini: {response.status_code}")

            if response.status_code != 200:
                logger.error(f"Ошибка Gemini API: {response.text}")
                return "Извините, произошла ошибка при обращении к AI-сервису. Попробуйте позже. 😔"

            data = response.json()

            if 'promptFeedback' in data and 'blockReason' in data['promptFeedback']:
                reason = data['promptFeedback']['blockReason']
                logger.warning(f"Запрос заблокирован: {reason}")
                return "Запрос содержит недопустимый контент. Пожалуйста, переформулируйте вопрос. ⚠️"

            if 'candidates' not in data or not data['candidates']:
                logger.error("Нет кандидатов в ответе API")
                return "Не удалось получить ответ. Пожалуйста, переформулируйте вопрос. 🤔"

            candidate = data['candidates'][0]
            if 'content' not in candidate or 'parts' not in candidate['content']:
                logger.error("Неверная структура ответа API")
                return "Ошибка обработки ответа. Попробуйте снова. 😕"

            assistant_response = candidate['content']['parts'][0]['text']

            # Обновляем историю с обрезкой
            session["history"].append({
                "role": "user",
                "parts": [{"text": user_input}]
            })
            session["history"].append({
                "role": "model",
                "parts": [{"text": assistant_response}]
            })

            session["history"] = self._trim_history(session["history"])
            session["last_interaction"] = datetime.now()

            logger.info(f"Ответ получен ({len(assistant_response)} символов)")
            return assistant_response

        except requests.exceptions.Timeout:
            logger.error("Таймаут при запросе к Gemini API")
            return "Превышено время ожидания ответа. Попробуйте позже. ⏰"
        except requests.exceptions.ConnectionError:
            logger.error("Ошибка подключения к Gemini API")
            return "Проблемы с подключением к сервису. Проверьте интернет-соединение. 🌐"
        except Exception as e:
            logger.error(f"Исключение в get_response: {str(e)}")
            return "Произошла непредвиденная ошибка. Пожалуйста, попробуйте позже. 😟"


# =====================================================================
# ИНИЦИАЛИЗАЦИЯ АССИСТЕНТА
# =====================================================================
assistant = NutritionAssistant()


# =====================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =====================================================================

async def send_long_message(context, chat_id, text, reply_markup=None):
    MAX_LENGTH = 4096

    parts = []
    while text:
        if len(text) <= MAX_LENGTH:
            parts.append(text)
            break

        split_index = text.rfind('\n', 0, MAX_LENGTH)
        if split_index == -1:
            split_index = text.rfind(' ', 0, MAX_LENGTH)
            if split_index == -1:
                split_index = MAX_LENGTH

        parts.append(text[:split_index])
        text = text[split_index:].lstrip()

    for i, part in enumerate(parts):
        markup = reply_markup if i == len(parts) - 1 else None
        await context.bot.send_message(
            chat_id=chat_id,
            text=part,
            reply_markup=markup
        )
        time.sleep(0.3)


def get_quick_actions_keyboard():
    current_day = datetime.now().strftime("%A")
    day_names = {
        "Monday": "понедельник", "Tuesday": "вторник", "Wednesday": "среда",
        "Thursday": "четверг", "Friday": "пятница", "Saturday": "суббота", "Sunday": "воскресенье"
    }
    day_ru = day_names.get(current_day, current_day)

    keyboard = [
        [InlineKeyboardButton(f"🍎 Меню на {day_ru}", callback_data="menu_today")],
        [InlineKeyboardButton("💊 Добавки и витамины", callback_data="supplements")],
        [InlineKeyboardButton("🏃‍♀️ Активность на сегодня", callback_data="activity")],
        [InlineKeyboardButton("📋 Список покупок", callback_data="shopping_list")],
        [InlineKeyboardButton("💧 Питьевой режим", callback_data="water")],
        [InlineKeyboardButton("📊 Дневник питания", callback_data="diary")],
    ]
    return InlineKeyboardMarkup(keyboard)


# =====================================================================
# ОБРАБОТЧИКИ КОМАНД
# =====================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        logger.info(f"Обработка /start от {user.id} (@{user.username})")

        current_date = datetime.now().strftime("%d.%m.%Y")
        current_day = datetime.now().strftime("%A")
        day_names = {
            "Monday": "понедельник", "Tuesday": "вторник", "Wednesday": "среда",
            "Thursday": "четверг", "Friday": "пятница", "Saturday": "суббота", "Sunday": "воскресенье"
        }
        day_ru = day_names.get(current_day, current_day)

        welcome_message = (
            f"👩‍⚕️ Здравствуйте! Сегодня {day_ru}, {current_date}\n\n"
            f"Я ваш персональный AI-ассистент по нутрициологии.\n\n"
            f"Я помогу вам с:\n"
            f"✅ Персонализированным питанием с учетом дня недели\n"
            f"✅ Анализом фотографий еды 📸\n"
            f"✅ Рекомендациями по образу жизни\n"
            f"✅ Планированием меню\n"
            f"✅ Контролем важных показателей здоровья\n\n"
            f"💡 Совет: Можете отправить фото своего блюда для анализа!\n\n"
            f"Чем могу помочь в этот {day_ru}?"
        )

        await update.message.reply_text(
            welcome_message,
            reply_markup=get_quick_actions_keyboard()
        )

        logger.info("Приветственное сообщение отправлено")

    except Exception as e:
        logger.error(f"Ошибка в start: {str(e)}", exc_info=True)
        await update.message.reply_text("⚠️ Произошла ошибка. Попробуйте команду /start снова.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        user_input = update.message.text
        logger.info(f"Сообщение от {user.id}: {user_input[:50]}{'...' if len(user_input) > 50 else ''}")

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        response = assistant.get_response(user.id, user_input)
        logger.info(f"Получен ответ ({len(response)} символов)")

        if len(response) > 4000:
            logger.info("Отправка длинного сообщения")
            await send_long_message(
                context,
                update.effective_chat.id,
                response,
                get_quick_actions_keyboard()
            )
        else:
            await update.message.reply_text(
                response,
                reply_markup=get_quick_actions_keyboard()
            )

        logger.info("Ответ успешно отправлен")

    except Exception as e:
        logger.error(f"Ошибка обработки сообщения: {str(e)}", exc_info=True)
        await update.message.reply_text("⚠️ Произошла ошибка при обработке вашего сообщения.")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        logger.info(f"Получено фото от {user.id}")

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        await update.message.reply_text("📸 Анализирую ваше блюдо... Это может занять несколько секунд.")

        # Получаем файл
        photo = update.message.photo[-1]  # Берем самое качественное фото
        file = await context.bot.get_file(photo.file_id)

        # Скачиваем файл
        file_path = f"temp_photo_{user.id}_{int(time.time())}.jpg"
        await file.download_to_drive(file_path)

        try:
            # Обрабатываем изображение
            response = await assistant.process_image(user.id, file_path)

            if len(response) > 4000:
                await send_long_message(
                    context,
                    update.effective_chat.id,
                    response,
                    get_quick_actions_keyboard()
                )
            else:
                await update.message.reply_text(
                    response,
                    reply_markup=get_quick_actions_keyboard()
                )
        finally:
            # Удаляем временный файл
            if os.path.exists(file_path):
                os.remove(file_path)

        logger.info("Фото обработано и ответ отправлен")

    except Exception as e:
        logger.error(f"Ошибка обработки фото: {str(e)}", exc_info=True)
        await update.message.reply_text("⚠️ Произошла ошибка при анализе фотографии. Попробуйте еще раз.")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        user = query.from_user
        data = query.data
        logger.info(f"Нажата кнопка {data} пользователем {user.id}")

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        current_day = datetime.now().strftime("%A")
        day_names = {
            "Monday": "понедельник", "Tuesday": "вторник", "Wednesday": "среда",
            "Thursday": "четверг", "Friday": "пятница", "Saturday": "суббота", "Sunday": "воскресенье"
        }
        day_ru = day_names.get(current_day, current_day)

        if data == "menu_today":
            prompt = f"Составь персональное меню на {day_ru} с учетом моих потребностей. Учти особенности этого дня недели."
        elif data == "supplements":
            prompt = "Какие добавки и витамины мне особенно важны сегодня? Учти дефициты из моего отчета и время года."
        elif data == "activity":
            prompt = f"Какая физическая активность мне подойдет в {day_ru}? Учти проблемы с позвоночником и день недели."
        elif data == "shopping_list":
            prompt = "Создай список покупок на неделю с учетом моих диетических рекомендаций и сезонности."
        elif data == "water":
            prompt = "Как мне поддерживать водный баланс сегодня? Учти мой водно-электролитный дисбаланс и погодные условия."
        elif data == "diary":
            prompt = "Помоги мне вести дневник питания. Что важно отслеживать при моих особенностях здоровья?"
        else:
            prompt = "Помоги мне с персональными рекомендациями на сегодня"

        response = assistant.get_response(user.id, prompt)
        logger.info(f"Получен ответ ({len(response)} символов)")

        if len(response) > 4000:
            logger.info("Отправка длинного сообщения")
            await send_long_message(
                context,
                update.effective_chat.id,
                response,
                get_quick_actions_keyboard()
            )
        else:
            try:
                await query.edit_message_text(
                    response,
                    reply_markup=get_quick_actions_keyboard()
                )
            except Exception:
                # Если не удается отредактировать, отправляем новое сообщение
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=response,
                    reply_markup=get_quick_actions_keyboard()
                )

        logger.info("Сообщение обновлено")

    except Exception as e:
        logger.error(f"Ошибка обработки кнопки: {str(e)}", exc_info=True)
        try:
            await query.edit_message_text("⚠️ Произошла ошибка. Пожалуйста, попробуйте другой запрос.")
        except Exception:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="⚠️ Произошла ошибка. Пожалуйста, попробуйте другой запрос."
            )


async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        logger.info(f"Обработка /test от {user.id}")

        current_date = datetime.now().strftime("%d.%m.%Y %H:%M")
        session_info = ""

        if user.id in assistant.user_sessions:
            session = assistant.user_sessions[user.id]
            history_len = len(session["history"])
            last_interaction = session["last_interaction"].strftime("%H:%M")
            date_created = session.get("date_created", "неизвестно")
            session_info = f"📊 История: {history_len} сообщений\n🕐 Последнее: {last_interaction}\n📅 Создана: {date_created}\n"

        response = (
            f"🔧 Тест успешен! Бот работает правильно.\n\n"
            f"⏰ Текущее время: {current_date}\n"
            f"👤 Ваш ID: `{user.id}`\n"
            f"💬 Chat ID: `{update.effective_chat.id}`\n"
            f"👤 Имя: {user.full_name}\n"
            f"📱 Username: @{user.username if user.username else 'отсутствует'}\n\n"
            f"{session_info}"
            f"🤖 Версия: Улучшенная с поддержкой изображений"
        )

        await update.message.reply_text(response, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Ошибка в test_command: {str(e)}", exc_info=True)
        await update.message.reply_text("⚠️ Произошла ошибка при выполнении теста.")


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сброс сессии пользователя"""
    try:
        user = update.effective_user
        logger.info(f"Обработка /reset от {user.id}")

        if user.id in assistant.user_sessions:
            del assistant.user_sessions[user.id]
            response = "🔄 Ваша сессия сброшена! Все рекомендации будут обновлены с учетом сегодняшнего дня."
        else:
            response = "ℹ️ У вас нет активной сессии для сброса."

        await update.message.reply_text(response, reply_markup=get_quick_actions_keyboard())

    except Exception as e:
        logger.error(f"Ошибка в reset_command: {str(e)}", exc_info=True)
        await update.message.reply_text("⚠️ Произошла ошибка при сбросе сессии.")


# =====================================================================
# ОБРАБОТЧИК ОШИБОК
# =====================================================================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error = context.error
    logger.error(f"Глобальная ошибка: {str(error)}", exc_info=error)

    try:
        if update and hasattr(update, 'message') and update.message:
            await update.message.reply_text(
                "⚠️ Произошла непредвиденная ошибка. Разработчики уже уведомлены.\n"
                "Попробуйте повторить запрос позже или используйте /reset для сброса сессии."
            )
        elif update and hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.message.reply_text(
                "⚠️ Произошла непредвиденная ошибка. Разработчики уже уведомлены.\n"
                "Попробуйте повторить запрос позже или используйте /reset для сброса сессии."
            )
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение об ошибке: {str(e)}")


# =====================================================================
# ЗАПУСК БОТА
# =====================================================================

def main():
    try:
        logger.info("🚀 Запуск улучшенного бота...")

        # Создаем приложение
        application = Application.builder().token(TELEGRAM_TOKEN).build()

        # Добавляем обработчик ошибок
        application.add_error_handler(error_handler)

        # Регистрируем обработчики
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("test", test_command))
        application.add_handler(CommandHandler("reset", reset_command))
        application.add_handler(CallbackQueryHandler(button_handler))
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        logger.info("✅ Обработчики зарегистрированы")
        logger.info("🤖 Улучшенный бот запущен и ожидает сообщений...")
        print("🤖 Улучшенный бот запущен. Отправьте /start боту в Telegram")
        print("📸 Теперь поддерживается анализ фотографий еды!")
        print("🗓️ Рекомендации меняются каждый день!")

        # Запускаем бота с уменьшенным таймаутом
        application.run_polling(
            poll_interval=0.5,
            timeout=10
        )

    except Exception as e:
        logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА ПРИ ЗАПУСКЕ: {str(e)}", exc_info=True)
        print(f"❌ Критическая ошибка: {str(e)}")


if __name__ == "__main__":
    main()