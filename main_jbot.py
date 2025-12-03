import telebot
import threading
import time
import os

TOKEN = "8568346129:AAGZw8pbpPfzS6dEGewtU52ZrDUvd8MWPyM"
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

IDEAS_FILE = "ideas.txt"
FOOD_FILE = "food.txt"

ideas = []
food = []


# -------------------------------------------------
# Normalize all dash types
# -------------------------------------------------
def normalize_dashes(text):
    return text.replace("–", "-").replace("—", "-")


# -------------------------------------------------
# Load list from file
# -------------------------------------------------
def load_list(file_path):
    if not os.path.exists(file_path):
        with open(file_path, "w", encoding="utf-8") as f:
            pass
        return []

    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    return [line.strip() for line in lines if line.strip()]


# -------------------------------------------------
# Save list to file
# -------------------------------------------------
def save_list(file_path, data_list):
    with open(file_path, "w", encoding="utf-8") as f:
        for item in data_list:
            f.write(item + "\n")


# -------------------------------------------------
# Backup every 5 minutes
# -------------------------------------------------
def backup_loop():
    while True:
        save_list(IDEAS_FILE, ideas)
        save_list(FOOD_FILE, food)
        time.sleep(300)


# -------------------------------------------------
# /start
# -------------------------------------------------
@bot.message_handler(commands=["start"])
def start_command(message):
    bot.send_message(
        message.chat.id,
        "👋 Welcome! Type /help to get started."
    )


# -------------------------------------------------
# HELP (with or without '/')
# -------------------------------------------------
@bot.message_handler(commands=["help"])
def help_cmd(message):
    send_help(message.chat.id)


@bot.message_handler(func=lambda m: m.text.lower().strip() == "help")
def help_txt(message):
    send_help(message.chat.id)


def send_help(chat_id):
    help_text = (
        "🤖 <b>List Bot - Help</b>\n\n"
        "This bot helps you maintain two lists: ideas and shopping items.\n"
        "Use commands to add, delete and view both lists.\n"
        "Both lists are shared across all users.\n"
        "Everything is stored in text files and backed up automatically.\n\n"

        "🧠 <b>Ideas commands:</b>\n"
        "<code>addidea-Your idea text</code>\n"
        "<code>delidea-ID</code>\n"
        "<code>/showideas</code>\n\n"

        "🛒 <b>Shopping list commands:</b>\n"
        "<code>addfood-Item</code>\n"
        "<code>delfood-ID</code>\n"
        "<code>/showfood</code>\n\n"

        "📋 <b>Show everything:</b>\n"
        "<code>show</code>\n"
    )

    bot.send_message(chat_id, help_text)


# -------------------------------------------------
# /showideas
# -------------------------------------------------
@bot.message_handler(commands=["showideas"])
def show_ideas_command(message):
    if not ideas:
        bot.send_message(message.chat.id, "📭 Your idea list is empty.")
        return

    response = "🧠 <b>Your Ideas:</b>\n\n"
    for idx, idea in enumerate(ideas, start=1):
        response += f"[{idx}] - {idea}\n"

    bot.send_message(message.chat.id, response)


# -------------------------------------------------
# /showfood
# -------------------------------------------------
@bot.message_handler(commands=["showfood"])
def show_food_command(message):
    if not food:
        bot.send_message(message.chat.id, "🛒 Your shopping list is empty.")
        return

    response = "🛒 <b>Your Shopping List:</b>\n\n"
    for idx, item in enumerate(food, start=1):
        response += f"[{idx}] - {item}\n"

    bot.send_message(message.chat.id, response)


