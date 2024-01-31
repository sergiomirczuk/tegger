import tkinter as tk
from tkinter import messagebox, Text, Scrollbar, Frame
import json
import asyncio
import os
import re
import logging
import codecs
import random
import datetime
from telethon.sync import TelegramClient
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.types import InputPeerChannel
from telethon.tl.types import ChannelParticipantsSearch
from telethon.tl.types import InputPeerEmpty
from telethon.tl.functions.messages import GetDialogsRequest
from telethon.tl import types
from telethon.errors.rpcerrorlist import SlowModeWaitError, UserIsBlockedError, UserBannedInChannelError, ChatWriteForbiddenError, MessageIdInvalidError, ChatAdminRequiredError, MessageTooLongError, FloodWaitError, ForbiddenError, ChannelPrivateError
from PIL import Image, ImageTk
import requests
from io import BytesIO
import subprocess
import os
import threading
import queue

class TextHandler(logging.Handler):
    def __init__(self, text):
        logging.Handler.__init__(self)
        self.text = text

    def emit(self, record):
        msg = self.format(record)
        self.text.config(state="normal")
        self.text.insert(tk.END, msg + "\n")
        self.text.see(tk.END)
        self.text.config(state="disabled")
        self.text.update() 

        save_log_to_file(msg)  # Сохранение лога в файл

def save_log_to_file(log_entry):
    with codecs.open('log_file.txt', 'a', encoding='utf-8') as file:
        file.write(log_entry + "\n") 

