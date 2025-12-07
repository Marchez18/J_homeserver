import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import os
import time
import threading
from datetime import datetime
import html

# =====================================================
# CONFIG
# =====================================================
TOKEN = "8528816841:AAFPhGuUOD66zFNOUN0hygitAYeUakWbW_I"
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

LISTS_DIR = "shopping_lists"  # folder where per-chat lists are stored

# chat_id -> [ { "name": str, "quantity": int, "added_at": str } ]
shopping_lists = {}
# chat_id -> pending state
# For "add":
#   {"type": "add", "stage": "waiting_quantity" / "waiting_confirm",
#    "name": str, "quantity": int|None, "created_at": float}
# For "delete":
#   {"type": "delete", "stage": "waiting_confirm",
#    "index": int, "item": dict, "created_at": float}
pending_actions = {}


# =====================================================
# FILE FUNCTIONS
# =====================================================
def ensure_dir():
    if not os.path.exists(LISTS_DIR):
        os.makedirs(LISTS_DIR)


def get_file_path(chat_id):
    ensure_dir()
    return os.path.join(LISTS_DIR, f"list_{chat_id}.txt")


def load_list(chat_id):
    """
    File format (one item per line):
    name|quantity|timestamp
    Example:
    milk|2|2025-12-07 18:45
    If the line has no pipes, treat it as 'name' only with quantity 1 and no timestamp.
    """
    path = get_file_path(chat_id)
    if not os.path.exists(path):
        return []

    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if "|" in line:
                parts = line.split("|")
                name = parts[0].strip()
                try:
                    quantity = int(parts[1])
                except (IndexError, ValueError):
                    quantity = 1
                added_at = parts[2].strip() if len(parts) > 2 else ""
            else:
                # old format: just the name
                name = line
                quantity = 1
                added_at = ""
            items.append(
                {
                    "name": name,
                    "quantity": quantity,
                    "added_at": added_at,
                }
            )
    return items


def save_list(chat_id):
    ensure_dir()
    path = get_file_path(chat_id)
    items = shopping_lists.get(chat_id, [])
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            name = item.get("name", "")
            quantity = item.get("quantity", 1)
            added_at = item.get("added_at", "")
            f.write(f"{name}|{quantity}|{added_at}\n")


def get_list_for_chat(chat_id):
    if chat_id not in shopping_lists:
        shopping_lists[chat_id] = load_list(chat_id)
    return shopping_lists[chat_id]


# =====================================================
# INLINE KEYBOARDS (YES / NO)
# =====================================================
def get_add_keyboard():
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton("✅ Yes", callback_data="add_yes"),
        InlineKeyboardButton("❌ No", callback_data="add_no"),
    )
    return kb


def get_delete_keyboard():
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton("✅ Yes", callback_data="delete_yes"),
        InlineKeyboardButton("❌ No", callback_data="delete_no"),
    )
    return kb


# =====================================================
# PENDING ACTIONS CLEANUP (every 5 minutes)
# =====================================================
def pending_cleanup_loop():
    while True:
        now = time.time()
        # make a copy of items to avoid RuntimeError while deleting
        for chat_id, action in list(pending_actions.items()):
            created_at = action.get("created_at", now)
            if now - created_at > 300:  # 5 minutes
                pending_actions.pop(chat_id, None)
                try:
                    bot.send_message(
                        chat_id,
                        "⏱️ Your previous pending action expired after 5 minutes. No action needed."
                    )
                except Exception:
                    # ignore send errors
                    pass
        time.sleep(300)