# -------------------------------------------------
# MAIN MESSAGE HANDLER
# -------------------------------------------------
@bot.message_handler(func=lambda m: True)
def main_handler(message):
    global ideas, food

    text = normalize_dashes(message.text.strip())
    text_lower = text.lower()

    print(f"[LOG] User {message.from_user.id} | Message: {text}")

    # -------------------------------------------------
    # ADD IDEA
    # -------------------------------------------------
    if text_lower.startswith("addidea-"):
        idea_text = text.split("addidea-", 1)[1].strip()

        if not idea_text:
            bot.send_message(message.chat.id, "⚠️ Please provide an idea after <code>addidea-</code>.")
            return

        ideas.append(idea_text)
        save_list(IDEAS_FILE, ideas)

        bot.send_message(
            message.chat.id,
            f"✅ Idea added!\n\n🆔 <b>ID:</b> {len(ideas)}\n💡 <b>Idea:</b> {idea_text}"
        )
        return

    # -------------------------------------------------
    # DELETE IDEA
    # -------------------------------------------------
    if text_lower.startswith("delidea-"):
        index_str = text_lower.split("delidea-", 1)[1].strip()

        if not index_str.isdigit():
            bot.send_message(message.chat.id, "⚠️ Invalid ID. Use: <code>delidea-3</code>")
            return

        index = int(index_str)

        if index < 1 or index > len(ideas):
            bot.send_message(message.chat.id, "⚠️ That idea ID does not exist.")
            return

        removed = ideas.pop(index - 1)
        save_list(IDEAS_FILE, ideas)

        bot.send_message(
            message.chat.id,
            f"🗑️ Idea deleted!\n\n🆔 <b>Deleted ID:</b> {index}\n❌ <b>Idea:</b> {removed}"
        )
        return

    # -------------------------------------------------
    # ADD FOOD
    # -------------------------------------------------
    if text_lower.startswith("addfood-"):
        food_text = text.split("addfood-", 1)[1].strip()

        if not food_text:
            bot.send_message(message.chat.id, "⚠️ Please provide an item after <code>addfood-</code>.")
            return

        food.append(food_text)
        save_list(FOOD_FILE, food)

        bot.send_message(
            message.chat.id,
            f"✅ Item added!\n\n🆔 <b>ID:</b> {len(food)}\n🍎 <b>Item:</b> {food_text}"
        )
        return

    # -------------------------------------------------
    # DELETE FOOD
    # -------------------------------------------------
    if text_lower.startswith("delfood-"):
        index_str = text_lower.split("delfood-", 1)[1].strip()

        if not index_str.isdigit():
            bot.send_message(message.chat.id, "⚠️ Invalid ID. Use: <code>delfood-3</code>")
            return

        index = int(index_str)

        if index < 1 or index > len(food):
            bot.send_message(message.chat.id, "⚠️ That food ID does not exist.")
            return

        removed = food.pop(index - 1)
        save_list(FOOD_FILE, food)

        bot.send_message(
            message.chat.id,
            f"🗑️ Item deleted!\n\n🆔 <b>Deleted ID:</b> {index}\n❌ <b>Item:</b> {removed}"
        )
        return

    # -------------------------------------------------
    # SHOW EVERYTHING
    # -------------------------------------------------
    if text_lower == "show":
        response = ""

        if ideas:
            response += "🧠 <b>Your Ideas:</b>\n"
            for idx, idea in enumerate(ideas, start=1):
                response += f"[{idx}] - {idea}\n"
        else:
            response += "🧠 <b>Your Ideas:</b>\n📭 Your idea list is empty.\n"

        response += "\n"

        if food:
            response += "🛒 <b>Your Shopping List:</b>\n"
            for idx, item in enumerate(food, start=1):
                response += f"[{idx}] - {item}\n"
        else:
            response += "🛒 <b>Your Shopping List:</b>\n🛒 Your shopping list is empty.\n"

        bot.send_message(message.chat.id, response)
        return

    # -------------------------------------------------
    # Unknown command
    # -------------------------------------------------
    bot.send_message(
        message.chat.id,
        "❓ Unknown command.\nType /help for instructions."
    )


ideas = load_list(IDEAS_FILE)
food = load_list(FOOD_FILE)

threading.Thread(target=backup_loop, daemon=True).start()

bot.infinity_polling()
