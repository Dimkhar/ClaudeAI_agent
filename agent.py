import os
import asyncio
from datetime import datetime
from dotenv import load_dotenv
import anthropic
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

load_dotenv()

# Клиенты
claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# История разговора (память в рамках сессии)
conversation_history = {}

# =====================
# ИНСТРУМЕНТЫ АГЕНТА
# =====================

def get_current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def calculate(expression: str):
    try:
        return str(eval(expression))
    except:
        return "Ошибка в выражении"

def save_note(text: str):
    with open("notes.txt", "a") as f:
        f.write(f"[{datetime.now()}] {text}\n")
    return "Заметка сохранена!"

def read_notes():
    try:
        with open("notes.txt", "r") as f:
            return f.read() or "Заметок пока нет"
    except:
        return "Заметок пока нет"

tool_map = {
    "get_current_time": get_current_time,
    "calculate": calculate,
    "save_note": save_note,
    "read_notes": read_notes
}

tools = [
    {
        "name": "get_current_time",
        "description": "Возвращает текущую дату и время",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "calculate",
        "description": "Вычисляет математическое выражение",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "Математическое выражение"}
            },
            "required": ["expression"]
        }
    },
    {
        "name": "save_note",
        "description": "Сохраняет заметку",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Текст заметки"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "read_notes",
        "description": "Читает все сохранённые заметки",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    }
]

# =====================
# ЛОГИКА АГЕНТА
# =====================

def run_agent(user_id: int, user_message: str) -> str:
    # Инициализируем историю для нового пользователя
    if user_id not in conversation_history:
        conversation_history[user_id] = []

    # Добавляем сообщение в историю
    conversation_history[user_id].append({
        "role": "user",
        "content": user_message
    })

    messages = conversation_history[user_id].copy()

    # Цикл агента
    while True:
        response = claude.messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            system="""Ты личный помощник пользователя. 
            Отвечай на русском языке.
            Используй инструменты когда это нужно.
            Будь кратким и полезным.""",
            tools=tools,
            messages=messages
        )

        # Финальный ответ
        if response.stop_reason == "end_turn":
            final_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    final_text = block.text

            # Сохраняем ответ в историю
            conversation_history[user_id].append({
                "role": "assistant",
                "content": final_text
            })

            # Ограничиваем историю последними 20 сообщениями
            if len(conversation_history[user_id]) > 20:
                conversation_history[user_id] = conversation_history[user_id][-20:]

            return final_text

        # Вызов инструментов
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    func = tool_map[block.name]
                    result = func(**block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })

            messages.append({"role": "user", "content": tool_results})

# =====================
# TELEGRAM ИНТЕРФЕЙС
# =====================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text

    # Показываем что агент думает
    await update.message.reply_text("⏳ Думаю...")

    try:
        response = run_agent(user_id, user_message)
        await update.message.reply_text(response)
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {str(e)}")

async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Агент запущен!")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())