import os
import asyncio
from datetime import datetime
from dotenv import load_dotenv
import anthropic
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

load_dotenv()

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

conversation_history = {}

tools = [
    {
        "name": "get_current_time",
        "description": "Возвращает текущую дату и время",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "save_note",
        "description": "Сохраняет заметку",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"}
            },
            "required": ["text"]
        }
    }
]

def get_current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def save_note(text: str):
    with open("notes.txt", "a") as f:
        f.write(f"[{datetime.now()}] {text}\n")
    return "Заметка сохранена!"

tool_map = {
    "get_current_time": get_current_time,
    "save_note": save_note
}

def run_agent(user_id: int, user_message: str) -> str:
    if user_id not in conversation_history:
        conversation_history[user_id] = []

    conversation_history[user_id].append({
        "role": "user",
        "content": user_message
    })

    messages = conversation_history[user_id].copy()

    while True:
        response = claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system="Ты личный помощник. Отвечай на русском языке. Будь кратким.",
            tools=tools,
            messages=messages
        )

        if response.stop_reason == "end_turn":
            final_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    final_text = block.text

            conversation_history[user_id].append({
                "role": "assistant",
                "content": final_text
            })

            if len(conversation_history[user_id]) > 20:
                conversation_history[user_id] = conversation_history[user_id][-20:]

            return final_text

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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text
    await update.message.reply_text("⏳ Думаю...")
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, run_agent, user_id, user_message)
        await update.message.reply_text(response)
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {str(e)}")

if __name__ == "__main__":
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Агент запущен!")
    app.run_polling()