def load_processed_members():
    try:
        with open('processed_members.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_processed_members(members):
    with open('processed_members.json', 'w') as f:
        json.dump(members, f)
        

logging.basicConfig(level=logging.INFO)

config = {}

def load_config():
    global config
    with open("config.json") as config_file:
        config = json.load(config_file)

def save_config():
    with open("config.json", "w") as config_file:
        json.dump(config, config_file, indent=4)

log_text = None
logger = logging.getLogger(__name__)
pending_members = {}  # Словарь для хранения участников, которым еще не было отправлено уведомление

async def main():
    client = TelegramClient('anon', config["api_id"], config["api_hash"])
    await client.start()

    dialogs = await client(GetDialogsRequest(
        offset_date=None,
        offset_id=0,
        offset_peer=InputPeerEmpty(),
        limit=200,
        hash=0
    ))

    groups = []
    for dialog in dialogs.dialogs:
        if isinstance(dialog.peer, types.PeerChannel):
            groups.append(dialog.peer)

    await send_notifications_to_random_groups(client, groups)

    await asyncio.sleep(30)
    


processed_members = load_processed_members()

async def send_notifications_to_random_groups(client, groups):
    global pending_members

    while True:
        random.shuffle(groups)
        for group in groups:
            if group.channel_id not in processed_members:
                if group.channel_id not in pending_members:
                    pending_members[group.channel_id] = set()
                await process_group(client, group, pending_members[group.channel_id])
                

async def process_group(client, group, pending_members):
    offset = 0
    limit = 200
    all_participants = []

    while True:
        try:
            participants = await client(GetParticipantsRequest(
                group, types.ChannelParticipantsSearch(''), offset, limit, hash=0
            ))
            if not participants.users:
                break
            all_participants.extend(participants.users)
            offset += len(participants.users)
        except (SlowModeWaitError, UserIsBlockedError, ForbiddenError, ChannelPrivateError, UserBannedInChannelError, ChatWriteForbiddenError, MessageIdInvalidError, ChatAdminRequiredError, MessageTooLongError, FloodWaitError) as e:
            logger.info(f"An error occurred while getting group participants: {e}")
            return

    last_message = await client.get_messages('me', limit=1)
    message = last_message[0].text if last_message else ""
    last_message_image = last_message[0].media if last_message else None
    user_count = 0

    try:
        group_entity = await client.get_entity(group)
        group_title = group_entity.title
        access_hash = group_entity.access_hash
    except (SlowModeWaitError, UserIsBlockedError, ForbiddenError, ChannelPrivateError, UserBannedInChannelError, ChatWriteForbiddenError, MessageIdInvalidError, ChatAdminRequiredError, MessageTooLongError, FloodWaitError) as e:
        logger.info(f"An error occurred while getting group info: {e}")
        return

    all_participant_ids = {user.id for user in all_participants if not user.bot and not getattr(user, 'admin_rights', None)}
    pending_members.update(all_participant_ids)

    for user in list(pending_members):
        try:
            user_entity = await client.get_entity(user)
            if user_entity.id not in processed_members or not processed_members[user_entity.id]:
                message += (f"[‌‌](tg://user?id={user_entity.id})")
                logger.info(f"Notification sent to user: {user_entity.username} in group: {group_title}")
                user_count += 1
                if user_count == config.get("max_mentions", 0):
                    break
                processed_members[user_entity.id] = True
                save_processed_members(processed_members)
            else:
                pending_members.remove(user)
        except (SlowModeWaitError, UserIsBlockedError, ForbiddenError, ChannelPrivateError, UserBannedInChannelError, ChatWriteForbiddenError, MessageIdInvalidError, ChatAdminRequiredError, MessageTooLongError, FloodWaitError) as e:
            logger.info(f"An error occurred while processing user: {e}")
            continue

    message += " "

    try:
        if last_message_image:
            await client.send_file(
                types.InputPeerChannel(group.channel_id, access_hash),
                last_message_image,
                caption=message,
                parse_mode='md'
            )
        else:
            await client.send_message(
                types.InputPeerChannel(group.channel_id, access_hash),
                message,
                parse_mode='md'
            )
        await asyncio.sleep(config.get("message_delay", 0))
    except (SlowModeWaitError, UserIsBlockedError, ForbiddenError, ChannelPrivateError, UserBannedInChannelError, ChatWriteForbiddenError, MessageIdInvalidError, ChatAdminRequiredError, MessageTooLongError, FloodWaitError) as e:
        logger.info(f"An error occurred while sending the message: {e}\n")


def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
    loop.close()

def start_bot_thread():
    load_processed_members()
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()

def run_program():
    program_path = os.path.join(os.path.dirname(__file__), "j.py")
    subprocess.Popen(["python3", program_path])
    logger.info("Program executed successfully.")  # Пример записи лога    
   

def create_gui():
    global log_text

    load_config()

    window = tk.Tk()
    window.title("Kovi Tagger")

    response = requests.get('https://cojo.ru/wp-content/uploads/2022/12/fon-dlia-telegi-1.webp')
    img_data = response.content
    img = Image.open(BytesIO(img_data))
    img = img.resize((600, 200))
    img = ImageTk.PhotoImage(img)
    panel = tk.Label(window, image=img)
    panel.pack(side="top", fill="both", expand="yes")

    api_frame = tk.Frame(window)
    api_frame.pack()

    api_id_label = tk.Label(api_frame, text="API ID:")
    api_id_label.pack(side="left")

    api_id_entry = tk.Entry(api_frame)
    api_id_entry.insert(0, config.get("api_id", ""))
    api_id_entry.pack(side="left")

    api_hash_label = tk.Label(api_frame, text="API Hash:")
    api_hash_label.pack(side="left")

    api_hash_entry = tk.Entry(api_frame)
    api_hash_entry.insert(0, config.get("api_hash", ""))
    api_hash_entry.pack(side="left")

    group_send_frame = tk.Frame(window)
    group_send_frame.pack()

    group_send_label = tk.Label(group_send_frame, text="Group Send Choice (all or specific):")
    group_send_label.pack(side="left")

    group_send_choice = tk.Entry(group_send_frame)
    group_send_choice.insert(0, config.get("group_send_choice", "all"))
    group_send_choice.pack(side="left")

    group_link_label = tk.Label(group_send_frame, text="Group Link (only for specific choice):")
    group_link_label.pack(side="left")

    group_link_entry = tk.Entry(group_send_frame)
    group_link_entry.insert(0, config.get("group_link", ""))
    group_link_entry.pack(side="left")

    update_api_button = tk.Button(window, text="Update API & Group Info", command=lambda: update_api(api_id_entry.get(), api_hash_entry.get(), group_send_choice.get(), group_link_entry.get()))
    update_api_button.pack()

    update_api_button = tk.Button(window, text="Join Groups", command=run_program)
    update_api_button.pack()

    settings_frame = tk.Frame(window)
    settings_frame.pack()

    message_delay_label = tk.Label(settings_frame, text="Message delay (seconds):")
    message_delay_label.pack(side="left")

    message_delay_entry = tk.Entry(settings_frame)
    message_delay_entry.insert(0, config.get("message_delay", 0))
    message_delay_entry.pack(side="left")

    group_delay_label = tk.Label(settings_frame, text="Group Delay (seconds):")
    group_delay_label.pack(side="left")

    group_delay_entry = tk.Entry(settings_frame)
    group_delay_entry.insert(0, config.get("group_delay", ""))
    group_delay_entry.pack(side="left")

    max_mentions_label = tk.Label(settings_frame, text="Max Mentions per message:")
    max_mentions_label.pack(side="left")

    max_mentions_entry = tk.Entry(settings_frame)
    max_mentions_entry.insert(0, config.get("max_mentions", 0))
    max_mentions_entry.pack(side="left")

    update_settings_button = tk.Button(window, text="Update Settings", command=lambda: update_settings(message_delay_entry.get(), group_delay_entry.get(), max_mentions_entry.get()))
    update_settings_button.pack()

    start_bot_button = tk.Button(window, text="Start Bot", command=start_bot_thread)
    start_bot_button.pack()

    log_frame = tk.Frame(window)
    log_frame.pack()

    log_label = tk.Label(log_frame, text="Bot Logs:")
    log_label.pack(side="left")

    log_text = Text(window, state="normal", height=15, width=100)
    log_text.pack()

    log_handler = TextHandler(log_text)
    logger.addHandler(log_handler)

    padding_frame = Frame(window, height=10)
    padding_frame.pack()

    window.mainloop()

def update_api(api_id, api_hash, group_send_choice, group_link):
    config["api_id"] = api_id
    config["api_hash"] = api_hash
    config["group_send_choice"] = group_send_choice
    config["group_link"] = group_link

    save_config()

def update_settings(message_delay, group_delay, max_mentions):
    config["message_delay"] = int(message_delay)
    config["group_delay"] = group_delay
    config["max_mentions"] = int(max_mentions)

    save_config()

if __name__ == "__main__":
    if os.path.exists("anon.session"):
        create_gui()
    else:
        load_config()
        start_bot_thread()