# =====================================================
# BASIC COMMANDS
# =====================================================
@bot.message_handler(commands=["start"])
def start_cmd(message):
    chat_id = message.chat.id
    get_list_for_chat(chat_id)  # force list creation/loading

    welcome_text = (
        "👋 Hi! Welcome to your personal Shopping List Bot.\n\n"
        "Here is how you can use me:\n\n"
        "• <b>/show</b> – Show your current shopping list (names only).\n"
        "• <b>/extra</b> – Show detailed list (name, quantity, timestamp, totals).\n"
        "• <b>/delete</b> – Show a numbered list so you can delete an item.\n"
        "• <b>/clearlist</b> – Remove <b>all</b> items from your shopping list.\n\n"
        "➕ To <b>add an item</b>, just send a normal message, for example:\n"
        "   <code>Milk</code>\n"
        "   I will ask for the quantity (number), and then ask you to confirm (✅ / ❌).\n\n"
        "🗑️ To <b>delete an item</b>:\n"
        "   1) Type <b>/delete</b> to see the numbered list.\n"
        "   2) Send the number of the item, e.g. <code>2</code>.\n"
        "   3) I will ask you to confirm (✅ Yes / ❌ No).\n\n"
        "ℹ️ Outside of the 'how many items?' step, if you send only a number, "
        "I will treat it as a delete command, not as a new item.\n\n"
        "⏱️ If you do not answer a pending question within 5 minutes, "
        "it will be automatically cleared."
    )

    bot.send_message(chat_id, welcome_text)


@bot.message_handler(commands=["help"])
def help_cmd(message):
    chat_id = message.chat.id
    help_text = (
        "🛒 <b>Shopping List Bot - Help</b>\n\n"
        "Available commands:\n\n"
        "• <b>/show</b> – Show the current list (names only).\n"
        "• <b>/extra</b> – Show detailed list with quantities, timestamps and totals.\n"
        "• <b>/delete</b> – Show the list with numbers so you can delete an item.\n"
        "• <b>/clearlist</b> – Remove all items from your shopping list.\n\n"
        "➕ <b>Add an item</b>:\n"
        "   1) Send any text (not a command), e.g.: <code>Whole milk</code>.\n"
        "   2) I will ask: <b>How many items?</b> – reply with a number.\n"
        "   3) I will show something like <code>Whole milk - 2 items</code> and ask "
        "for confirmation (✅ / ❌).\n\n"
        "🗑️ <b>Delete an item</b>:\n"
        "   1) Type <b>/delete</b> to see the numbered list.\n"
        "   2) Type the item number, e.g.: <code>2</code>.\n"
        "   3) I will ask for confirmation (✅ / ❌).\n\n"
        "ℹ️ When you send <b>only a number</b> and there is no 'quantity' question "
        "pending, it will be interpreted as a delete action.\n\n"
        "⏱️ If you do not answer a pending question within 5 minutes, "
        "I will clear it automatically."
    )
    bot.send_message(chat_id, help_text)


@bot.message_handler(commands=["show"])
def show_cmd(message):
    chat_id = message.chat.id
    items = get_list_for_chat(chat_id)

    if not items:
        bot.send_message(chat_id, "📭 Your shopping list is empty.")
        return

    text = "🛒 <b>Your shopping list (names only):</b>\n\n"
    for idx, item in enumerate(items, start=1):
        name = item.get("name", "")
        text += f"[{idx}] - {name}\n"

    bot.send_message(chat_id, text)


@bot.message_handler(commands=["extra"])
def extra_cmd(message):
    """
    Show detailed list: name, quantity, timestamp, totals, in table format.
    """
    chat_id = message.chat.id
    items = get_list_for_chat(chat_id)

    if not items:
        bot.send_message(chat_id, "📭 Your shopping list is empty.")
        return

    # Prepare rows: (ID, FOOD, QTY, TIMESTAMP)
    rows = []
    for idx, item in enumerate(items, start=1):
        id_str = str(idx)
        name = item.get("name", "")
        qty_str = str(item.get("quantity", 1))
        ts = item.get("added_at", "")
        # Escape name and timestamp to avoid breaking HTML
        name = html.escape(name)
        ts = html.escape(ts)
        rows.append((id_str, name, qty_str, ts))

    # Compute column widths
    id_w = max(len("ID"), max(len(r[0]) for r in rows))
    food_w = max(len("FOOD"), max(len(r[1]) for r in rows))
    qty_w = max(len("QTY"), max(len(r[2]) for r in rows))
    ts_w = max(len("TIMESTAMP"), max(len(r[3]) for r in rows))

    # Build table string
    header = (
        f"{'ID'.ljust(id_w)} | "
        f"{'FOOD'.ljust(food_w)} | "
        f"{'QTY'.ljust(qty_w)} | "
        f"{'TIMESTAMP'.ljust(ts_w)}"
    )

    separator = (
        f"{'-' * id_w}-+-"
        f"{'-' * food_w}-+-"
        f"{'-' * qty_w}-+-"
        f"{'-' * ts_w}"
    )

    lines = [header, separator]
    for r in rows:
        line = (
            f"{r[0].ljust(id_w)} | "
            f"{r[1].ljust(food_w)} | "
            f"{r[2].ljust(qty_w)} | "
            f"{r[3].ljust(ts_w)}"
        )
        lines.append(line)

    table_text = "\n".join(lines)

    total_items = len(items)
    total_quantity = sum(i.get("quantity", 1) for i in items)

    msg = (
        "📊 <b>Your shopping list (detailed):</b>\n\n"
        f"<pre>{table_text}</pre>\n\n"
        f"📦 <b>Total different items:</b> {total_items}\n"
        f"📦 <b>Total quantity:</b> {total_quantity}"
    )

    bot.send_message(chat_id, msg)


@bot.message_handler(commands=["delete"])
def delete_cmd(message):
    chat_id = message.chat.id
    items = get_list_for_chat(chat_id)

    if not items:
        bot.send_message(chat_id, "📭 There is nothing to delete, your list is empty.")
        return

    text = "🗑️ <b>Current items:</b>\n\n"
    for idx, item in enumerate(items, start=1):
        name = item.get("name", "")
        text += f"[{idx}] - {name}\n"

    text += "\nSend the <b>number</b> of the item you want to delete."
    bot.send_message(chat_id, text)


@bot.message_handler(commands=["clearlist"])
def clear_list_cmd(message):
    """
    Remove all items from the list for this chat.
    """
    chat_id = message.chat.id
    shopping_lists[chat_id] = []
    save_list(chat_id)
    bot.send_message(chat_id, "🧹 Your shopping list has been <b>cleared</b>.")


# =====================================================
# MAIN MESSAGE HANDLER
# =====================================================
@bot.message_handler(func=lambda m: True)
def main_handler(message):
    chat_id = message.chat.id
    text = (message.text or "").strip()

    # Ignore other commands, they are handled by specific handlers
    if text.startswith("/"):
        return

    action = pending_actions.get(chat_id)

    # If there is a pending action, handle it according to its stage
    if action:
        # ------------- ADD: waiting for quantity -------------
        if action["type"] == "add" and action.get("stage") == "waiting_quantity":
            if not text.isdigit():
                bot.send_message(
                    chat_id,
                    "⚠️ Please send a <b>number</b> for the quantity."
                )
                return

            quantity = int(text)
            if quantity <= 0:
                bot.send_message(
                    chat_id,
                    "⚠️ Quantity must be a positive number. Please try again."
                )
                return

            # update action with quantity and move to confirmation stage
            action["quantity"] = quantity
            action["stage"] = "waiting_confirm"
            pending_actions[chat_id] = action  # explicit

            item_name = action["name"]
            bot.send_message(
                chat_id,
                f"❓ Do you want to <b>add</b> this item to your list?\n\n"
                f"🛒 <b>Item:</b> {item_name} — {quantity} item(s)",
                reply_markup=get_add_keyboard()
            )
            return

        # ------------- Any other pending action: block text until Yes/No -------------
        bot.send_message(
            chat_id,
            "⚠️ Please answer the previous Yes/No confirmation first before "
            "sending a new item or delete request."
        )
        return

    # No pending action:
    # If the message is ONLY a number -> delete attempt
    if text.isdigit():
        items = get_list_for_chat(chat_id)

        if not items:
            bot.send_message(chat_id, "📭 Your list is empty, nothing to delete.")
            return

        index = int(text)

        if index < 1 or index > len(items):
            bot.send_message(chat_id, "⚠️ That number does not match any item in the list.")
            return

        item = items[index - 1]
        pending_actions[chat_id] = {
            "type": "delete",
            "stage": "waiting_confirm",
            "index": index - 1,
            "item": item,
            "created_at": time.time(),
        }

        bot.send_message(
            chat_id,
            f"❓ Do you want to <b>delete</b> this item?\n\n[{index}] - {item.get('name', '')}",
            reply_markup=get_delete_keyboard()
        )
        return

    # If it is not a command and not just a number, treat it as NEW ITEM NAME TO ADD
    item_text = text
    pending_actions[chat_id] = {
        "type": "add",
        "stage": "waiting_quantity",
        "name": item_text,
        "quantity": None,
        "created_at": time.time(),
    }

    bot.send_message(
        chat_id,
        f"🛒 You want to add: <b>{html.escape(item_text)}</b>\n\n"
        "❓ <b>How many items?</b> Please send a number.",
    )


# =====================================================
# CALLBACK HANDLER (YES / NO)
# =====================================================
@bot.callback_query_handler(func=lambda c: c.data in ["add_yes", "add_no", "delete_yes", "delete_no"])
def callback_handler(call):
    chat_id = call.message.chat.id
    data = call.data

    action = pending_actions.get(chat_id)

    if not action:
        bot.answer_callback_query(call.id, "There is no pending action.")
        return

    # --------------------------------------------
    # CONFIRM ADD
    # --------------------------------------------
    if data.startswith("add_") and action["type"] == "add":
        # We expect to be in "waiting_confirm" with name and quantity set
        name = action.get("name", "")
        quantity = action.get("quantity", 1)

        # Remove inline keyboard from the original message (best-effort)
        try:
            bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=None
            )
        except Exception:
            pass

        if data == "add_yes":
            items = get_list_for_chat(chat_id)
            added_at = datetime.now().strftime("%Y-%m-%d %H:%M")
            items.append(
                {
                    "name": name,
                    "quantity": quantity,
                    "added_at": added_at,
                }
            )
            save_list(chat_id)
            pending_actions.pop(chat_id, None)

            bot.send_message(
                chat_id,
                "✅ Item added to your list:\n"
                f"🛒 <b>{html.escape(name)}</b> — {quantity} item(s)\n"
                f"🕒 {added_at}"
            )
            bot.answer_callback_query(call.id, "Added.")
            return
        else:  # add_no
            pending_actions.pop(chat_id, None)
            bot.send_message(chat_id, "❌ Add action cancelled.")
            bot.answer_callback_query(call.id, "Cancelled.")
            return

    # --------------------------------------------
    # CONFIRM DELETE
    # --------------------------------------------
    if data.startswith("delete_") and action["type"] == "delete":
        idx = action.get("index")
        # Remove inline keyboard from the original message (best-effort)
        try:
            bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=None
            )
        except Exception:
            pass

        if data == "delete_yes":
            items = get_list_for_chat(chat_id)
            if isinstance(idx, int) and 0 <= idx < len(items):
                removed = items.pop(idx)
                save_list(chat_id)
                removed_name = removed.get("name", "")
                removed_qty = removed.get("quantity", 1)
                bot.send_message(
                    chat_id,
                    "✅ Item removed from your list:\n"
                    f"🗑️ <b>{html.escape(removed_name)}</b> — {removed_qty} item(s)"
                )
            else:
                bot.send_message(chat_id, "⚠️ Could not remove the item (invalid index).")
            pending_actions.pop(chat_id, None)
            bot.answer_callback_query(call.id, "Deleted.")
            return
        else:  # delete_no
            pending_actions.pop(chat_id, None)
            bot.send_message(chat_id, "❌ Delete action cancelled.")
            bot.answer_callback_query(call.id, "Cancelled.")
            return

    # Fallback (should not happen often)
    bot.answer_callback_query(call.id, "Invalid action.")


# =====================================================
# BOT STARTUP
# =====================================================
if __name__ == "__main__":
    ensure_dir()
    # start background cleaner for pending_actions
    threading.Thread(target=pending_cleanup_loop, daemon=True).start()
    print("Shopping list bot started...")
    bot.infinity_polling()
