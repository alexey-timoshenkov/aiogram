#! /usr/bin/env python
# -*- coding: utf-8 -*-

import sys, os, shutil, random
import sqlite3
import datetime
from time import sleep
from types import ModuleType
import threading
from hashlib import md5

import config_english

import requests
import telebot
from telebot.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, LabeledPrice
import db_english
from db_english import DBUser, DBLesson, DBSlide, DBVariant, DBGame, DBSeller, DBKey, DBActiveKey, DBPromo, time_int, get_dict_words, int_to_time_to_str

import moviepy.editor as mp #Нужен для pydub
import vosk

#import subprocess
from pydub import AudioSegment
import json
import soundfile as sf
import difflib #Для сравнение на подобие текстовых строк
import importlib

pathlib: ModuleType
argostranslate_package: ModuleType
argostranslate_translate: ModuleType
from_code = 'en'
to_code = 'ru'

f_load_argostranslate: bool = False
def load_argostranslate():
    global pathlib
    global argostranslate_package
    global argostranslate_translate
    global f_load_argostranslate

    print("Loading model Argostranslate...")
    pathlib = importlib.import_module("pathlib")
    argostranslate_package = importlib.import_module("argostranslate.package")
    argostranslate_translate = importlib.import_module("argostranslate.translate")

    package_path = pathlib.Path("translate-en_ru-1_9.argosmodel")
    argostranslate_package.install_from_path(package_path)

    print("Loading Argostranslate - Ok")

    f_load_argostranslate = True

if f_load_argostranslate: load_argostranslate()

f_load_pyttsx3 = True
try:
    import pyttsx3
    engine = pyttsx3.init()
    print("Load engine pyttsx3 - OK")
    #f_load_pyttsx3 = False
except:
    f_load_pyttsx3 = False
    print("Load engine pyttsx3 - ERROR")

# Модели Vosk
model_en = None
model_ru = None

class MyBot(telebot.TeleBot):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def delete_msg(self, chat_id: int, msg_id: int):
        if msg_id != 0:
            try:
                if not self.delete_message(chat_id, msg_id):
                    print(f"don't delete message id={msg_id}")
            except: pass

    def delete_msg_dialog(self, db_user: DBUser):
        if db_user.msg_dialog_id != 0:
            try: self.delete_message(db_user.chat_id, db_user.msg_dialog_id)
            except: pass
            db_user.save_user(msg_dialog_id = 0)

    def delete_reply_msg(self, db_user: DBUser):
        if db_user.msg_reply_id != 0:
            self.delete_msg(db_user.chat_id, db_user.msg_reply_id)
            db_user.save_user(msg_reply_id = 0)

    def similarity(self, str1: str, str2: str):
        normalized1 = str1.lower()
        normalized2 = str2.lower()
        matcher = difflib.SequenceMatcher(None, normalized1, normalized2)
        return matcher.ratio()

ADMIN_CHAT_ID = config_english.ADMIN_CHAT_ID
num_token = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in config_english.TOKENS else "1"
TOKEN = config_english.TOKENS[num_token]["TOKEN"]
PAYMENT_TOKEN = config_english.TOKENS[num_token]["PAYMENT_TOKEN"]
FILE_NAME_DB = config_english.TOKENS[num_token]["DB"]

bot = MyBot(token=TOKEN)
_SQL_ = db_english.SQLiteClient(FILE_NAME_DB, TOKEN, ADMIN_CHAT_ID, True)
_SQL_.close()
mutex = threading.Lock()

#Стандартные клавиатуры
keyb_y_n = InlineKeyboardMarkup()
keyb_y_n.add(
    InlineKeyboardButton(text="Да", callback_data='/command_yes'),
    InlineKeyboardButton(text="Нет", callback_data='/command_no')
    )
keyb_cancel = InlineKeyboardMarkup()
keyb_cancel.add(InlineKeyboardButton(text="Отмена", callback_data='/command_cancel'))
keyb_ok = InlineKeyboardMarkup()
keyb_ok.add(InlineKeyboardButton(text="OK", callback_data='/command_ok'))

#Транскрибация аудио файла
def transcription(file_name_audio: str, l: str) -> str:
    global model_en
    global model_ru

    if l == "ru" and model_ru is None: model_ru = vosk.Model("vosk-model-small-ru-0.22")

    if l == "en" and model_en is None: model_en = vosk.Model("vosk-model-small-en-us-0.15")
    #if l == "en" and model_en is None: model_en = vosk.Model("vosk-model-en-us-0.22-lgraph")

    audio = AudioSegment.from_wav(file_name_audio)
    audio=audio.set_channels(1)

    # Преобразуем вывод в json
    rec = vosk.KaldiRecognizer(model_ru if l=="ru" else model_en, audio.frame_rate)
    rec.AcceptWaveform(audio.raw_data)
    result = rec.Result()
    text = json.loads(result)["text"]

    return text

def get_adm_level_user_message(chat_id: int)->int:
    return 0
    if ADMIN_CHAT_ID == chat_id:
        return 3
    return 0

def create_variants_from_text(db_user: DBUser, db_slide:DBSlide, text: str, type: str = "_button") -> bool:
    SQL = db_user.db_connect
    if db_slide.id_lesson != db_user.current_lesson_id: return False

    list_variants = db_slide.get_list_variants()
    db_variant: DBVariant
    for db_variant in list_variants:
        db_variant.delete()

    text = text.strip()
    if text == "": return True

    a_text = text.split(';')
    row_width = len(a_text)

    db_slide.save(Rules=f"_row_width {row_width}")

    db_slide_next: DBSlide = DBSlide(SQL)
    id_next_slide: int = db_slide_next.ROWID if db_slide_next.get_from_num(db_slide.num + 1, db_slide.id_lesson) else 0

    a_variants = []
    for i in range(0, row_width):
        f_variant: str = "_true_answer" if i == 0 else "_false_answer"
        name:str = a_text[i].strip()

        if type == "_voice_button" and (SQL.get_word_id(name, "EN") is None or name.find("^") < 0):
            #name2 = name
            # gender = ""
            # if name[:2] == "M:" : gender = "M"
            # elif name[:2] == "F:" : gender = "F"
            # if gender != "" : name2 = name[2:].strip()
            # else : gender = "F"
            # translate = argostranslate(db_user, name2, from_code, to_code)
            # voice_en = get_voice_text(name2, "EN", gender)
            # voice_ru = get_voice_text(translate, "RU", gender)
            # SQL.save_word_to_dict(name2, "EN", voice_en, translate, "RU", voice_ru, gender)
            SaveWordToDictionary(db_user, name, f_cleary=False, f_skip=True)

        a_variants.append({"Name": name, "Caption": f"{type}\n{f_variant}",
                           "next_slide_id": id_next_slide if i == 0 else 0})

    random.shuffle(a_variants)
    for variant in a_variants:
        db_variant: DBVariant = DBVariant(db_user.db_connect, 0, db_slide.ROWID)
        db_variant.save(Name=variant["Name"], Caption=variant["Caption"], id_next_slide=variant["next_slide_id"])

    return True

@bot.message_handler(commands=["subtitles"], chat_types=["private"])
def subtitles(message: Message):
    SQL = db_english.SQLiteClient(FILE_NAME_DB, token=TOKEN, admin_chat_id=ADMIN_CHAT_ID)
    db_user = GetUser(SQL, message.chat.id, message.from_user.first_name, message.from_user.username)

    if db_user is None:
        bot.delete_msg(message.chat.id, message.message_id)
        return

    keyboard = InlineKeyboardMarkup(row_width=6)

    #keyboard.add(InlineKeyboardButton(text="По умолчанию", callback_data="/set_subtitles_0"))
    keyboard.add(InlineKeyboardButton(text=" 🔤 Текстом", callback_data="/set_subtitles_1"))
    keyboard.add(InlineKeyboardButton(text="🔊 Аудио", callback_data="/set_subtitles_2"))
    keyboard.add(InlineKeyboardButton(text="🔤 Текстом и Аудио 🔊", callback_data="/set_subtitles_3"))
    keyboard.add(InlineKeyboardButton(text="Отмена", callback_data="/command_cancel"))

    send_reaply_message(db_user, "<b>Выберите режим перевода титров</b>", 1, keyboard)

    bot.delete_msg(db_user.chat_id, message.message_id)

@bot.message_handler(commands=["adm_1508"], chat_types=["private"])
def adm_1508(message: Message):

    SQL = db_english.SQLiteClient(FILE_NAME_DB, token=TOKEN, admin_chat_id=ADMIN_CHAT_ID)
    db_user = GetUser(SQL, message.chat.id, message.from_user.first_name, message.from_user.username)

    if db_user is not None and db_user.adm_level == 3:
        id_msg_adm_panel = SQL.get_admin_panel()
        if id_msg_adm_panel != 0:
            bot.delete_msg(db_user.chat_id, id_msg_adm_panel)

        send_reaply_message(db_user, "Введие пароль", 101)

    bot.delete_msg(db_user.chat_id, message.message_id)

@bot.message_handler(commands=["invite"], chat_types=["private"])
def invite(message: Message):

    SQL = db_english.SQLiteClient(FILE_NAME_DB, token=TOKEN, admin_chat_id=ADMIN_CHAT_ID)
    db_user = GetUser(SQL, message.chat.id, message.from_user.first_name, message.from_user.username)

    S_Nubber = SQL.create_invites(db_user.chat_id)
    text = f"""
💎 <a href='https://t.me/english_quest_ru_bot'>Telegram BOT</a> <b>- осваиваиваем Английский язык как дети</b>

🔸 <b>Сomprehensible Input English - "Понятный вход"</b> - методика, разработанная американскими учеными в 80-х годах 20-го века для быстрого и эффективного обучения мигрантов иностранному языку

    🔹 <b>интуитивная лексика</b>
    🔹 <b>интуитивная грамматика</b>
    🔹 <b>экшен аудирование</b>
    🔹 <b>имплицитное обучение</b>
    🔹 <b>интерактивные видео в игровой форме</b>

🔸 <code>{S_Nubber}</code> - Активируете код и получите 100💎 бонусов (перейдите в <a href='https://t.me/english_quest_ru_bot'>ТелеБота</a>, введите код в поле сообщений)
🔹 https://t.me/english_quest_ru_bot
"""

    msg_id_1 = bot.send_message(message.chat.id, text=text, parse_mode="html").message_id
    msg_id_2 = bot.send_message(message.chat.id, text="☝️ Отправьте пригласительную ссылку друзьям.\nЗа каждую активацию Вашего приглашения на Ваш счет поступит 100💎 бонусов!").message_id
    DeleteOldMessages(db_user)
    db_user.save_message(msg_id_1)
    db_user.save_message(msg_id_2)
    bot.delete_msg(db_user.chat_id, message.message_id)

# @bot.message_handler(commands=["bonuses"], chat_types=["private"])
# def bonuses(message: Message):
#     SQL = db_english.SQLiteClient(FILE_NAME_DB, token=TOKEN, admin_chat_id=ADMIN_CHAT_ID)
#     db_user = GetUser(SQL, message.chat.id, message.from_user.first_name, message.from_user.username)
#
#     #keyboard
#     msg = f"На Вашем счету {db_user.bonuses}💎 бонусов.\nБонусы можно будет обменять на подписку."
#     msg_id=bot.send_message(message.chat.id, text=msg).message_id
#     bot.delete_msg(db_user.chat_id, message.message_id)
#     DeleteOldMessages(db_user)
#     db_user.save_message(msg_id)

def display_subscription(db_user: DBUser):
    msg = f"📄 Подписка не оформлена" \
        if db_user.license_date == 0 else \
        f"📄 Подписка до: {int_to_time_to_str(db_user.license_date, 3)} (по Москве)\n"
    time_cur = time_int()
    if db_user.license_date != 0:
        if db_user.license_date < time_cur:
            msg += "❗️ <i>подписка окончена</i>"
        else:
            k = 3600 * 24
            msg += f"<i>осталось: <b>{int((db_user.license_date - time_cur) / k)}</b> дн.</i>"

    msg += f"\n\n🗄 Бонусы: {db_user.bonuses}💎\n"

    msg += "\n📝 Оформить подписку можно:\n" \
           " 🔸 через ТелеБота - кнопки 'Подписка ...'\n" \
           " 🔸 через Маркетплейсы"

    keyboard = InlineKeyboardMarkup()
    # keyboard.add(InlineKeyboardButton(text="Подписка на день 99 руб.", callback_data=f"/bay {99}"))
    # keyboard.add(InlineKeyboardButton(text="Подписка на неделю 399 руб.", callback_data=f"/bay {399}"))
    keyboard.add(InlineKeyboardButton(text="Подписка на месяц 990 руб.", callback_data=f"/bay {999}"))
    keyboard.add(InlineKeyboardButton(text="💎 Бонусы на подписку", callback_data=f"/subscription_{0}"))
    keyboard.add(InlineKeyboardButton(text="Закрыть", callback_data=f"/command_cancel"))

    msg_id = bot.send_message(db_user.chat_id, text=msg, parse_mode="html", reply_markup=keyboard).message_id

    DeleteOldMessages(db_user)
    db_user.save_message(msg_id)

@bot.pre_checkout_query_handler(func=lambda query: True)
def checkout(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True, error_message="Ошибка оплаты. Попробуйте произвести оплату позже.")

@bot.message_handler(content_types=['successful_payment'])
def got_payment(message):
    SQL = db_english.SQLiteClient(FILE_NAME_DB, token=TOKEN, admin_chat_id=ADMIN_CHAT_ID)
    db_user = GetUser(SQL, message.chat.id, message.from_user.first_name, message.from_user.username)

    SQL.set_subscription_telegram(db_user.ROWID, message.successful_payment.total_amount/100, message.successful_payment.invoice_payload)
    
    if db_user.license_date < time_int():
        db_user.license_date = time_int() + 3600 * 24 * 31
    else:
        db_user.license_date += 3600 * 24 * 31
    db_user.save_user()

    display_subscription(db_user)

@bot.message_handler(commands=["subscription"], chat_types=["private"])
def subscription(message: Message):
    SQL = db_english.SQLiteClient(FILE_NAME_DB, token=TOKEN, admin_chat_id=ADMIN_CHAT_ID)
    db_user = GetUser(SQL, message.chat.id, message.from_user.first_name, message.from_user.username)

    display_subscription(db_user)
    bot.delete_msg(db_user.chat_id, message.message_id)

@bot.message_handler(commands=["about"], chat_types=["private"])
def about(message: Message):
    SQL = db_english.SQLiteClient(FILE_NAME_DB, token=TOKEN, admin_chat_id=ADMIN_CHAT_ID)
    db_user = GetUser(SQL, message.chat.id, message.from_user.first_name, message.from_user.username)

    filename: str = "about.txt"
    if os.path.exists(filename):
        with open(filename, "rt", encoding="utf-8") as file:
            msg = file.read()
            msg_id = bot.send_message(db_user.chat_id, text=msg, parse_mode="html", reply_markup=keyb_ok,
                                      link_preview_options=telebot.types.LinkPreviewOptions(is_disabled=True)).message_id
            db_user.save_message(msg_id)
    bot.delete_msg(db_user.chat_id, message.message_id)

@bot.message_handler(commands=["metod"], chat_types=["private"])
def metod(message: Message):
    SQL = db_english.SQLiteClient(FILE_NAME_DB, token=TOKEN, admin_chat_id=ADMIN_CHAT_ID)
    db_user = GetUser(SQL, message.chat.id, message.from_user.first_name, message.from_user.username)

    filename: str = "metod.txt"
    if os.path.exists(filename):
        with open(filename, "rt", encoding="utf-8") as file:
            msg = file.read()
            msg_id = bot.send_message(db_user.chat_id, text=msg, parse_mode="html", reply_markup=keyb_ok,
                                      link_preview_options=telebot.types.LinkPreviewOptions(is_disabled=True)).message_id
            db_user.save_message(msg_id)
    bot.delete_msg(db_user.chat_id, message.message_id)
@bot.message_handler(commands=["start"], chat_types=["private"])
def start(message: Message):

    SQL = db_english.SQLiteClient(FILE_NAME_DB, token=TOKEN, admin_chat_id=ADMIN_CHAT_ID)
    db_user = GetUser(SQL, message.chat.id, message.from_user.first_name, message.from_user.username)

    if db_user is not None:

        if db_user.mode == 5: # Идёт тестовая работа
            send_reaply_message(db_user, "⁉️<b>Прервать Тестовую работу⁉️</b>", 6, keyb_y_n)
        else:
            List_Lessons_Root(db_user, 0, 0)

    bot.delete_msg(db_user.chat_id, message.message_id)

def List_Lessons_Root(db_user: DBUser, mode=None, current_lesson_id=None, current_video_id=None, current_variant_id=None):
    msg_dialog_id = db_user.msg_dialog_id

    if current_lesson_id is None:
        current_lesson_id = db_user.current_lesson_id if db_user.current_lesson_id != 0 and \
                        DBLesson(db_user.db_connect, db_user.current_lesson_id).ROWID !=0 else 0

    #Ставим по умолчанию корень на Детей
    # if current_lesson_id == 0 and db_user.adm_level != 3:
    #     current_lesson_id = 10

    if current_video_id is None:
        current_video_id = db_user.current_video_id if current_lesson_id != 0 and db_user.current_video_id != 0 and \
                        DBSlide(db_user.db_connect, db_user.current_video_id).ROWID != 0 else 0

    db_user.save_user(mode=0 if mode is None else mode,
                      current_lesson_id=current_lesson_id,
                      current_video_id=current_video_id,
                      current_variant_id = 0 if current_variant_id is None else current_variant_id,
                      msg_dialog_id=0, last_video_id=0)

    refresh_dialog(db_user)

    if msg_dialog_id != 0:
        bot.delete_msg(db_user.chat_id, msg_dialog_id)
    # else:
    #     print("msg_dialog_id == 0")
    # if db_user.chat_id != ADMIN_CHAT_ID:
    #     db_user.send_admin_message("- Start", True)

@bot.message_handler(content_types=['video'], chat_types=["private"])
def video(message):
    SQL = db_english.SQLiteClient(FILE_NAME_DB, token=TOKEN, admin_chat_id=ADMIN_CHAT_ID)
    db_user = GetUser(SQL, message.chat.id, message.from_user.first_name, message.from_user.username)
    if db_user is None: return

    command = db_user.mode
    if db_user.adm_level != 3 or not (command != 34 or command != 35):
        db_user.save_message(message.id)
        return

    if db_user.msg_reply_id != 0:
        try: bot.edit_message_text(chat_id=db_user.chat_id, message_id=db_user.msg_reply_id,
                                   text="\U00002699 <b>Loading video...</b>", parse_mode="html")
        except: db_user.save_user(msg_reply_id=0)

    file_info = bot.get_file(message.video.file_id)
    file_name_video = file_info.file_path  # message.video.file_name

    if command == 34 or command == 35: # 34-new 35-change
        db_lesson: DBLesson = DBLesson(SQL, db_user.current_lesson_id)
        if db_lesson.type != 2: db_lesson.save(type = 2)
        db_lesson.normalize_num_slides()
        db_slide: DBSlide = DBSlide(SQL, 0 if command == 34 else db_user.current_video_id, db_lesson.ROWID)
        db_slide.save_video(bot.download_file(file_name_video), file_info.file_size)
        if db_user.mode == 34: #Формирование пустого словоря ListWord
            dict_list_words: dict = get_dict_words(db_slide.List_Words, db_slide.ROWID)
            db_slide.save(keyboard_dict=json.dumps(dict_list_words))
        db_user.save_user(mode=30 if command == 35 else 20, current_lesson_id=db_slide.id_lesson,
                          current_video_id=db_slide.ROWID if command == 35 else 0, current_variant_id=0)

        if message.caption is not None: #В капче сообщения к видео - список кнопок через запятую
            caption: str = message.caption.strip()
            List_Words = caption
            if caption.find(";") < 0:
                f_skip_list_word = False
                if caption[-1:] == "#" or caption == "Проигрыш" or caption == "Выигрыш":
                    if caption[-1:] == "#":
                        caption = caption[:-1]
                    f_skip_list_word = True
                    List_Words = ""

                if not f_skip_list_word:
                    if caption.find("\n") > 0:
                        a_caption = caption.split("\n")
                        caption = ""
                        for s in a_caption:
                            SaveWordToDictionary(db_user, s, f_cleary=False, f_skip=True)
                            caption += f"{s} "
                    else:
                        SaveWordToDictionary(db_user, caption, f_cleary=False, f_skip=True)

                db_slide.save(Name=caption, List_Words=List_Words,
                              keyboard_dict=json.dumps(get_dict_words(List_Words, db_slide.ROWID)))
                db_variant: DBVariant = DBVariant(SQL, 0, db_slide.ROWID)
                db_variant.save(Name="Следующий слайд ⤵️", Caption="_button")
            else:
                if caption[-1:] == "#":
                    caption = caption[:-1]
                    db_slide.save(is_test=1)

                type_button = "_button"
                if caption[-1:] == "@":
                    caption = caption[:-1]
                    type_button = "_voice_button"

                create_variants_from_text(db_user, db_slide, caption, type_button)
                db_slide_prev: DBSlide = DBSlide(SQL)
                if db_slide_prev.get_from_num(db_slide.num-1, db_slide.id_lesson): #Связываем предыдущую true кнопку с этим слайдом
                    list_variants = db_slide_prev.get_list_variants()
                    db_variant: DBVariant
                    for db_variant in list_variants:
                        if db_variant.db_rules.command("_true_answer"):
                            db_variant.save(id_next_slide=db_slide.ROWID)

        bot.delete_msg(db_user.chat_id, message.id)
        refresh_dialog(db_user)
        
        if command == 35:
            bot.delete_msg(db_user.chat_id, db_user.msg_reply_id)
        else:
            send_reaply_message(db_user, "Load Video of Slide", 34)
    else:
        db_user.save_message(message.message_id)
    return
    # if db_user.reply_msg_id !=0:
    #     bot.edit_message_text(chat_id=db_user.chat_id, message_id=db_user.reply_msg_id, text="Загрузка данных ждите...")

    # file_info = bot.get_file(message.video.file_id)
    # file_name_video = file_info.file_path  # message.video.file_name
    #
    # with open(file_name_video, "wb") as f:
    #     file_content = bot.download_file(file_name_video)
    #     f.write(file_content)
    #     f.close()
    #
    # clip = mp.VideoFileClip(fr"{file_name_video}")
    # file_name_audio=fr"{file_name_video[:-3]}wav"
    # bot.edit_message_text(chat_id=db_user.chat_id, message_id=msg_id, text="Extract audio...")
    # clip.audio.write_audiofile(file_name_audio)
    #
    #
    # bot.edit_message_text(chat_id=db_user.chat_id, message_id=msg_id, text="Recognizer text...")
    # text = transcription(file_name_audio, "en")
    # bot.edit_message_text(chat_id=db_user.chat_id, message_id=msg_id, parse_mode="html",
    #                       text=f"<code>{text}</code>" if text!="" else "Текст не распознан")
    # clip.close()
    # os.remove(file_name_video)
    #.remove(file_name_audio)

@bot.message_handler(content_types=['voice'], chat_types=["private"])
def voice(message: telebot.types.Message):
    SQL = db_english.SQLiteClient(FILE_NAME_DB, token=TOKEN, admin_chat_id=ADMIN_CHAT_ID)
    db_user = GetUser(SQL, message.chat.id, message.from_user.first_name, message.from_user.username)
    if db_user is None: return

    db_user.save_message(message.message_id, "voice", 0)
    #msg_id = bot.send_message(message.chat.id, text="Load voice...").message_id

    file_info = bot.get_file(message.voice.file_id)

    file_name = fr"voice/{db_user.chat_id}-{file_info.file_path[6:]}"  # Audio file *.oga voice/
    file_content = bot.download_file(file_info.file_path)

    if db_user.adm_level == 3 and db_user.mode == 12 and db_user.keyboard != "":  # Изменение озвучки выражения
        a_params = db_user.keyboard.split('_')
        try:
            id_word = a_params[0]
            lang = a_params[1]
            gender = a_params[2]
            caption = a_params[3]
            SQL.set_voice_id(id_word, file_content, lang, gender)
            DeleteOldMessages(db_user, True, 3)
            bot.delete_reply_msg(db_user)

            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton(text="ReSound", callback_data=f"/set_voice_{id_word}_{lang}_{gender}"))
            msg_voice_id = db_user.current_variant_id  # Здесь храним id voice-сообщения
            media = telebot.types.InputMediaAudio(media=file_content, caption=caption)
            bot.edit_message_media(chat_id=db_user.chat_id, message_id=msg_voice_id, media=media, reply_markup=keyboard)
            return
        except:
            pass

    with open(file_name, "wb") as f: #Write audio file *.oga
        f.write(file_content)
        f.close()

    #Converting *.oga to *.wav
    data, samplerate = sf.read(file_name)
    os.remove(file_name)
    file_name=file_name[:-3]+'wav'
    sf.write(file_name, data, samplerate)

    text = transcription(file_name, "en")
    if text == "yeah": text = "yes"
    msg_id = bot.send_message(db_user.chat_id, text=f"<code>{text if text != '' else 'None translate'}</code>",
                              parse_mode="html", reply_to_message_id=message.message_id).message_id
    db_user.save_message(msg_id)

    if text != "" and db_user.last_video_id != 0:

        id_next_slide = -2  # 0 - нет голосовых ответа по слайду,
        # > 0 - есть голосовой ответ и он совпадает с ответом пользователя
        # -1 - есть голосовой ответ, но он не совпадает с ответом пользователя

        db_slide = DBSlide(SQL, db_user.last_video_id)
        list_variannts = db_slide.get_list_variants()
        db_variant: DBVariant
        for db_variant in list_variannts:
            if db_variant.Caption == "_voice":
                id_next_slide = db_variant.id_next_slide if db_variant.Name == text else -1
                if db_variant.Name == text:
                    break

        if id_next_slide >= 0: #Правильный ответ
            sleep(1)
            if db_user.mode == 5:  # Контрольная Прохождение (db_user.last_word - кодовая строка Контрльной работы)
                f_variant = False if db_variant.id_next_slide == 0 or \
                                     db_variant.id_next_slide == db_variant.ROWID or \
                                     db_variant.db_rules.command("_false_answer") else True
                Testing(db_user, db_variant, "continue", f_variant)

            elif id_next_slide != 0:
                db_user.save_user(mode=0, last_video_id=id_next_slide)
                PlaySlide(db_user)

    os.remove(file_name)

@bot.message_handler(content_types=['audio'], chat_types=["private"])
def audio(message: telebot.types.Message):
    SQL = db_english.SQLiteClient(FILE_NAME_DB, token=TOKEN, admin_chat_id=ADMIN_CHAT_ID)
    db_user = GetUser(SQL, message.chat.id, message.from_user.first_name, message.from_user.username)
    if db_user is None: return

    db_user.save_message(message.message_id, "audio", 0)
    #msg_id = bot.send_message(message.chat.id, text="Load voice...").message_id

    file_info = bot.get_file(message.audio.file_id)

    #file_name = fr"voice/{db_user.chat_id}-{file_info.file_path[6:]}"  # Audio file *.oga voice/
    file_content = bot.download_file(file_info.file_path)

    if db_user.adm_level == 3 and db_user.mode == 12 and db_user.keyboard != "":  # Изменение озвучки выражения
        a_params = db_user.keyboard.split('_')
        try:
            id_word = a_params[0]
            lang = a_params[1]
            gender = a_params[2]
            caption = a_params[3]
            keyboard=InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton(text="ReSound",callback_data=f"/set_voice_{id_word}_{lang}_{gender}_{caption}"))
            SQL.set_voice_id(id_word, file_content, lang, gender)
            DeleteOldMessages(db_user, True, 3)
            bot.delete_reply_msg(db_user)
            msg_voice_id = db_user.current_variant_id #Здесь храним id voice-сообщения
            media = telebot.types.InputMediaAudio(media = file_content, caption=caption)
            bot.edit_message_media(chat_id=db_user.chat_id, message_id=msg_voice_id, media=media, reply_markup=keyboard)
        except:
            pass

def create_dict_from_voice(db_user: DBUser, list_tuple: list, type: int) -> bool:
    SQL = db_user.db_connect
    msg_id = bot.send_message(text="<b>Экспорт данных для словоря...</b>",
                              chat_id=db_user.chat_id, parse_mode="html").message_id
    db_user.save_message(msg_id)

    file_name = "export_dict_from.sqlite"

    if os.path.exists(file_name):
        os.remove(file_name)

    conn = sqlite3.connect(file_name, check_same_thread=False)
    conn.execute("CREATE TABLE Dictionary(ID INT, EN TXT, EN_VOICE_M INT, EN_VOICE_F INT,"
                 "RU TXT, RU_VOICE_M INT, RU_VOICE_F INT);")
    if conn is None:
        bot.edit_message_text(text="<b>Не могу создать таблицу для экспорта данных.</b>",
                        chat_id=db_user.chat_id, message_id=msg_id, parse_mode="html")
        return False

    for row in list_tuple:
        ROWID = row[0]
        text_en = SQL.get_word_from_row(ROWID, "EN")
        text_ru = SQL.get_word_from_row(ROWID, "RU")
        s1=SQL.is_voice_row(ROWID, "EN", "M") if type == 1 else 0
        s2=SQL.is_voice_row(ROWID, "EN", "F") if type == 1 else 0
        s3=SQL.is_voice_row(ROWID, "RU", "M") if type == 1 else 0
        s4=SQL.is_voice_row(ROWID, "RU", "F") if type == 1 else 0
        conn.execute("""INSERT INTO Dictionary(ID, EN , EN_VOICE_M, EN_VOICE_F,
                     RU, RU_VOICE_M, RU_VOICE_F) VALUES(?, ?, ?, ?, ?, ?, ?);""",
                     (ROWID, text_en, s1, s2, text_ru, s3, s4))
        conn.commit()
    conn.close()

    bot.edit_message_text(text=f"<b>Данные экспортированны успешно.\nКоличество записей: {len(list_tuple)}</b>",
                          chat_id=db_user.chat_id, message_id=msg_id, parse_mode="html")
    f = open(file_name, "rb")
    msg_id = bot.send_document(db_user.chat_id, f).message_id
    db_user.save_message(msg_id)
    return True

def delete_all_files(folder: str):
    for filename in os.listdir(folder):
        file_path = os.path.join(folder, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print('Failed to delete %s. Reason: %s' % (file_path, e))

@bot.message_handler(content_types=['document'], chat_types=["private"])
def get_document(message: telebot.types.Message):
    pass
    # SQL = db_english.SQLiteClient(FILE_NAME_DB, token=TOKEN, admin_chat_id=ADMIN_CHAT_ID)
    # db_user = GetUser(message, SQL)
    # if db_user is None: return
    #
    # db_user.save_message(message.message_id, message.text, 1)
    #
    # if db_user.adm_level != 3:
    #     return
    #
    # file_name = message.document.file_name
    # file_info = bot.get_file(message.document.file_id)
    #
    # if message.document.file_name == "export_dict_from.sqlite" and f_load_pyttsx3 == False:
    #     bot.send_message(message.chat.id, text="pyttsx3 not load")
    #     bot.delete_msg(db_user.chat_id, message.message_id)
    #     return
    #
    # if message.document.file_name == "export_dict_from.sqlite":
    #     msg_id = bot.send_message(text="<b>Импорт данных для словоря...</b>",
    #                               chat_id=db_user.chat_id, parse_mode="html").message_id
    #     db_user.save_message(msg_id)
    #
    #     with open(file_name, "wb") as f:
    #         file_content = bot.download_file(file_info.file_path)
    #         f.write(file_content)
    #         f.close()
    #     conn = sqlite3.connect(file_name, check_same_thread=False)
    #     cursor = conn.cursor()
    #     cursor.execute("SELECT * FROM Dictionary;")
    #     list_tuple = cursor.fetchall()
    #
    #     dir_name = "voice_ru"
    #     if not os.path.isdir(dir_name):
    #         os.mkdir(dir_name)
    #     delete_all_files(dir_name)
    #
    #     for row in list_tuple:
    #         # conn.execute("CREATE TABLE Dictionary(ID INT, EN TXT, EN_VOICE_M INT, EN_VOICE_F INT,"
    #         #              "RU TXT, RU_VOICE_M INT, RU_VOICE_F INT);")
    #
    #         rowid: int = int(row[0])
    #         text_en: str = str(row[1])
    #         is_voice_en_m: int= int(row[2])
    #         is_voice_en_f: int = int(row[3])
    #         text_ru: str = str(row[4])
    #         is_voice_ru_m: int = int(row[5])
    #         is_voice_ru_f: int = int(row[6])
    #
    #         bot.edit_message_text(chat_id=db_user.chat_id, message_id=msg_id,
    #             text=f"\U00002699 <b>Импорт данных для словоря...</b>\n{text_en} - {text_ru}", parse_mode="html")
    #         if is_voice_en_m == 0:
    #             save_file_voice_text(f"{dir_name}/{rowid}_EN_M.wav", text_en, "EN", "M")
    #         if is_voice_en_f == 0:
    #             save_file_voice_text(f"{dir_name}/{rowid}_EN_F.wav", text_en, "EN", "F")
    #         if is_voice_ru_m == 0:
    #             save_file_voice_text(f"{dir_name}/{rowid}_RU_M.wav", text_ru, "RU", "M")
    #         if is_voice_ru_f == 0:
    #             save_file_voice_text(f"{dir_name}/{rowid}_RU_F.wav", text_ru, "RU", "F")
    #
    #     conn.close()
    #     bot.delete_msg(db_user.chat_id, message.message_id)
    #     bot.edit_message_text(text=f"<b>Данные импортированны успешно.\nОбработанно записей : {len(list_tuple)}</b>\n"
    #                                f"Файлы находятся в каталоге: {os.path.abspath(dir_name)}",
    #                           chat_id=db_user.chat_id, message_id=msg_id, parse_mode="html")
    #
    #
    # elif file_name[-4:] == ".wav":
    #     print(f"import {file_name}")
    #     try:
    #         a_file = message.document.file_name[:-4].split('_')
    #         ROWID = int(a_file[0])
    #         LANG = a_file[1]
    #         GENDER = a_file[2]
    #         voice = bot.download_file(file_info.file_path)
    #         SQL.save_word_to_dict(ROWID, LANG, GENDER, voice)
    #         bot.delete_msg(db_user.chat_id, message.message_id)
    #     except:
    #         print(f"Error save audio in Dictonary (file: {file_name})")
    #
    # bot.delete_msg(db_user.chat_id, message.message_id)

@bot.message_handler(content_types=['new_chat_members'], chat_types=['group', 'supergroup', 'channel']) #'sender',
def new_chat_members(message: Message):
    mutex.acquire()
    SQL = db_english.SQLiteClient(FILE_NAME_DB, token=TOKEN, admin_chat_id=ADMIN_CHAT_ID)

    #Удаление прошлых приветствий
    a_messages_group_id = SQL.get_messages_group(message.chat.id)
    SQL.delete_message_group(message.chat.id)
    for id_message in a_messages_group_id:
        bot.delete_msg(message.chat.id, id_message)

    text = f"""
💎 <b>Hello {message.from_user.first_name}!</b>

🔹 Это группа пользователей <a href='https://t.me/english_quest_ru_bot'>Telegram BOT</a> для обучения Английскому языку по методике <b>Сomprehensible Input English</b>

🔸 <b>"Понятный вход"</b> - методика, разработанная американскими учеными в 80-х годах 20-го века для быстрого и эффективного обучения мигрантов иностранному языку
    
    🔹 <a href='https://www.youtube.com/shorts/RA1vgM60E9g'>имплицитное обучение</a>
    🔹 <b>интуитивная лексика</b>
    🔹 <b>интуитивная грамматика</b>
    🔹 <b>экшен аудирование</b>
    🔹 <b>учим язык как дети</b>
    🔹 <b>интерактивные видео в игровой форме</b>

️❗ ТелеБот работает в демо-режиме (все уроки БЕСПЛАТНО)

🔸 <i>Переходим в <a href='https://t.me/english_quest_ru_bot'>ТелеБота,</a> нажимаем Меню->Start->Выбираем нужный раздел</i>
🔹 https://t.me/english_quest_ru_bot
    """
    msg_id = bot.send_message(message.chat.id, text=text, parse_mode="html").message_id
    SQL.save_message_group(message.chat.id, msg_id)
    bot.delete_msg(message.chat.id, message.message_id)

    mutex.release()

@bot.message_handler(content_types=['left_chat_member'], chat_types=['group', 'supergroup', 'channel']) #'sender',
def out_chat_members(message: Message):
    bot.delete_msg(message.chat.id, message.message_id)

def GetUser(SQL: db_english.SQLiteClient, chat_id: int, first_name: str, user_name: str) -> DBUser:
    db_user: DBUser = DBUser(SQL, chat_id, get_adm_level_user_message(chat_id), first_name, user_name)

    if db_user.ROWID == -1:
        bot.send_message(text="<b>🛠 В данный момент на сервере проводятся профилактические работы.</b>\n\n" \
                              "Повторите запрос позже.\nПриносим свои извинения.",
                         chat_id=chat_id, parse_mode="html")

    return db_user if db_user.chat_id != -1 else None

@bot.message_handler(chat_types=["private"])
def all_messages(message: Message):
    SQL = db_english.SQLiteClient(FILE_NAME_DB, token=TOKEN, admin_chat_id=ADMIN_CHAT_ID)
    db_user = GetUser(SQL, message.chat.id, message.from_user.first_name, message.from_user.username)
    if db_user is None: return

    db_user.save_message(message.message_id, message.text, 1)
    f_edit = False

    if message.text.find("BC584D0A9D") > 0:  # Активация приглашения
        # return -1 - нет такого S_Number, 0 - пользователь уже пользоавлся приграшением, 1 - есть S_Number и есть возможность приглашения
        result = SQL.test_invite(id_user=db_user.ROWID, chat_id=db_user.chat_id, S_Number=message.text)
        if result == -2:
            msg = "❌ Код повреждён или не действителен!"
        elif result == -1:
            msg = "⁉️ Себя приглашать всегда пожалуйста 😊!"
        elif result == 0:
            msg = "‼️ У Вас уже есть активированное приглашение!"
        else:
            msg = f"😊 Приглашение активированно!\nВам на счет положено {result}💎 бонусов!"
        msg_id = bot.send_message(db_user.chat_id, msg).message_id
        DeleteOldMessages(db_user)
        db_user.save_message(msg_id)


    elif message.text.find("6DC2A7B34E") > 0: #Активация подписки
        db_key: DBKey = DBKey(SQL, S_Nunber=message.text)
        if db_key.ID > 0:
            db_promo: DBPromo = DBPromo(SQL, db_key.id_promo)
            db_seller: DBSeller = DBSeller(SQL, db_promo.id_seller)
            list_active = db_key.get_list_activate()
            msg = f"😎 <b>Данные ключа</b>\n" \
                  f"Ключ: {db_key.S_Number}\n" \
                  f"Продавец: {db_seller.Name}\n" \
                  f"Тип лицензии: {'однопользовательская' if db_promo.count_lic == 1 else 'многопользовательская'}\n" \
                  f"Период подписки: {db_promo.license_period}д.\n" \
                  f"Активировано: {len(list_active)} из {db_promo.count_lic}"

            keboard = InlineKeyboardMarkup()
            if db_seller.block == 1:
                msg += "\n\n❌ Данный продавец заблокирован!\nОбратитесь в поддержку."
                keboard.add(InlineKeyboardButton(text="Закрыть", callback_data=f"/command_cancel"))
            elif db_promo.block == 1:
                msg += "\n\n❌ Данная подписка заблокирована!\nОбратитесь в поддержку."
                keboard.add(InlineKeyboardButton(text="Закрыть", callback_data=f"/command_cancel"))
            elif len(list_active)<db_promo.count_lic:
                keboard.add(InlineKeyboardButton(text="Активировать", callback_data=f"/activate_key_{db_key.ID}"))
                keboard.add(InlineKeyboardButton(text="Отменить", callback_data=f"/command_cancel"))
            else:
                msg += "\n\n❌ Подписка уже полностью активирована!"
                keboard.add(InlineKeyboardButton(text="Закрыть", callback_data=f"/command_cancel"))

            msg_id = bot.send_message(chat_id=db_user.chat_id, text=msg, reply_markup=keboard, parse_mode="html").message_id
            db_user.save_message(msg_id)
            bot.delete_msg(db_user.chat_id, message.message_id)
        else:
            msg_id = bot.send_message(chat_id=db_user.chat_id, text="❌ Ключ повреждён или не действителен!").message_id
            db_user.save_message(message.message_id)
            db_user.save_message(msg_id)

    elif db_user.adm_level == 3 and message.text.find("/get_dict_from_create_voice") == 0:
        type = 1
        list_tuple = SQL.sql_select("""SELECT ROWID FROM Dictionary WHERE (RU<>'' OR EN<>'') AND 
            (RU_VOICE_M is NULL OR RU_VOICE_F is NULL OR EN_VOICE_M is NULL OR EN_VOICE_F is NULL);""")

        if message.text[-1:] == "0":
            list_tuple = SQL.sql_select("""SELECT ROWID FROM Dictionary WHERE RU<>'' OR EN<>'';""")
            type = 0

        if len(list_tuple) > 0:
            create_dict_from_voice(db_user, list_tuple, type)
        else:
            msg_id = bot.send_message(text="<b>Данные для экспорта отсутствуют.\nВсе слова и фразы уже переведены.</b>",
                                      chat_id=db_user.chat_id, parse_mode="html").message_id
            db_user.save_message(msg_id)
            bot.delete_msg(db_user.chat_id, message.message_id)
        return

    elif message.text.find("/lvl") == 0 and db_user.current_lesson_id != 0:
        db_lesson: DBLesson = DBLesson(SQL, db_user.current_lesson_id)
        a_text = message.text.split(' ')
        level = int(a_text[1]) if len(a_text) > 1 and a_text[1].isdigit() else db_lesson.skill
        if db_lesson.ROWID != 0:
            db_parent_game: DBGame = get_parent_game(db_user, db_lesson)
            decrement_game_skill(db_user, db_parent_game, level)
            refresh_dialog(db_user)

    elif db_user.adm_level == 3 and db_user.mode >= 10:

        if db_user.mode == 121: # Name Saller
            if db_user.current_variant_id != 0:
                db_seller: DBSeller = DBSeller(SQL, db_user.current_variant_id)
                if db_seller.ID != 0 and message.text != db_seller.Name:
                    db_seller.save(Name=message.text)
                    db_user.save_user(mode=120)
                    f_edit = True

        elif db_user.mode == 122: # Caption Saller
            if db_user.current_variant_id != 0:
                db_seller: DBSeller = DBSeller(SQL, db_user.current_variant_id)
                if db_seller.ID != 0 and message.text != db_seller.Caption:
                    db_seller.save(Caption=message.text)
                    db_user.save_user(mode=120)
                    f_edit = True

        elif db_user.mode == 101: #Admin_Panel
            md = md5(message.text.encode('utf-8')).hexdigest().upper()
            if md == SQL.get_admin_pass_md5():
                db_user.save_user(mode=100)
                SQL.set_admin_panel(1)
                refresh_dialog(db_user)
                SQL.set_admin_panel(db_user.msg_dialog_id)

        elif db_user.mode == 103 and SQL.get_admin_panel()>0: #Создание ключей - ввод обоснования
            db_user.save_user(keyboard=message.text)
            db_seller:DBSeller = DBSeller(SQL, db_user.current_video_id)
            send_reaply_message(db_user, f"🛠 <b>Создание ключей</b>\nПродавец: {db_seller.Name}\n" \
                                         f"Примечание: {message.text}\n\nВведие количество ключей", 104)
            bot.delete_msg(db_user.chat_id, message.message_id)

        elif db_user.mode == 104 and SQL.get_admin_panel()>0 and message.text.isdigit(): #Создание ключей - вваод количества ключей
            count_key = int(message.text)
            db_user.save_user(skill=count_key)
            db_seller: DBSeller = DBSeller(SQL, db_user.current_video_id)
            send_reaply_message(db_user,
                                f"🛠 <b>Создание ключей</b>\nПродавец: {db_seller.Name}\n" \
                                f"Примечание: {db_user.keyboard}\nКоличество ключей: {count_key}\n\n" \
                                f"Введие количество лицензий/подписок на один ключ",105)
            bot.delete_msg(db_user.chat_id, message.message_id)

        elif db_user.mode == 105 and SQL.get_admin_panel()>0 and message.text.isdigit(): #Создание ключей - вваод количества лицензий на олджин ключ
            count_lic = int(message.text)
            db_user.save_user(current_variant_id=count_lic)
            db_seller: DBSeller = DBSeller(SQL, db_user.current_video_id)
            send_reaply_message(db_user,
                                f"🛠 <b>Создание ключей</b>\n" \
                                f"Продавец: {db_seller.Name}\n" \
                                f"Примечание: {db_user.keyboard}\n"\
                                f"Количество ключей: {db_user.skill}\n" \
                                f"Подписок на ключ: {count_lic}\n\n" \
                                f"Введие длительность подписки в днях",
                                106)
            bot.delete_msg(db_user.chat_id, message.message_id)

        elif db_user.mode == 106 and SQL.get_admin_panel()>0 and message.text.isdigit(): #Создание ключей - вваод количества лицензий на олджин ключ
            period = int(message.text)
            db_seller: DBSeller = DBSeller(SQL, db_user.current_video_id)
            id_promo: int = SQL.create_promocodes(id_seller=db_user.current_video_id,Caption=db_user.keyboard,
                count_key=db_user.skill, count_lic=db_user.current_variant_id, period=period, id_user=db_user.ROWID)

            db_user.save_user(mode=140, current_variant_id=id_promo)
            bot.delete_msg(db_user.chat_id, message.message_id)
            f_edit = True

        elif db_user.mode == 11: #Изменение перевода RU слова
            a_params = db_user.keyboard.split('_')
            try:
                id_word = int(a_params[0])
                lang = a_params[1]
                gender = a_params[2]
                keyboard = InlineKeyboardMarkup()
                keyboard.add(
                    InlineKeyboardButton(text="Поменять перевод", callback_data=f"/set_word_{id_word}_{lang}_{gender}"))

                word = SQL.get_word_from_row(id_word, "EN")
                SaveWordToDictionary(db_user, word, f_cleary=False, f_skip=False, f_translate=False, f_word_translate=message.text)

                file_content = SQL.get_voice_id(id_word, lang, gender)

                #DeleteOldMessages(db_user, True, 3)
                bot.delete_reply_msg(db_user)
                msg_voice_id = db_user.current_variant_id  # Здесь храним id voice-сообщения
                translate_text = SQL.get_word_from_row(id_word, "RU")
                caption = f"{word}\n{translate_text}"
                media = telebot.types.InputMediaAudio(media=file_content, caption=caption)
                bot.edit_message_media(chat_id=db_user.chat_id, message_id=msg_voice_id, media=media,
                                       reply_markup=keyboard)
                bot.delete_msg(db_user.chat_id, message.message_id)
            except:
                pass

        elif db_user.mode == 21: # Name Lesson
            if db_user.current_lesson_id != 0:
                db_lesson: DBLesson = DBLesson(SQL, db_user.current_lesson_id)
                if message.text != db_lesson.Name:
                    db_lesson.save(Name=message.text)
                    db_user.save_user(mode=20)
                    f_edit = True

        elif db_user.mode == 22: # Caption Lesson
            if db_user.current_lesson_id != 0:
                db_lesson: DBLesson = DBLesson(SQL, db_user.current_lesson_id)
                if message.text != db_lesson.Caption:
                    db_lesson.save(Caption=message.text)
                    db_user.save_user(mode=20)
                    f_edit = True

        elif db_user.mode == 24:
            if message.text.isdigit() and db_user.current_lesson_id != 0:
                db_lesson: DBLesson = DBLesson(SQL, db_user.current_lesson_id)
                skill = int(message.text)
                if skill != db_lesson.skill:
                    db_lesson.save(skill=skill)
                    db_user.save_user(mode=20)
                    f_edit = True

        elif db_user.mode == 26:
            if message.text.isdigit() and db_user.current_lesson_id != 0:
                db_lesson: DBLesson = DBLesson(SQL, db_user.current_lesson_id)
                test_time = int(message.text)
                if test_time != db_lesson.test_time:
                    db_lesson.save(test_time=test_time)
                    db_user.save_user(mode=20)
                    f_edit = True

        elif db_user.mode == 27:
            if message.text.isdigit() and db_user.current_lesson_id != 0:
                db_lesson: DBLesson = DBLesson(SQL, db_user.current_lesson_id)
                test_num_errors = int(message.text)
                if test_num_errors != db_lesson.test_num_errors:
                    db_lesson.save(test_num_errors=test_num_errors)
                    db_user.save_user(mode=20)
                    f_edit = True

        elif db_user.mode == 28:
            if message.text.isdigit() and db_user.current_lesson_id != 0:
                db_lesson: DBLesson = DBLesson(SQL, db_user.current_lesson_id)
                num = int(message.text)
                if num != db_lesson.test_skill_decrement:
                    db_lesson.save(test_skill_decrement=num)
                    db_user.save_user(mode=20)
                    f_edit = True

        elif db_user.mode == 31: # Name Slide
            if db_user.current_video_id != 0:
                db_slide: DBSlide = DBSlide(SQL, db_user.current_video_id)
                if message.text != db_slide.Name:
                    db_slide.save(Name=message.text)
                    db_user.save_user(mode=30)
                    f_edit = True

        elif db_user.mode == 32: # Caption Slide
            if db_user.current_video_id != 0:
                db_slide: DBSlide = DBSlide(SQL, db_user.current_video_id)
                if message.text != db_slide.Caption:
                    db_slide.save(Caption=message.text)
                    db_user.save_user(mode=30)
                    f_edit = True

        elif db_user.mode == 33: # ListWords Slide
            if db_user.current_video_id != 0:
                db_slide: DBSlide = DBSlide(SQL, db_user.current_video_id)
                if db_slide.ROWID !=0 and message.text != db_slide.List_Words:
                    Set_Slide_New_ListWords(db_user, db_slide, message.text)

                db_user.save_user(mode=30)
                f_edit = True

        elif db_user.mode == 36: # Rules Slide
            if db_user.current_video_id != 0:
                db_slide: DBSlide = DBSlide(SQL, db_user.current_video_id)
                if message.text != db_slide.Rules:
                    # if db_slide.Rules == "_slide_if_end_lesson" or message.text == "_slide_if_end_lesson":
                    #     if message.text == "_slide_if_end_lesson" and db_slide.Rules != "_slide_if_end_lesson":
                    #         db_slide.increment_las_indexes_num()
                    #         db_slide.save(num=0)
                    #     else:
                    #         db_slide.save(num=db_slide.get_max_num() + 1)
                    db_slide.save(Rules=message.text)
                    db_user.save_user(mode=30)
                f_edit = True

        elif db_user.mode == 37:  # Message Slide
            if db_user.current_video_id != 0:
                db_slide: DBSlide = DBSlide(SQL, db_user.current_video_id)
                old_message = db_slide.Message
                if message.text != db_slide.Message:
                    db_slide.save(Message=message.text)
                    db_user.save_user(mode=30)
                    if not refresh_dialog(db_user):
                        db_slide.save(Message=old_message)
                        f_edit = True

        elif db_user.mode == 38:
            if db_user.current_video_id != 0:
                db_slide: DBSlide = DBSlide(SQL, db_user.current_video_id)
                if create_variants_from_text(db_user, db_slide, message.text):
                    db_user.save_user(mode=30)
                    f_edit = True

        elif db_user.mode == 39:
            if db_user.current_video_id != 0:
                db_slide: DBSlide = DBSlide(SQL, db_user.current_video_id)
                if create_variants_from_text(db_user, db_slide, message.text, "_voice_button"):
                    db_user.save_user(mode=30)
                    f_edit = True

        elif db_user.mode == 41: # Правка текста для перевода _voice_button
            if db_user.current_variant_id != 0:
                db_variant: DBVariant = DBVariant(SQL, db_user.current_variant_id)
                if message.text != db_variant.Name:
                    db_variant.save(Name=message.text)
                    if db_variant.db_rules.command("_voice_button"):
                        name = db_variant.Name
                        # gender = ""
                        # if name[:2] == "M:": gender = "M"
                        # elif name[:2] == "F:": gender = "F"
                        # if gender != "": name = name[2:].strip()
                        # else: gender = "F"
                        # translate = argostranslate(db_user, name, from_code, to_code)
                        # voice_en = get_voice_text(name, "EN", gender)
                        # voice_ru = get_voice_text(translate, "RU", gender)
                        # SQL.save_word_to_dict(name, "EN", voice_en, translate, "RU", voice_ru, gender)
                        SaveWordToDictionary(db_user, name, f_cleary=False, f_skip=True)
                    db_user.save_user(mode=40)
                    f_edit = True

        elif db_user.mode == 42:
            if db_user.current_variant_id != 0:
                db_variant: DBVariant = DBVariant(SQL, db_user.current_variant_id)
                if message.text != db_variant.Caption:
                    db_variant.save(Caption=message.text)
                    db_user.save_user(mode=40)
                    f_edit = True

    if f_edit == True: refresh_dialog(db_user)

def decrement_game_skill(db_user: DBUser, db_game: DBGame, skill: int):

    db_lesson: DBLesson = DBLesson(db_user.db_connect, db_game.id_lesson)
    list_lessons = db_lesson.get_list_lessons(id_chapter=db_game.id_lesson)

    for db_lesson_ in list_lessons:
        db_game_lesson:DBGame = DBGame(db_user.db_connect, db_user.ROWID, db_lesson_.ROWID)
        decrement_game_skill(db_user, db_game_lesson, skill if db_lesson_.skill < skill else 0)

    if db_lesson.skill >= skill:
        db_game.save(control_result=0, user_skill=0)
    else:
        db_game.save(control_result=2, user_skill=skill)

    if db_lesson.id_chapter == 0:
        db_game.save(control_result=0, user_skill=skill)

    db_game.check_result_all_lessons()

def save_file_voice_text(file_name: str, translation: str, LANG: str = "EN", GENDER: str = "F") -> bool:
    if f_load_pyttsx3 == False or translation == "":
        return  False

    voices = engine.getProperty("voices")
    default_voice = ""
    for voice in voices:
        if LANG == "RU" and GENDER == "F" and voice.id == r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices\TokenEnums\RHVoice\Victoria":
            default_voice = r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices\TokenEnums\RHVoice\Victoria"
            engine.setProperty('rate', 210)
            break
        elif LANG == "RU" and GENDER == "M" and voice.id == r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices\TokenEnums\RHVoice\Artemiy":
            default_voice = r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices\TokenEnums\RHVoice\Artemiy"
            engine.setProperty('rate', 150)
            break
        if LANG == "EN" and GENDER == "F" and voice.id == r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices\TokenEnums\RHVoice\Lyubov":
            default_voice = r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices\TokenEnums\RHVoice\Lyubov"
            engine.setProperty('rate', 190)
            break
        elif LANG == "EN" and GENDER == "M" and voice.id == r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices\TokenEnums\RHVoice\Evgeniy-Eng":
            default_voice = r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices\TokenEnums\RHVoice\Evgeniy-Eng"
            engine.setProperty('rate', 220)
            break

        if LANG == "EN" and voice.id == r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices\TokenEnums\RHVoice\Lyubov":
            default_voice=r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices\TokenEnums\RHVoice\Lyubov"
            engine.setProperty('rate', 190)
        elif LANG == "RU" and voice.id == r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices\TokenEnums\RHVoice\Victoria":
            default_voice=r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices\TokenEnums\RHVoice\Victoria"
            engine.setProperty('rate', 210)

    if default_voice != "":
        engine.setProperty("voice", default_voice)

    engine.save_to_file(translation, file_name)
    engine.runAndWait()
    return True

def get_voice_text(translation: str, LANG: str = "EN", GENDER: str = "F"):

    if f_load_pyttsx3 == False or translation == "":
        return None

    file_name_wav = f"voice/translate-{random.randint(0, 1000000)}.wav"
    while os.path.exists(file_name_wav):
        file_name_wav = f"voice/translate-{random.randint(0, 1000000)}.wav"

    if save_file_voice_text(file_name_wav, translation, LANG, GENDER):

        file_content = None
        with open(file_name_wav, "rb") as f:
            file_content = f.read()

        os.remove(file_name_wav)
        return file_content

    return None

def SaveWordToDictionary(db_user: DBUser, text: str, f_cleary: bool = False, f_skip: bool = False,
                         f_translate: bool = True, f_word_translate: str = ""):
    if f_skip and db_user.db_connect.get_word_id(text, "EN") is not None and text.find('^') >= 0: return

    if text.find("M:") >= 0 or text.find("F:") >= 0:
        text = text[2:].strip()

    if f_cleary:
        text = text.replace("...", "").replace("..", "").replace(".", "").replace(",", "").replace("!", "").replace("?", "").replace('"', "")
    translation = argostranslate(db_user, text, from_code, to_code) if f_translate else f_word_translate
    if f_cleary:
        translation = translation.replace(".", "").replace(",", "").replace("!", "").replace("?", "").replace("%s","").strip()

    voice_en = get_voice_text(text, "EN", "F")
    voice_ru = get_voice_text(translation, "RU", "F")
    db_user.db_connect.save_word_to_dict(text, "EN", voice_en, translation, "RU", voice_ru, "F")

    voice_en = get_voice_text(text, "EN", "M")
    voice_ru = get_voice_text(translation, "RU", "M")
    db_user.db_connect.save_word_to_dict(text, "EN", voice_en, translation, "RU", voice_ru, "M")

def Set_Slide_New_ListWords(db_user: DBUser, db_slide: DBSlide, ListWords: str):
    SQL = db_user.db_connect

    db_slide.List_Words = ListWords if ListWords != "-" else ""
    dict_list_words: dict = get_dict_words(db_slide.List_Words, db_slide.ROWID)
    db_slide.save(keyboard_dict=json.dumps(dict_list_words))
# {
#     "list_line":
#         [
#             {"text": text, "gender": gender, "list_words"[word1, word2, ...], "keyboard_line": InlineKeyboardButton, "keyboard_words": []},
#             {"text": text, "gender": gender, "list_words"[word1, word2, ...], "keyboard_line": InlineKeyboardButton, "keyboard_words": []}
#             ...
#         ]
# }
    if db_slide.List_Words == "":
        return

    for i in range(0, len(dict_list_words["list_line"])):
        GENDER: str = dict_list_words["list_line"][i]["gender"]
        # Перевод целого выражения
        text: str = dict_list_words["list_line"][i]["text"]
        SaveWordToDictionary(db_user, text, f_cleary=False, f_skip=True)

        # Перевод каждого слова
        for j in range(0, len(dict_list_words["list_line"][i]["list_words"])):
            word = dict_list_words["list_line"][i]["list_words"][j]
            SaveWordToDictionary(db_user, word, f_cleary=True, f_skip=True)

def check_keyboard_dict_correct(keyboard_dict) -> bool:
    return isinstance(keyboard_dict, dict) and keyboard_dict.get("list_line") is not None and \
           isinstance(keyboard_dict["list_line"], list) and keyboard_dict["list_line"] != []

def user_select_word_slide(db_user: DBUser, db_slide: DBSlide, list_i_j_word: list):
    SQL = db_user.db_connect
    
    i: int = None
    j: int = None

    if len(list_i_j_word) == 2:
        i = int(list_i_j_word[1])
    else:
        i = int(list_i_j_word[1])
        j = int(list_i_j_word[2]) if list_i_j_word[2] != "X" else -1

    keyboard, msg, a_voice_variants, text, translation_text, \
    translation_voice, subtitles_type, gender = get_settings_PlaySlide(db_user, db_slide, i, j)

    if keyboard is None: return

    if not (j is not None and j == -1) and subtitles_type >= 2 and translation_text is not None and \
        translation_voice is not None:
        if db_user.adm_level == 3:
            keyboard2 = InlineKeyboardMarkup()
            rowid = SQL.get_word_id(text, "EN")
            caption = f"{text}\n{translation_text}"
            keyboard2.add(
                InlineKeyboardButton(text="Поменять перевод", callback_data=f"/set_word_{rowid}_RU_{gender}"))
            db_user.save_message(bot.send_audio(db_user.chat_id,
                translation_voice, caption, reply_markup=keyboard2).message_id)
        else:
            db_user.save_message(bot.send_audio(db_user.chat_id, translation_voice, translation_text).message_id)

    if subtitles_type != 2:
        bot.edit_message_caption(chat_id=db_user.chat_id, message_id=db_user.msg_dialog_id,
                                 caption=msg, parse_mode="html", reply_markup=keyboard)


a_voice_variants_l = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
#keyboard, msg, a_voice_variants, text, translation_text, translation_voice, subtitles_type, gender
def get_settings_PlaySlide(db_user, db_slide, i, j):
    SQL = db_user.db_connect
    
    subtitles_type = db_user.subtitle_type #get_subtitles_type(db_user, DBLesson(SQL, db_slide.id_lesson))
    msg: str = f"<code>{db_slide.Caption}</code>" if db_slide.Caption != "" and db_slide.Caption != "-" else ""
    if db_slide.keyboard_dict == "":
        dict_list_words: dict = get_dict_words(db_slide.List_Words, db_slide.ROWID)
        db_slide.save(keyboard_dict=json.dumps(dict_list_words))

    keyboard_dict = json.loads(db_slide.keyboard_dict)
    # {
    #     "list_line":
    #         [
    #             {"text": text, "gender": gender, "list_words"[word1, word2, ...], "keyboard_line": InlineKeyboardButton, "keyboard_words": []},
    #             {"text": text, "gender": gender, "list_words"[word1, word2, ...], "keyboard_line": InlineKeyboardButton, "keyboard_words": []}
    #             ...
    #         ]
    # }
    check_keyboard_dict: bool = check_keyboard_dict_correct(keyboard_dict)

    DeleteOldMessages(db_user, True, 3)
    buttons: list = []
    btn: list = []

    if check_keyboard_dict: #Титры
        if j is not None and j == -1:
            if db_user.mode != 5: #Тестовая работа - пропускаем титры
                for key in keyboard_dict["list_line"]:
                    key_button = InlineKeyboardButton("").de_json(key["keyboard_line"])
                    if subtitles_type >= 2:  # Перевод титров в Аудио
                        key_button.text = "🔊" + key_button.text
                    buttons.append([key_button])
        elif subtitles_type != 2:
            row_width = 5
            for key in keyboard_dict["list_line"][i]["keyboard_words"]:
                key_button = InlineKeyboardButton("").de_json(key)
                btn.append(key_button)
                if len(btn) == row_width:
                    buttons.append(btn.copy())
                    btn.clear()
            btn.append(InlineKeyboardButton(text="🔙", callback_data=f"/select_word_{db_slide.ROWID}_{i}_X"))  # ⤴️⤴️
            buttons.append(btn.copy())

    # Кнопки ответов
    btn.clear()
    a_voice_variants = []
    k: int = 0
    list_variants = db_slide.get_list_variants()
    db_variant: DBVariant
    row_width = int(db_slide.db_rules.Format) if db_slide.db_rules.command(
        "_row_width") and db_slide.db_rules.Format.isdigit() else 1
    for db_variant in list_variants:
        key: InlineKeyboardButton = None
        if db_variant.db_rules.command("_button"):  # Переход
            key = InlineKeyboardButton(text=db_variant.Name, callback_data=f"/click_variant_{db_variant.ROWID}")
        elif db_variant.db_rules.command("_voice_button"):  # Переход
            Name = db_variant.Name
            if Name[:2] != "M:" and Name[:2] != "F:":
                Name = "F: " + Name
            a_voice_variants.append(Name)
            key = InlineKeyboardButton(text=a_voice_variants_l[k], callback_data=f"/click_variant_{db_variant.ROWID}")
            k += 1
            if k >= len(a_voice_variants_l): break
        if key is not None:
            btn.append(key)
            if len(btn) == row_width:
                buttons.append(btn.copy())
                btn.clear()
    if len(btn) != 0:  buttons.append(btn.copy())

    if db_user.adm_level == 3:
        buttons.append(
            [InlineKeyboardButton(text="\U00002699 Edit this Slide", callback_data=f"/get_slide2_{db_slide.ROWID}")])

    keyboard = InlineKeyboardMarkup(buttons)
    translation_voice, text, gender, translation_text = None, None, "F", None

    if check_keyboard_dict:  # Титры - перевод
        text = keyboard_dict["list_line"][i]["text"]
        gender = keyboard_dict["list_line"][i]["gender"] if "gender" in keyboard_dict["list_line"][i] else "F"
        id_word = SQL.get_word_id(text, "EN")
        translation_text = SQL.get_word_from_row(id_word, "RU")

        if not (j is not None and j == -1) and subtitles_type != 2:
            msg += f"\n{text} - {translation_text if translation_text != None else 'not translate'}"

        if j is not None and j != -1 and subtitles_type != 2:
            text = keyboard_dict["list_line"][i]["list_words"][j]
            text = text.replace("...", "").replace("..", "").replace(".", "").replace(",", "").replace("!", ""). \
                replace("?", "").replace('"', "")
            id_word = SQL.get_word_id(text, "EN")
            translation_text = SQL.get_word_from_row(id_word, "RU")
            msg += f"\n{text} - {translation_text if translation_text != None else 'not translate'}"

        if not (j is not None and j == -1) and subtitles_type >= 2 and translation_text is not None:
            translation_voice = SQL.get_voice_id(id_word, "RU", gender)

    return keyboard, msg, a_voice_variants, text, translation_text, translation_voice, subtitles_type, gender

def argostranslate(db_user: DBUser, text: str, from_code: str, to_code: str):
    if not f_load_argostranslate:
        try:
            bot.edit_message_text(chat_id=db_user.chat_id, message_id=db_user.msg_reply_id,
                              text="\U00002699 <b>Load ArgosTranslate module...</b>", parse_mode="html")
        except: pass
        load_argostranslate()

    try:
        bot.edit_message_text(chat_id=db_user.chat_id, message_id=db_user.msg_reply_id,
                              text=f"\U00002699 <b>Translating...</b>\n{text}", parse_mode="html")
    except: pass

    return argostranslate_translate.translate(text, from_code, to_code)

def Testing(db_user: DBUser, db_variant: DBVariant, type: str, f_variant: bool = None):
    SQL = db_user.db_connect
    
    if db_variant.id_slide == 0: return
    db_slide: DBSlide = DBSlide(SQL, db_variant.id_slide)
    if db_slide.ROWID == 0 or db_slide.id_lesson == 0: return
    db_lesson: DBLesson = DBLesson(SQL, db_slide.id_lesson)
    if db_lesson.ROWID == 0: return

    last_slide_id = 0
    msg_id_test = 0

    if type == "start":
        list_slide_test = db_lesson.get_list_slides_test()
        count_slide_test = len(list_slide_test)
        if len(list_slide_test) == 0:
            level, path = get_path_lesson(db_user, db_lesson)
            db_user.send_admin_message(f"Ошибка. Отсутствуют слайды для контрольной. "
                                       f"Lesson='{path}'", True)
            return

        control_list_id_slides = ""
        db_slide_for: DBSlide = list_slide_test.pop(0)
        last_slide_id = db_slide_for.ROWID
        for db_slide_for in list_slide_test:
            control_list_id_slides += f"{db_slide_for.ROWID},"
        control_list_id_slides = control_list_id_slides[:-1]
        cur_time = time_int()
        control_edate = 0 if db_lesson.test_time == 0 else db_lesson.test_time * 60 + cur_time
        db_game: DBGame = DBGame(SQL, db_user.ROWID, db_lesson.ROWID)
        db_game.save(id_cur_slide=last_slide_id, control_cdate=cur_time, control_edate=control_edate,
                     control_time=0, control_num_errors=0, control_result=2 if db_game.control_result==2 else 1,
                     control_list_id_slides=control_list_id_slides, id_variant_click=db_variant.ROWID)
        #text_msg = ""
        if db_variant.db_rules.command("_test_start") and db_variant.db_rules.Text != "":  # в db_variant.db_rules хранится сообщение от _test_start
            text_msg = db_variant.db_rules.Text
        else:
            time_test = f"{db_lesson.test_time} мин" if db_lesson.test_time != 0 else "-"
            text_msg = f"<b>Тестовая работа</b>\n" \
                       f"Количество заданий: <b>{count_slide_test}</b>\n" \
                       f"Время прохождения: <b>{time_test}</b>\n" \
                       f"Количество допустимых ошибок: <b>{db_lesson.test_num_errors}</b>"

        msg_id_test = bot.send_message(chat_id=db_user.chat_id, text=text_msg, parse_mode="html").message_id
        sleep(1)

    elif type == "continue":
        db_game: DBGame = DBGame(SQL, db_user.ROWID, db_lesson.ROWID)

        if not f_variant:
            db_game.save(control_num_errors=db_game.control_num_errors+1)

        if db_game.control_list_id_slides == "": # Конец тестирования
            c = time_int()
            t = c - db_game.control_cdate
            m = int(t / 60)
            s = t % 60
            f_test: bool = (db_game.control_edate == 0 or c <= db_game.control_edate) and \
                            db_game.control_num_errors <= db_lesson.test_num_errors

            msg_id_1 = bot.send_message(db_user.chat_id, text=f"{'👍' if f_test else '🤷‍♂️'}").message_id
            sleep(1)

            msg = f"<b>Результаты Тестовой работы:</b>\n" \
                  f"Количество ошибок: <b>{db_game.control_num_errors}</b>\n" \
                  f"Время выполнения: <b>{m} мин {s} сек</b>\n" \
                  f"Результат: <b>{'✅' if f_test else '❌'}</b>"

            keyboard = InlineKeyboardMarkup(row_width=6)

            keyboard.add(InlineKeyboardButton(text="Повторить урок", callback_data=f"/get_lesson_{db_lesson.ROWID}"))
            keyboard.add(InlineKeyboardButton(text="Повторить тест", callback_data=f"/get_lesson_test_{db_lesson.ROWID}"))
            keyboard.add(InlineKeyboardButton(text="Вернуться в Меню", callback_data=f"/get_lesson_{db_lesson.id_chapter}"))

            old_msg_dialog_id = db_user.msg_dialog_id
            msg_id_2 = bot.send_message(db_user.chat_id, text=msg, parse_mode="html", reply_markup=keyboard).message_id
            db_user.save_user(msg_dialog_id=msg_id_2)
            sleep(1)

            if f_test:
                f_edit: bool = db_game.control_result != 2 and db_game.user_skill == 0
                db_game.save(control_result=2, control_time=t)
                new_skill = db_lesson.skill+db_lesson.test_skill_decrement
                db_chapter: DBLesson = DBLesson(SQL, db_lesson.ROWID)
                while True:
                    db_chapter_game: DBGame = DBGame(SQL, db_user.ROWID, db_chapter.ROWID)
                    if f_edit:
                        if db_chapter_game.user_skill < new_skill:
                            db_chapter_game.save(user_skill=new_skill)
                    db_chapter_game.check_result_all_lessons()
                    if db_chapter.id_chapter == 0:
                        if db_chapter_game.user_skill < new_skill:
                            db_chapter_game.save(user_skill=new_skill)
                        break
                    db_chapter: DBLesson = DBLesson(SQL, db_chapter.id_chapter)

            elif db_game.control_result != 2:
                db_game.save(control_result=-1, control_time=t)

            db_user.save_user(mode=0, skill=(db_user.skill + 1) if f_test else db_user.skill)
            DeleteOldMessages(db_user)
            bot.delete_msg(db_user.chat_id, old_msg_dialog_id)
            db_user.save_message(msg_id_1)

        else: #Продолжение тестирования
            a_str_id_slides = db_game.control_list_id_slides.split(",")
            last_slide_id = int(a_str_id_slides.pop(0))
            control_list_id_slides = ",".join(a_str_id_slides)
            db_game.save(id_cur_slide=last_slide_id, control_list_id_slides=control_list_id_slides)

    # if db_variant.db_rules.command("_pause") and db_variant.db_rules.Format.isdigit():
    #     sleep(int(db_variant.db_rules.Format))
    #     if db_variant.db_rules.Text != "":
    #         msg_id = bot.send_message(chat_id=db_user.chat_id, text=db_variant.db_rules.Text,
    #                                   reply_markup=keyb_ok, parse_mode="html").message_id
    #         db_user.save_message(msg_id)
    #         sleep(1)

    if last_slide_id != 0:

        db_user.save_user(mode=5, last_video_id=last_slide_id)
        PlaySlide(db_user)

        if msg_id_test != 0: db_user.save_message(msg_id_test)

@bot.callback_query_handler(func=lambda call: True)
def callback(call: telebot.types.CallbackQuery):
    SQL = db_english.SQLiteClient(FILE_NAME_DB, token=TOKEN, admin_chat_id=ADMIN_CHAT_ID)
    db_user = GetUser(SQL, call.message.chat.id, call.from_user.first_name, call.from_user.username)
    if db_user is None: return

    if call.data == '/command_ok' or call.data == '/command_no' or call.data == '/command_cancel':
        bot.delete_msg(db_user.chat_id, call.message.id)
        db_user.save_user(mode=int(db_user.mode / 10) * 10, msg_reply_id=0)
    elif call.data.find("/bay") == 0:
        prices = [LabeledPrice(label='Подписка на месяц', amount=990*100)]
        bot.send_message(db_user.chat_id, parse_mode='html',
                         text="Для оплаты используйте данные тестовой карты: <code>1111 1111 1111 1026</code>, 12/22, CVC 000.",)
        bot.send_invoice(
            db_user.chat_id,  # chat_id
            'Подписка на месяц',  # title
            'Английский | Понятный вход - подписка на месяц.', # description
            'Подписка на месяц',  # invoice_payload
            PAYMENT_TOKEN,  # provider_token
            'rub',  # currency
            prices,  # prices
            # photo_url=None,
            # photo_height=0,  # !=0/None or picture won't be shown
            # photo_width=512,
            # photo_size=512,
            is_flexible=False,  # True If you need to set up Shipping Fee
            start_parameter='subscription-payment')
        bot.delete_msg(db_user.chat_id, call.message.message_id)

    elif call.data.find("/activate_key_") == 0:
        id_key = call.data[len('/activate_key_'):]
        db_key:DBKey = DBKey(SQL, ID=id_key)
        db_promo: DBPromo = DBPromo(SQL, db_key.id_promo)
        db_seller: DBSeller = DBSeller(SQL, db_promo.id_seller)
        list_active = db_key.get_list_activate()
        if db_seller.block == 1:
            bot.send_message(chat_id=db_user.chat_id, text="❌ Данный продавец заблокирован!\nОбратитесь в поддержку.")
        elif db_promo.block == 1:
            bot.send_message(chat_id=db_user.chat_id, text="❌ Данная подписка заблокирована!\nОбратитесь в поддержку.")
        elif len(list_active) < db_promo.count_lic:
            db_key.activate(db_user.ROWID)
            if db_user.license_date < time_int():
                db_user.license_date = time_int()+3600*24*db_promo.license_period
            else:
                db_user.license_date += 3600 * 24 * db_promo.license_period
            db_user.save_user()
            msg = f"🙋‍♂️ <b>Подписка успешно активированна!</b>\n" \
                    f"<i>Подписка действует до: {int_to_time_to_str(db_user.license_date, 3)} (по Москве)</i>"
            bot.send_message(chat_id=db_user.chat_id, text=msg, parse_mode="html")
        else:
            bot.send_message(chat_id=db_user.chat_id, text="❌ Данная подписка уже полностью активированна!")

        DeleteOldMessages(db_user)

    elif db_user.adm_level == 3 and call.data.find("/set_word_") == 0:
        params = call.data[len('/set_word_'):]
        db_user.save_user(current_variant_id=call.message.message_id, keyboard=params)
        send_reaply_message(db_user, f"Введите перевод", 11)

    elif db_user.adm_level == 3 and call.data.find("/set_voice_") == 0:
        params = call.data[len('/set_voice_'):]
        a_params = params.split('_')
        try:
            id_word = int(a_params[0])
            lang = a_params[1]
            gender = 'FAMALE' if a_params[2] == 'F' else 'MAIL'
            word = SQL.get_word_from_row(id_word, lang)
            # Здесь используем keyboard для хранения параметров
            params += "_"+call.message.caption
            db_user.save_user(keyboard=params, current_variant_id=call.message.message_id)
            send_reaply_message(db_user, f"Озвучте выражение, или пришлите файл\n{word}\nlang={lang}\ngender={gender}", 12)
        except:
            msg_id = bot.send_message(db_user.chat_id, f"Ошибка параметров запроса на изменение озвучивания выражения {params}").message_id
            db_user.save_message(msg_id)

    #Не соответствие текущего диалога и комманды от другого диалога
    elif call.message.message_id != db_user.msg_dialog_id and call.message.message_id != db_user.msg_reply_id:
        #bot.delete_msg_dialog(db_user)
        #bot.delete_reply_msg(db_user)
        print(f"User {db_user.Name} mima")
        return

    elif call.data == '/command_yes' and db_user.mode == 6:
        if db_user.current_lesson_id !=0 and DBLesson(SQL, db_user.current_lesson_id).ROWID != 0:
            db_game: DBGame = DBGame(SQL, db_user.ROWID, db_user.current_lesson_id)
            db_game.save(control_result=0)
        List_Lessons_Root(db_user, 0)

    elif call.data == '/start_main':
        List_Lessons_Root(db_user, 0, 0, 0, 0)

    elif call.data.find("/click_variant_") == 0:
        id_variant = int(call.data[len('/click_variant_'):])
        db_variant: DBVariant = DBVariant(SQL, id_variant)
        if db_variant.ROWID == 0:
            return

        if db_user.chat_id != ADMIN_CHAT_ID and db_variant.db_rules.command("_send_admin_message"):
            db_user.send_admin_message(f"_send_admin_message\n{db_variant.db_rules.Text}", True)

        if db_variant.db_rules.command("_set_game_true"):
            db_game: DBGame = DBGame(SQL, db_user.ROWID, DBSlide(SQL, db_variant.id_slide).id_lesson)
            db_game.save(control_result=2)

        if db_variant.db_rules.command("_set_game_false"):
            db_game: DBGame = DBGame(SQL, db_user.ROWID, DBSlide(SQL, db_variant.id_slide).id_lesson)
            db_game.save(control_result=0)

        if db_variant.db_rules.command("_goto_menu"):
            List_Lessons_Root(db_user)
            return

        if db_user.mode == 5:  # Контрольная Прохождение
            f_variant = True if db_variant.db_rules.command("_true_answer") else False if \
                        db_variant.db_rules.command("_false_answer") or \
                        db_variant.id_next_slide == 0 or \
                        db_variant.id_next_slide == db_variant.ROWID else True
            Testing(db_user, db_variant, "continue", f_variant)

        elif db_variant.db_rules.command("_test_start"): #Тесты Старт
            Testing(db_user, db_variant, "start")

        elif db_variant.id_next_slide != 0:
            db_user.save_user(mode=0, last_video_id=db_variant.id_next_slide)
            PlaySlide(db_user)

    elif call.data.find("/get_lesson_test_") == 0:
        id_lesson = int(call.data[len('/get_lesson_test_'):])
        db_lesson: DBLesson = DBLesson(SQL, id_lesson if id_lesson != 0 else -1)
        if db_lesson.ROWID != 0:
            db_game: DBGame = DBGame(SQL, db_user.ROWID, db_lesson.ROWID)
            if db_game.ROWID != 0:
                db_variant: DBVariant = DBVariant(SQL, db_game.id_variant_click)
                if db_variant.ROWID != 0:
                    Testing(db_user, db_variant, "start")

    elif call.data.find("/get_lesson_") == 0:
        id_lesson = int(call.data[len('/get_lesson_'):])
        db_lesson: DBLesson = DBLesson(SQL, id_lesson if id_lesson != 0 else -1)

        if db_lesson.ROWID == 0:
            List_Lessons_Root(db_user, 0, 0, 0, 0)
        else:
            level, path = get_path_lesson(db_user, db_lesson, False)
            #db_game: DBGame = DBGame(SQL, db_user.ROWID, db_lesson.id_chapter)

            if db_user.adm_level == 3 or \
                (not db_lesson.db_rules.command("_not_ready") and \
                not db_lesson.db_rules.command("_unvisible") and level >= db_lesson.skill):

                time_cur = time_int()

                # Проверка подписки (только на урок, а не на каталог)
                if db_user.adm_level != 3 and level == db_lesson.skill and db_lesson.type == 2 and \
                   db_user.license_date < time_cur and \
                   not db_lesson.db_rules.command("_free_price"):

                    display_subscription(db_user)
                    bot.delete_msg(db_user.chat_id, db_user.msg_dialog_id)
                    # msg = "❗️ Оформите подписку." \
                    #     if db_user.license_date == 0 else \
                    #     f"❗️ Истёк срок вашей подписки: {int_to_time_to_str(db_user.license_date, 3)} (по Москве)\n\n" \
                    #     f"Оформите подписку заново.", db_user.mode
                    # send_reaply_message(db_user, msg, db_user.mode)

                elif db_user.adm_level == 3 or db_lesson.type == 1:
                    db_user.save_user(mode=0, current_lesson_id=db_lesson.ROWID, current_video_id=0, current_variant_id=0, last_video_id=0) #, msg_dialog_id=0
                    refresh_dialog(db_user)

                elif db_lesson.type == 2:
                    #if db_lesson.db_rules.command("_send_admin_message") and db_user.adm_level == 0:
                    username = "" if db_user.UserName == None or db_user.UserName == "" else f" @{db_user.UserName}"
                    msg_id = bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"{db_user.Name}{username}\n{path}", parse_mode="html").message_id
                    db_user.save_message(msg_id, "", 0, ADMIN_CHAT_ID)

                    db_slide:DBSlide = DBSlide(SQL)
                    if db_slide.get_from_num(1, db_lesson.ROWID):
                        db_user.save_user(last_video_id=db_slide.ROWID)
                        PlaySlide(db_user)

    elif call.data.find('/select_word_') == 0:
        id_i_j_word: str = call.data[len('/select_word_'):]

        if db_user.last_word != id_i_j_word and (db_user.last_video_id != 0 or db_user.current_video_id != 0):

            id_slide = db_user.last_video_id if db_user.last_video_id != 0 else db_user.current_video_id
            list_i_j_word: list = id_i_j_word.split('_')

            if int(list_i_j_word[0]) == id_slide:
                db_slide: DBSlide = DBSlide(SQL, id_slide)
                user_select_word_slide(db_user, db_slide, list_i_j_word)
                db_user.save_user(last_word=id_i_j_word)
            else:
                print("click user not slide :))")

    elif call.data.find("/get_slide2_") == 0:
        id_slide = int(call.data[len('/get_slide2_'):])
        db_slide: DBSlide = DBSlide(SQL, id_slide)
        if db_user.last_video_id != 0:
            db_user.save_message(db_user.msg_dialog_id)
            db_user.save_user(msg_dialog_id=0)
        db_user.save_user(mode=30, current_lesson_id=db_slide.id_lesson, current_video_id=db_slide.ROWID,
                          current_variant_id=0, last_video_id=0)
        refresh_dialog(db_user)

    elif call.data.find("/set_subtitles_") == 0 and call.data[len('/set_subtitles_'):].isdigit():
        subtitle_type = int(call.data[len('/set_subtitles_'):])
        db_user.save_user(subtitle_type=subtitle_type)
        # msg_id = bot.send_message(db_user.chat_id, f"subtitles_type = {subtitle_type}").message_id
        # db_user.save_message(msg_id)
        if db_user.last_video_id ==0:
            List_Lessons_Root(db_user, 0)
        else:
            PlaySlide(db_user)

    elif db_user.adm_level == 3 and db_user.last_video_id == 0:

        if call.data == "/admin_panel_close" and SQL.get_admin_panel()>0:
            SQL.set_admin_panel(0)
            List_Lessons_Root(db_user, 0, 0)

        elif call.data.find("/get_seller_") == 0 and SQL.get_admin_panel() > 0:
            id_seller = int(call.data[len('/get_seller_'):])
            db_user.save_user(mode=120, current_variant_id=id_seller)
            refresh_dialog(db_user)

        elif call.data.find("/get_promo_") == 0 and SQL.get_admin_panel() > 0:
            id_seller = int(call.data[len('/get_promo_'):])
            db_user.save_user(mode=140, current_variant_id=id_seller)
            refresh_dialog(db_user)

        elif call.data.find("/block_promo_") == 0 and SQL.get_admin_panel() > 0:
            id_promo = int(call.data[len('/block_promo_'):])
            db_promo: DBPromo = DBPromo(SQL, id_promo)
            db_promo.save(block = 1 - db_promo.block)
            refresh_dialog(db_user)

        elif call.data.find("/list_keys_promo_") == 0 and SQL.get_admin_panel() > 0:
            id_promo = int(call.data[len('/list_keys_promo_'):])
            db_promo: DBPromo = DBPromo(SQL, id_promo)
            db_seller: DBSeller = DBSeller(SQL, db_promo.id_seller)
            list_keys: list = db_promo.get_list_keys()
            j = 1
            msg, i = f"Эмиссия от: {int_to_time_to_str(db_promo.cdate, 3)}\n" \
                     f"Продавец: {db_seller.Name}\n" \
                     f"Ключей: {db_promo.count_key}\n" \
                     f"Подписок на ключ: {db_promo.count_lic}\n" \
                     f"Активироваций: {db_promo.count_activate_key}\n" \
                     f"Страница: {j}\n\n", 0
            db_key: DBKey = None
            for db_key in list_keys:
                list_activate = db_key.get_list_activate()
                s_active = f" - act: {len(list_activate)}" if len(list_activate)>0 else ""
                msg += f"{db_key.S_Number}{s_active}\n"
                i += 1
                if i == 50:
                    msg_id = bot.send_message(db_user.chat_id, msg).message_id
                    db_user.save_message(msg_id)
                    j += 1
                    msg, i = f"{db_seller.Name} [{db_promo.count_key}/{db_promo.count_lic}] {int_to_time_to_str(db_promo.cdate, 3)} (стр. {j})\n\n", 0
            if i != 0:
                msg_id = bot.send_message(db_user.chat_id, msg).message_id
                db_user.save_message(msg_id)

        elif call.data == "/new_saller" and SQL.get_admin_panel() > 0:
            db_seller: DBSeller = DBSeller(SQL)
            db_seller.save(Name="Name", Caption="Caption")
            db_user.save_user(mode=120, current_variant_id=db_seller.ID)
            refresh_dialog(db_user)

        elif call.data == "/seller_name" and SQL.get_admin_panel() > 0:
            send_reaply_message(db_user, "Введите Name Продавца", 121)

        elif call.data == "/seller_caption" and SQL.get_admin_panel() > 0:
            send_reaply_message(db_user, "Введите Caption Продавца", 122)

        elif call.data == "/seller_block" and SQL.get_admin_panel() > 0:
            db_seller: DBSeller = DBSeller(SQL, db_user.current_variant_id)
            db_seller.save(block=1-db_seller.block)
            refresh_dialog(db_user)

        elif call.data == "/seller_delete" and SQL.get_admin_panel() > 0:
            send_reaply_message(db_user, "Удалить Продавца?", 123, keyb_y_n)

        elif call.data == "/sellers_list" and SQL.get_admin_panel()>0:
            db_user.save_user(mode=110)
            refresh_dialog(db_user)

        elif call.data == "/admin_panel" and SQL.get_admin_panel()>0:
            db_user.save_user(mode=100)
            refresh_dialog(db_user)

        elif call.data == "/promo_create" and SQL.get_admin_panel()>0:
            keyboard = InlineKeyboardMarkup()
            db_seller: DBSeller = DBSeller(SQL)
            list_sellers = db_seller.get_list_sellers()
            for db_seller in list_sellers:
                keyboard.add(
                    InlineKeyboardButton(text=f"{db_seller.Name}", callback_data=f"/key_get_seller_{db_seller.ID}"))
            send_reaply_message(db_user, f"🛠 <b>Создание ключей</b>\n\nВыберите продавца", 102, keyboard)

        elif call.data.find("/key_get_seller_") == 0:
            id_seller = int(call.data[len('/key_get_seller_'):])
            db_seller:DBSeller = DBSeller(SQL, id_seller)
            db_user.save_user(current_video_id=id_seller)
            send_reaply_message(db_user, f"🛠 <b>Создание ключей</b>\nПродавец: {db_seller.Name}\n\nВведите Примечание", 103)

        elif call.data == "/promo_list" and SQL.get_admin_panel()>0:
            db_user.save_user(mode=130)
            refresh_dialog(db_user)

        elif call.data.find("/set_slide_up_") == 0:
            id_slide = int(call.data[len('/set_slide_up_'):])
            db_slide: DBSlide = DBSlide(SQL, id_slide)
            DBLesson(SQL, db_slide.id_lesson).normalize_num_slides()
            db_slide: DBSlide = DBSlide(SQL, id_slide)
            db_slide_prev: DBSlide = DBSlide(SQL, 0, db_slide.id_lesson, db_slide.num-1)
            if db_slide_prev.ROWID != 0:
                num_prev: int = db_slide_prev.num
                db_slide_prev.save(num=db_slide.num)
                db_slide.save(num=num_prev)
                refresh_dialog(db_user)

        elif call.data.find("/set_slide_down_") == 0:
            id_slide = int(call.data[len('/set_slide_down_'):])
            db_slide: DBSlide = DBSlide(SQL, id_slide)
            DBLesson(SQL, db_slide.id_lesson).normalize_num_slides()
            db_slide: DBSlide = DBSlide(SQL, id_slide)
            db_slide_next: DBSlide = DBSlide(SQL, 0, db_slide.id_lesson, db_slide.num + 1)
            if db_slide_next.ROWID != 0:
                num_next: int = db_slide_next.num
                db_slide_next.save(num = db_slide.num)
                db_slide.save(num = num_next)
                refresh_dialog(db_user)

        elif call.data.find("/set_slide_copy_") == 0:
            id_slide = int(call.data[len('/set_slide_copy_'):])
            db_slide: DBSlide = DBSlide(SQL, id_slide)
            db_new_slide = db_slide.copy(db_slide.id_lesson)
            db_new_slide.save(Name=f"{db_slide.Name} - copy")
            DBLesson(SQL, db_slide.id_lesson).normalize_num_slides()
            db_user.save_user(current_video_id=db_new_slide.ROWID)
            refresh_dialog(db_user)

        elif call.data.find("/lesson_new") == 0:
            if db_user.current_lesson_id != 0:
                db_lesson: DBLesson = DBLesson(SQL, db_user.current_lesson_id)
                if db_lesson.type == 2: # Коллизия - не может Урок со слайдами быть каталогом для других уроков
                    msg_id = bot.send_message(db_user.chat_id, text="Ошибка создания урока - коллизия. Не может Урок со слайдами быть каталогом для других уроков").message_id
                    db_user.save_message(msg_id)
                    return
                elif db_lesson.type != 1:
                    db_lesson.save(type = 1)
            db_lesson_new: DBLesson = DBLesson(SQL, 0, None, db_user.current_lesson_id)
            db_paren_game: DBGame = get_parent_game(db_user, db_lesson_new)
            db_lesson_new.save(skill=db_paren_game.user_skill)
            db_lesson_new.normalize_num_lessons()
            db_user.save_user(mode=0, current_lesson_id=db_lesson_new.ROWID, current_video_id=0, current_variant_id=0)
            refresh_dialog(db_user)

        elif call.data.find("/set_lesson_up_") == 0:
            id_lesson = int(call.data[len('/set_lesson_up_'):])
            db_lesson: DBLesson = DBLesson(SQL, id_lesson)
            db_lesson_prev: DBLesson = DBLesson(SQL, 0, db_lesson.num-1, db_lesson.id_chapter)
            if db_lesson_prev.ROWID != 0:
                num_prev: int = db_lesson_prev.num
                db_lesson_prev.save(num=db_lesson.num)
                db_lesson.save(num=num_prev)
                refresh_dialog(db_user)

        elif call.data.find("/set_lesson_down_") == 0:
            id_lesson = int(call.data[len('/set_lesson_down_'):])
            db_lesson: DBLesson = DBLesson(SQL, id_lesson)
            db_lesson_next: DBLesson = DBLesson(SQL, 0, db_lesson.num + 1, db_lesson.id_chapter)
            if db_lesson_next.ROWID != 0:
                num_next: int = db_lesson_next.num
                db_lesson_next.save(num=db_lesson.num)
                db_lesson.save(num=num_next)
                refresh_dialog(db_user)

        elif call.data.find("/normalize_lesson_") == 0:
            id_lesson = int(call.data[len('/normalize_lesson_'):])
            db_lesson: DBLesson = DBLesson(SQL, id_lesson)
            list_slides: list = db_lesson.get_list_slides()
            if len(list_slides)>0:
                count_link = 0
                for i in range(0, len(list_slides)-1):
                    db_slide: DBSlide = list_slides[i]
                    list_variants = db_slide.get_list_variants()
                    db_variant: DBVariant
                    for db_variant in list_variants:
                        if db_variant.db_rules.command("_true_answer") or \
                        (db_variant.db_rules.command("_button") and db_variant.Name=="Следующий слайд ⤵️"):
                            db_variant.save(id_next_slide=list_slides[i+1].ROWID)
                            count_link += 1
                refresh_dialog(db_user)
                db_user.save_message(bot.send_message(db_user.chat_id,
                    f"<b>Перелинковка</b>\nУстановлено линков: <b>{count_link}</b>", parse_mode="html").message_id)

        elif call.data.find("/change_lesson_name") == 0:
            send_reaply_message(db_user, "Input Name Lesson", 21)
        elif call.data.find("/change_lesson_caption") == 0:
            send_reaply_message(db_user, "Input Caption Lesson", 22)
        elif call.data.find("/delete_lesson") == 0:
            db_lesson = DBLesson(SQL, db_user.current_lesson_id)
            send_reaply_message(db_user, f"\U0000274C Delete Lesson <b>{db_lesson.Name}</b>?", 23, keyb_y_n)
        elif call.data.find("/play_lesson_") == 0:
            if db_user.current_lesson_id != 0 and DBLesson(SQL, db_user.current_lesson_id).type == 2:
                db_user.save_user(mode=0, last_video_id=0)
                PlaySlide(db_user)
        elif call.data.find("/change_lesson_skill") == 0:
            send_reaply_message(db_user, "Input Skill Lesson", 24)
        elif call.data.find("/set_lesson_copy_") == 0:
            id_lesson = int(call.data[len('/set_lesson_copy_'):])
            db_lesson: DBLesson = DBLesson(SQL, id_lesson)
            db_user.save_user(current_lesson_id=id_lesson)
            send_reaply_message(db_user, f"Copy Lesson <b>'{db_lesson.Name}'</b>?", 25, keyb_y_n)
        elif call.data.find("/change_lesson_chapter") == 0 and db_user.current_lesson_id != 0:
            keyboard = InlineKeyboardMarkup(row_width=6)
            db_lesson = DBLesson(SQL, db_user.current_lesson_id if db_user.current_lesson_id != 0 else -1)

            if db_lesson.id_chapter != 0:
                db_lesson_parrent = DBLesson(SQL, db_lesson.id_chapter)
                keyboard.add(InlineKeyboardButton(text="Back Chapter \U00002934",
                         callback_data=f"/set_lesson_chapter_{db_lesson.ROWID}_{db_lesson_parrent.id_chapter}"))

            list_lessons = db_lesson.get_list_lessons(db_lesson.id_chapter)
            db_chapter: DBLesson
            for db_chapter in list_lessons:
                if db_chapter.type != 2 and db_lesson.ROWID != db_chapter.ROWID:
                    keyboard.add(InlineKeyboardButton(text=f"{db_chapter.s_type} {db_chapter.num}. {db_chapter.Name}",
                                 callback_data=f"/set_lesson_chapter_{db_lesson.ROWID}_{db_chapter.ROWID}"))

            keyboard.add(InlineKeyboardButton(text="Cancel", callback_data=f"/command_cancel"))

            send_reaply_message(db_user, "Select Chapter for Lesson", 20, keyboard)

        elif call.data.find("/set_lesson_chapter_") == 0:
            str_Lesson_Chapter: str = call.data[len('/set_lesson_chapter_'):]
            a_Lesson_Chapter: list = str_Lesson_Chapter.split("_")
            try:
                id_lesson = int(a_Lesson_Chapter[0])
                db_lesson = DBLesson(SQL, id_lesson)

                if db_lesson.ROWID != 0:

                    old_id_chapter = db_lesson.id_chapter
                    id_new_chapter = int(a_Lesson_Chapter[1])
                    db_new_chapter: DBLesson = DBLesson(SQL, id_new_chapter if id_new_chapter != 0 else -1)

                    if db_new_chapter.ROWID != 0:
                        db_new_chapter.normalize_num_lessons()
                        db_lesson.save(id_chapter=id_new_chapter, num=db_new_chapter.get_max_num_lessons()+1)
                        if db_new_chapter.type == 0:
                            db_new_chapter.save(type = 1)
                    else:
                        db_new_chapter.normalize_num_lessons(0)
                        db_lesson.save(id_chapter=0, num=db_new_chapter.get_max_num_lessons(0) + 1)

                    if db_lesson.normalize_num_lessons(old_id_chapter) == 0:
                        db_old_chapter: DBLesson = DBLesson(SQL, old_id_chapter)
                        db_old_chapter.save(type=0)

                    db_user.save_user(mode=0, current_lesson_id=id_lesson, current_video_id=0, current_variant_id=0)
                    refresh_dialog(db_user)

            except: pass

        elif call.data.find("/ch_les_test_time") == 0:
            send_reaply_message(db_user, "Input time from test in seconds", 26)

        elif call.data.find("/ch_les_test_num_error") == 0:
            send_reaply_message(db_user, "Input count errors from test", 27)

        elif call.data.find("/ch_les_skill_decrement") == 0:
            send_reaply_message(db_user, "Input decrement skill from test", 28)


        elif call.data.find("/add_new_slide") == 0:
            if db_user.current_lesson_id != 0:
                db_lesson: DBLesson = DBLesson(SQL, db_user.current_lesson_id)
                if db_lesson.type == 1: # Коллизия - не может Урок-каталог быть Уроком со слайдами
                    msg_id = bot.send_message(db_user.chat_id, text="Ошибка создания слайда - коллизия. Не может Урок-каталог быть Уроком со слайдами").message_id
                    db_user.save_message(msg_id)
                else:
                    send_reaply_message(db_user, "Load Video of Slide", 34)

        elif call.data.find("/get_slide_") == 0:
            id_slide = int(call.data[len('/get_slide_'):])
            db_slide: DBSlide = DBSlide(SQL, id_slide)
            if db_user.last_video_id != 0:
                db_user.save_message(db_user.msg_dialog_id)
                db_user.save_user(last_video_id=0, msg_dialog_id=0)
            db_user.save_user(mode=30, current_lesson_id=db_slide.id_lesson, current_video_id=db_slide.ROWID, current_variant_id= 0)
            refresh_dialog(db_user)
        elif call.data.find("/change_slide_name") == 0:
            send_reaply_message(db_user, "Input Name Slide", 31)
        elif call.data.find("/change_slide_caption") == 0:
            send_reaply_message(db_user, "Input Caption Slide", 32)
        elif call.data.find("/change_slide_words") == 0:
            send_reaply_message(db_user, "Input words Slide", 33)
        elif call.data.find("/change_slide_video") == 0:
            send_reaply_message(db_user, "Load Video of Slide", 35)
        elif call.data.find("/change_slide_rules") == 0:
            send_reaply_message(db_user, "Input Rules Slide", 36)
        elif call.data.find("/change_slide_message") == 0:
            send_reaply_message(db_user, "Input Message Slide", 37)
        elif call.data.find("/delete_slide") == 0 and db_user.current_video_id !=0:
            db_slide = DBSlide(SQL, db_user.current_video_id)
            send_reaply_message(db_user, f"Delete Slide <b>{db_slide.Name}</b>?", 35, keyb_y_n)
        elif call.data.find("/play_slide") == 0:
            db_user.save_user(mode=0, last_video_id=db_user.current_video_id)
            PlaySlide(db_user)
        elif call.data.find("/slide_is_test") == 0 and db_user.current_video_id !=0:
            db_slide = DBSlide(SQL, db_user.current_video_id)
            db_slide.save(is_test=1-db_slide.is_test)
            refresh_dialog(db_user)

        elif call.data.find("/add_new_variant") == 0:
            db_variant: DBVariant = DBVariant(SQL, 0, db_user.current_video_id)
            db_user.save_user(mode=40, current_variant_id=db_variant.ROWID)
            refresh_dialog(db_user)

        elif call.data.find("/get_variant_") == 0:
            id_variant = int(call.data[len('/get_variant_'):])
            db_variant: DBVariant = DBVariant(SQL, id_variant)
            db_user.save_user(mode=40, current_variant_id=db_variant.ROWID)
            refresh_dialog(db_user)
        elif call.data.find("/change_variant_name") == 0:
            send_reaply_message(db_user, "Input Name Variant", 41)
        elif call.data.find("/change_variant_caption") == 0:
            send_reaply_message(db_user, "Input Caption Variant", 42)

        elif call.data.find("/change_variant_next") == 0:
            keyboard = InlineKeyboardMarkup(row_width=6)
            keyboard.add(InlineKeyboardButton(text=f"\U00002699 Remove Next Slide", callback_data=f"/delete_next_slide"))
            db_lesson: DBLesson = DBLesson(SQL, db_user.current_lesson_id)
            list_slides = db_lesson.get_list_slides()
            for db_slide in list_slides:
                keyboard.add(InlineKeyboardButton(text=f"{db_slide.num}. {db_slide.Name}",
                                                  callback_data=f"/set_goto_slide_{db_slide.ROWID}"))
            keyboard.add(InlineKeyboardButton(text=f"\U00002699 Cancel", callback_data=f"/command_cancel"))
            send_reaply_message(db_user, "<b>Change Next Slide of Variant</b>", 43, keyboard)

        elif call.data.find("/set_goto_slide_") == 0:
            id_slide = int(call.data[len('/set_goto_slide_'):])
            DBVariant(SQL, db_user.current_variant_id).save(id_next_slide=id_slide)
            db_user.save_user(mode=40)
            refresh_dialog(db_user)

        elif call.data.find("/delete_next_slide") == 0:
            DBVariant(SQL, db_user.current_variant_id).save(id_next_slide=0)
            db_user.save_user(mode=40)
            refresh_dialog(db_user)

        elif call.data.find("/delete_variant") == 0:
            db_variant = DBVariant(SQL, db_user.current_variant_id)
            send_reaply_message(db_user, f"Delete Variant <b>{db_variant.Name}</b>?", 44, keyb_y_n)

        elif call.data.find("/add_templates_variant") == 0:
            keyboard = InlineKeyboardMarkup(row_width=6)
            keyboard.add(InlineKeyboardButton(text="❌Delete All Variants❌", callback_data="/add_template_9"))
            keyboard.add(InlineKeyboardButton(text="🎤Yes-TRUE | 🎤No-FALSE", callback_data="/add_template_1"))
            keyboard.add(InlineKeyboardButton(text="🎤Yes-FALSE | 🎤No-TRUE", callback_data="/add_template_2"))
            keyboard.add(InlineKeyboardButton(text="✅-TRUE | ❌-FALSE", callback_data="/add_template_3"))
            keyboard.add(InlineKeyboardButton(text="✅-FALSE | ❌-TRUE", callback_data="/add_template_4"))
            keyboard.add(InlineKeyboardButton(text="\U00002795\U00002795\U00002795 multi button", callback_data="/add_template_5"))
            keyboard.add(InlineKeyboardButton(text="\U00002795 В начало урока ⤴️", callback_data="/add_template_7"))
            keyboard.add(InlineKeyboardButton(text="\U00002795 Следующий слайд ⤵️", callback_data="/add_template_6"))
            keyboard.add(InlineKeyboardButton(text="❓Тестовая работа❓", callback_data="/add_template_8"))
            keyboard.add(InlineKeyboardButton(text="Переход в Меню", callback_data="/add_template_10"))
            keyboard.add(InlineKeyboardButton(text="\U00002795\U00002795 multi check voice",
                                              callback_data="/add_template_11"))
            keyboard.add(InlineKeyboardButton(text="\U00002699 Cancel", callback_data="/command_cancel"))
            send_reaply_message(db_user, "<b>Select Template Variant</b>", 30, keyboard)

        elif call.data == "/add_template_5":
            send_reaply_message(db_user, "<b>Введите наименование кнопок через запятую. Первая кнопка - правильный вариант.</b>", 38)

        elif call.data == "/add_template_11":
            send_reaply_message(db_user, "<b>Введите Check voice (голосовые ответы) через запятую. Первый - правильный вариант.</b>", 39)

        elif call.data.find("/add_template_") == 0 and db_user.current_lesson_id != 0 and db_user.current_video_id != 0:
            id = int(call.data[len('/add_template_'):])
            db_slide = DBSlide(SQL, db_user.current_video_id)

            if id == 1:
                create_variants_from_text(db_user, db_slide, "yes;no", "_voice")
            elif id == 2:
                create_variants_from_text(db_user, db_slide, "no;yes", "_voice")
            elif id == 3:
                create_variants_from_text(db_user, db_slide, "✅ Yes;❌ No", "_button")
            elif id == 4:
                create_variants_from_text(db_user, db_slide, "❌ No;✅ Yes", "_button")
            elif id == 9:
                create_variants_from_text(db_user, db_slide, "") #Delete All Variants
            else: #6, 7, 8, 10
                db_variant: DBVariant = DBVariant(SQL, 0, db_slide.ROWID)
                if id == 6:
                    Name = "Следующий слайд ⤵️"
                    Caption = "_button"
                    db_slide_next: DBSlide = DBSlide(SQL)
                    id_next_slide: int = db_slide_next.ROWID if db_slide_next.get_from_num(db_slide.num + 1, db_slide.id_lesson) else 0
                elif id == 7:
                    Name = "В начало урока ⤴️"
                    Caption = "_button"
                    db_slide_next: DBSlide = DBSlide(SQL)
                    id_next_slide: int = db_slide_next.ROWID if db_slide_next.get_from_num(1, db_slide.id_lesson) else 0
                elif id == 8:
                    Name = "❓Тестовая работа❓"
                    Caption = "_button\n_test_start"
                    id_next_slide = 0
                elif id == 10:
                    Name = "Переход в Меню"
                    Caption = "_button\n_goto_menu"
                    id_next_slide = 0

                db_variant.save(Name=Name, Caption=Caption, id_next_slide=id_next_slide)

            db_user.save_user(mode=30)
            refresh_dialog(db_user)

        elif call.data == '/command_yes':

            if db_user.mode == 123 and SQL.get_admin_panel()>0:
                DBSeller(SQL, db_user.current_variant_id).delete()
                db_user.save_user(mode=110, current_variant_id=0)
                refresh_dialog(db_user)

            if db_user.mode == 44:
                DBVariant(SQL, db_user.current_variant_id).delete()
                db_user.save_user(mode=30, current_variant_id=0)
                refresh_dialog(db_user)

            if db_user.mode == 35:
                DBSlide(SQL, db_user.current_video_id).delete()
                db_user.save_user(mode=20, current_video_id=0, current_variant_id=0)
                refresh_dialog(db_user)

            if db_user.mode == 23:
                db_lesson = DBLesson(SQL, db_user.current_lesson_id)
                if db_user.msg_reply_id != 0:
                    try: bot.edit_message_text(chat_id=db_user.chat_id, message_id=db_user.msg_reply_id,
                                                  text=f"\U00002699 <b>Deleting lesson '{db_lesson.Name}'...</b>", parse_mode="html")
                    except: db_user.save_user(msg_reply_id=0)

                #SQL.set_access_system(-1)

                db_lesson.delete()
                #SQL.sql_execute("VACUUM")

                #SQL.set_access_system(+1)

                if db_user.msg_reply_id != 0:
                    try: bot.edit_message_text(chat_id=db_user.chat_id, message_id=db_user.msg_reply_id,
                                                  text="\U00002699 <b>Delete lesson - DONE</b>", parse_mode="html")
                    except: db_user.save_user(msg_reply_id=0)

                db_user.save_user(mode=10, current_lesson_id=db_lesson.id_chapter, current_video_id=0, current_variant_id=0)
                sleep(1)
                refresh_dialog(db_user)

            if db_user.mode == 25 and db_user.current_lesson_id>0:
                db_lesson: DBLesson = DBLesson(SQL, db_user.current_lesson_id)
                if db_user.msg_reply_id != 0:
                    try: bot.edit_message_text(chat_id=db_user.chat_id, message_id=db_user.msg_reply_id,
                                                  text=f"\U00002699 <b>Coping lesson '{db_lesson.Name}'...</b>", parse_mode="html")
                    except: db_user.save_user(msg_reply_id=0)

                db_lesson_new: DBLesson = db_lesson.copy()
                Caption = db_lesson_new.Caption if db_lesson_new.db_rules.command("_unvisible") else \
                    "_unvisible" if db_lesson_new.Caption=="" or db_lesson_new.Caption=="-" else \
                    db_lesson_new.Caption+"\n_unvisible"
                db_lesson_new.save(id_chapter=db_lesson.id_chapter, Caption=Caption)
                db_user.save_user(mode=20, current_lesson_id=db_lesson_new.ROWID, current_video_id=0, current_variant_id=0)

                if db_user.msg_reply_id != 0:
                    try: bot.edit_message_text(chat_id=db_user.chat_id, message_id=db_user.msg_reply_id,
                                                  text="\U00002699 <b>Copy - DONE</b>", parse_mode="html")
                    except: db_user.save_user(msg_reply_id=0)
                sleep(1)
                refresh_dialog(db_user)

def send_reaply_message(db_user: DBUser, text: str, mode: int, keyboard = None) -> int:
    if keyboard is None: keyboard=keyb_cancel
    bot.delete_reply_msg(db_user)
    reply_msg_id = bot.send_message(chat_id=db_user.chat_id, text=text, reply_markup=keyboard, parse_mode="html").message_id
    db_user.save_user(msg_reply_id=reply_msg_id, mode=mode)
    return reply_msg_id

# def get_subtitles_type(db_user:DBUser, db_lesson: DBLesson) -> int:
#     SQL = db_user.db_connect
#
#     if db_user.subtitle_type != 0:
#         return db_user.subtitle_type
#
#     subtitles_type: int = 0
#     db_chapter: DBLesson = DBLesson(SQL, db_lesson.ROWID)
#     while db_chapter.id_chapter != 0:
#         if db_chapter.db_rules.command("_subtitles_type") and db_chapter.db_rules.Format.isdigit():
#             subtitles_type = int(db_chapter.db_rules.Format)
#             break
#         db_chapter: DBLesson = DBLesson(SQL, db_chapter.id_chapter)
#     if db_chapter.id_chapter == 0 and db_chapter.db_rules.command("_subtitles_type") and \
#         db_chapter.db_rules.Format.isdigit():
#         subtitles_type = int(db_chapter.db_rules.Format)
#     return subtitles_type

def get_parent_game(db_user:DBUser, db_lesson: DBLesson):
    SQL = db_user.db_connect

    db_chapter: DBLesson = DBLesson(SQL, db_lesson.ROWID)
    while db_chapter.id_chapter != 0:
        db_chapter: DBLesson = DBLesson(SQL, db_chapter.id_chapter)
    db_game:DBGame = DBGame(SQL, db_user.ROWID, db_chapter.ROWID)
    return db_game

def get_path_lesson(db_user:DBUser, db_lesson: DBLesson, f_code: bool = True) -> str:
    SQL = db_user.db_connect

    db_chapter: DBLesson = DBLesson(SQL, db_lesson.ROWID)
    level = 0
    c = "<code>" if f_code else ""
    c_ = "</code>" if f_code else ""
    a_list:list = []
    while True:
        #s_num = f"{db_chapter.num}. " if db_user.adm_level == 3 or db_chapter.id_chapter != 0 else ""
        a_list.insert(0, f"{db_chapter.s_type}{c}{db_chapter.Name}{c_}")
        if db_chapter.id_chapter == 0:
            db_game: DBGame = DBGame(SQL, db_user.ROWID, db_chapter.ROWID)
            level = db_game.user_skill
            break
        db_chapter: DBLesson = DBLesson(SQL, db_chapter.id_chapter)

    path, s_space, cnt = "", "", len(a_list)
    for i in range(1, cnt):
        f = "" if not f_code else '🔸' if i%2 == 0 else '🔹'
        path += f"{s_space}{f}{a_list[i]}"
        if f_code:
            s_space = "   " + s_space
        if i < cnt - 1: path += "\n" if f_code else "\\"

    return level, path

def get_dialog_message_and_keyboard(db_user: DBUser):
    SQL = db_user.db_connect

    msg = "."
    keyboard = InlineKeyboardMarkup(row_width=8)

    # Диалог Списка Разделов db_user.mode=0
    if db_user.mode < 20 and (db_user.current_lesson_id == 0 or db_user.current_lesson_id == 10):
        #"🗂 - разделы\n📄 - уроки\n" \
        # "🔒 - раздел закрыт\n"
        #"<b>Описание:</b>\n" \
        msg = "💚 - пройден\n" \
              "🧡 - доступен для прохождения\n" \
              "❤️ - ещё не доступен\n"

        id_lesson = 0 if db_user.adm_level == 3 else 10 #10 - Раздел Дети

        db_chapter: DBLesson = DBLesson(SQL, id_lesson if id_lesson != 0 else -1)
        if id_lesson != 0:
            level, msg2 = get_path_lesson(db_user, db_chapter)

        list_chapters = db_chapter.get_list_lessons(id_lesson) #По умолчанию Дети
        for db_chapter in list_chapters:
            if db_user.adm_level == 3 or (not db_chapter.db_rules.command("_unvisible") and db_chapter.type != 0):
                s_ready = " \U0001F512" if db_chapter.db_rules.command("_not_ready") else ""
                if id_lesson != 0:
                    db_game: DBGame = DBGame(SQL, db_user.ROWID, id_lesson)
                    s_ready = "🔒" if db_chapter.db_rules.command("_not_ready") else \
                        "💚" if db_game.control_result == 2 else \
                        "❤️" if db_chapter.skill > level else "🧡"
                s_unvisible = " 🚫" if db_chapter.db_rules.command("_unvisible") else ""
                s_num = f"{db_chapter.num}. " if db_user.adm_level == 3 else ""
                keyboard.add(InlineKeyboardButton(text=f"{db_chapter.s_type} {s_num}{db_chapter.Name} {s_ready}{s_unvisible}",
                                                  callback_data=f"/get_lesson_{db_chapter.ROWID}"))

        if db_user.adm_level == 3:
            keyboard.add(InlineKeyboardButton(text="\U00002795\U0001F4D9 - Empty", callback_data=f"/lesson_new"))

    elif db_user.mode < 30:  # Диалог Урока db_user.mode=20

        id_lesson = db_user.current_lesson_id if db_user.current_lesson_id != 0 else -1
        db_lesson: DBLesson = DBLesson(SQL, id_lesson)

        level, msg = get_path_lesson(db_user, db_lesson)

        #db_game:DBGame = DBGame(SQL, db_user.ROWID, id_lesson)
        msg = f"🧡 <b>Level: {level}</b>\n{msg}\n<b>Lessons:</b>\n" if db_user.adm_level == 3 else f"{msg}\n<b>Уроки:</b>\n"

        if db_user.adm_level == 3:
            msg += f"<b>Caption:</b> {set_code_html(db_lesson.Caption)}\n"
            msg += f"\U0001F480 <b>Skill Lesson:</b> <code>{db_lesson.skill}</code>\n"
            msg += f"➕💀 <b>Skill test:</b> <code>{db_lesson.test_skill_decrement}</code>\n"
            msg += f"⏱ <b>Test time:</b> <code>{db_lesson.test_time}</code>\n"
            msg += f"📛<b>Test num errors:</b> <code>{db_lesson.test_num_errors}</code>"

        if db_lesson.type == 2:  # Урок как список слайдов
            if db_user.adm_level == 3:
                db_lesson.normalize_num_slides()
                db_slide: DBSlide
                list_slides = db_lesson.get_list_slides()
                for db_slide in list_slides:
                    s_ready = " \U0001F512" if db_slide.db_rules.command("_not_ready") or \
                          (db_user.adm_level != 3 and db_lesson.skill > level) else ""
                    s_is_test = " ⁉️" if db_slide.is_test == 1 else ""
                    s_unvisible = " 🚫" if db_slide.db_rules.command("_unvisible") else ""
                    keyboard.add(InlineKeyboardButton(text=f"\U0001F4F9 {db_slide.num}. {db_slide.Name}{s_ready}{s_unvisible}{s_is_test}",
                                                      callback_data=f"/get_slide_{db_slide.ROWID}"))

        else: #db_lesson.type == 0 or db_lesson.type == 1 - Урок-Каталог

            if db_user.adm_level == 3:
                db_lesson.normalize_num_lessons()

            list_chapters = db_lesson.get_list_lessons()
            db_lesson_: DBLesson
            for db_lesson_ in list_chapters:
                f_visible = not db_lesson_.db_rules.command("_unvisible")
                if db_user.adm_level == 3 or (f_visible and db_lesson_.type != 0):
                    db_game: DBGame = DBGame(SQL, db_user.ROWID, db_lesson_.ROWID)
                    s_ready = "🔒" if db_lesson_.db_rules.command("_not_ready") else \
                                "💚" if db_game.control_result == 2 else \
                                "❤️" if db_lesson_.skill > level else "🧡"
                    if db_user.adm_level == 3 and not f_visible: s_ready+="🚫"
                    s_num = f"{db_lesson_.num}. " if db_user.adm_level == 3 else ""
                    keyboard.add(InlineKeyboardButton(callback_data=f"/get_lesson_{db_lesson_.ROWID}",
                        text=f"{db_lesson_.s_type} {s_num}{db_lesson_.Name} {s_ready}"))

        if db_user.adm_level == 3:
            if db_lesson.type == 2:
                keyboard.add(InlineKeyboardButton(text="Name", callback_data="/change_lesson_name"),
                         InlineKeyboardButton(text="Caption", callback_data="/change_lesson_caption"),
                         InlineKeyboardButton(text="\U00002795\U0001F4F9", callback_data="/add_new_slide"))
            elif db_lesson.type == 1:
                keyboard.add(InlineKeyboardButton(text="Name", callback_data="/change_lesson_name"),
                             InlineKeyboardButton(text="Caption", callback_data="/change_lesson_caption"),
                             InlineKeyboardButton(text="\U00002795\U0001F4D7", callback_data="/lesson_new"))
            else:
                keyboard.add(InlineKeyboardButton(text="Name", callback_data="/change_lesson_name"),
                             InlineKeyboardButton(text="Caption", callback_data="/change_lesson_caption"),
                             InlineKeyboardButton(text="\U00002795\U0001F4D7", callback_data="/lesson_new"),
                             InlineKeyboardButton(text="\U00002795\U0001F4F9", callback_data="/add_new_slide"))

            keyboard.add(InlineKeyboardButton(text="\U0001F480", callback_data="/change_lesson_skill"),
                         InlineKeyboardButton(text="➕💀", callback_data="/ch_les_skill_decrement"),
                         InlineKeyboardButton(text="⏱", callback_data="/ch_les_test_time"),
                         InlineKeyboardButton(text="📛", callback_data="/ch_les_test_num_error"),
                         InlineKeyboardButton(text="\U0001F504\U0001F4D7", callback_data="/change_lesson_chapter"),
                         InlineKeyboardButton(text="\U0000274C", callback_data="/delete_lesson"))

            keyboard.add(InlineKeyboardButton(text="\U000025B6", callback_data=f"/play_lesson_{time_int()}"),
                InlineKeyboardButton(text="\U0001F5A8", callback_data=f"/set_lesson_copy_{db_lesson.ROWID}"),
                InlineKeyboardButton(text="\U00002B06", callback_data=f"/set_lesson_up_{db_lesson.ROWID}"),
                InlineKeyboardButton(text="\U00002B07", callback_data=f"/set_lesson_down_{db_lesson.ROWID}"),
                InlineKeyboardButton(text="🔢", callback_data=f"/normalize_lesson_{db_lesson.ROWID}"),
                InlineKeyboardButton(text="\U0001F519", callback_data=f"/get_lesson_{db_lesson.id_chapter}"))
        else:
            keyboard.add(InlineKeyboardButton(text="На главную", callback_data="/start_main"),
                         InlineKeyboardButton(text="\U0001F519", callback_data=f"/get_lesson_{db_lesson.id_chapter}"))


    elif db_user.mode < 40 and db_user.adm_level == 3:  # Диалог Слайда db_user.mode=30
        if db_user.current_lesson_id != 0 and db_user.current_video_id != 0:
            db_lesson: DBLesson = DBLesson(SQL, db_user.current_lesson_id)
            level, msg = get_path_lesson(db_user, db_lesson)

            db_slide: DBSlide = DBSlide(SQL, db_user.current_video_id)

            msg = f"{msg}\n<b>Slide Name:</b>\U0001F4F9{db_slide.num}. <code>{db_slide.Name}</code>\n"
            msg += f"<b>Caption:</b> {set_code_html(db_slide.Caption)}\n"
            msg += f"<b>Rules:</b> {set_code_html(db_slide.Rules)}\n"
            msg += f"<b>Words:</b> {set_code_html(db_slide.List_Words)}\n"
            msg += f"\U0001F4CB <b>Message:</b> {db_slide.Message}\n"
            msg += f"⁉️ <b>Is Test:</b> {'❌' if db_slide.is_test == 0 else '✅'}\n"

            list_variants = db_slide.get_list_variants()
            buttons: list = []
            btn: list = []
            row_width = int(db_slide.db_rules.Format) if db_slide.db_rules.command("_row_width") and \
                        db_slide.db_rules.Format.isdigit() else 1
            db_variant: DBVariant
            for db_variant in list_variants:

                Name: str = f"🎤{db_variant.Name}" if db_variant.db_rules.command("_voice") else db_variant.Name
                Name = f"[{Name}]" if db_variant.db_rules.command("_true_answer") else Name
                btn.append(InlineKeyboardButton(text=f"{Name}", callback_data=f"/get_variant_{db_variant.ROWID}"))
                if len(btn) == row_width:
                    buttons.append(btn.copy())
                    btn.clear()
            if len(btn) != 0:  buttons.append(btn.copy())

            buttons.append([InlineKeyboardButton(text="Name", callback_data="/change_slide_name"),
                    InlineKeyboardButton(text="Caption", callback_data="/change_slide_caption"),
                    InlineKeyboardButton(text="Rules", callback_data="/change_slide_rules"),
                    InlineKeyboardButton(text="Words", callback_data="/change_slide_words")])

            buttons.append([InlineKeyboardButton(text="⁉️", callback_data="/slide_is_test"),
                     InlineKeyboardButton(text="\U0001F4F9", callback_data="/change_slide_video"),
                     InlineKeyboardButton(text="\U00002795\U0001F44C", callback_data="/add_new_variant"),
                     InlineKeyboardButton(text="\U00002795\U00002795", callback_data="/add_templates_variant"),
                     InlineKeyboardButton(text="\U0001F4CB", callback_data="/change_slide_message"),
                     InlineKeyboardButton(text="\U0000274C", callback_data="/delete_slide")])

            buttons.append([InlineKeyboardButton(text="\U000025B6", callback_data=f"/play_slide_{time_int()}"),
                 InlineKeyboardButton(text="\U0001F5A8", callback_data=f"/set_slide_copy_{db_slide.ROWID}"),
                 InlineKeyboardButton(text="\U00002B06", callback_data=f"/set_slide_up_{db_slide.ROWID}"),
                 InlineKeyboardButton(text="\U00002B07", callback_data=f"/set_slide_down_{db_slide.ROWID}"),
                 InlineKeyboardButton(text="\U0001F519", callback_data=f"/get_lesson_{db_lesson.ROWID}")])

            keyboard = InlineKeyboardMarkup(buttons)

    elif db_user.mode < 50 and db_user.adm_level == 3:  # Диалог Варианта db_user.mode=40
        if db_user.current_lesson_id != 0 and db_user.current_video_id != 0 and db_user.current_variant_id != 0:
            db_lesson: DBLesson = DBLesson(SQL, db_user.current_lesson_id)
            db_slide: DBSlide = DBSlide(SQL, db_user.current_video_id)
            db_variant: DBVariant = DBVariant(SQL, db_user.current_variant_id)
            level, msg = get_path_lesson(db_user, db_lesson)
            msg = f"{msg}📹{db_slide.num}. {db_slide.Name}\\\n"
            msg += f"<b>Variant Name:</b> <code>{db_variant.Name}</code>\n"
            msg += f"<b>Caption:</b> {set_code_html(db_variant.Caption)}\n"
            db_slide_next: DBSlide = None if db_variant.id_next_slide == 0 else DBSlide(SQL, db_variant.id_next_slide)
            if db_variant.id_next_slide != 0 and db_slide_next.ROWID == 0:
                db_variant.save(id_next_slide=0)
            s_next = '-' if db_variant.id_next_slide == 0 else f"{db_slide_next.num}. {db_slide_next.Name}"
            msg += f"<b>Next Slide:</b> <code>{s_next}</code>\n"

            keyboard.add(InlineKeyboardButton(text="Name", callback_data="/change_variant_name"),
                 InlineKeyboardButton(text="Caption", callback_data="/change_variant_caption"),
                 InlineKeyboardButton(text="Next Slide", callback_data="/change_variant_next"))

            keyboard.add(InlineKeyboardButton(text="\U000025B6", callback_data="/play_slide"),
                InlineKeyboardButton(text="\U0000274C", callback_data="/delete_variant"),
                InlineKeyboardButton(text="\U0001F519", callback_data=f"/get_slide_{db_slide.ROWID}"))

    elif db_user.mode == 100 and SQL.get_admin_panel()>0:
        msg = "⚙️ <b>Admin Panel</b>"
        keyboard.add(InlineKeyboardButton(text="Продавцы", callback_data="/sellers_list"))
        keyboard.add(InlineKeyboardButton(text="Новая Эмиссия", callback_data="/promo_create"))
        keyboard.add(InlineKeyboardButton(text="Эмиссии Список", callback_data="/promo_list"))
        keyboard.add(InlineKeyboardButton(text="❌ Закрыть диалог", callback_data="/admin_panel_close"))

    elif db_user.mode == 110 and SQL.get_admin_panel()>0: #List Sellers
        msg = "<b>Продавцы</b>"
        db_seller: DBSeller = DBSeller(SQL)
        list_sellers = db_seller.get_list_sellers()
        for db_seller in list_sellers:
            f_block = "✅" if db_seller.block == 0 else "❌"
            keyboard.add(InlineKeyboardButton(text=f"{f_block} {db_seller.Name}", callback_data=f"/get_seller_{db_seller.ID}"))
        keyboard.add(InlineKeyboardButton(text="➕ Новый продавец", callback_data="/new_saller"))
        keyboard.add(InlineKeyboardButton(text="🔙 В Админ Панель", callback_data="/admin_panel"))
        keyboard.add(InlineKeyboardButton(text="❌ Закрыть диалог", callback_data="/admin_panel_close"))

    elif db_user.mode == 120 and SQL.get_admin_panel()>0 and db_user.current_variant_id != 0: #Selers Parametrs
        db_seller: DBSeller = DBSeller(SQL, db_user.current_variant_id)
        msg = "<b>Картачка Продавца</b>\n\n"
        msg += f"Name: {db_seller.Name}\n"
        msg += f"Caption: {db_seller.Caption}\n"
        msg += f"Статус: {'✅ Активно' if db_seller.block==0 else '❌ Заблокированно'}\n"
        keyboard.add(InlineKeyboardButton(text="Name", callback_data="/seller_name"),
                     InlineKeyboardButton(text="Caption", callback_data="/seller_caption"))
        keyboard.add(InlineKeyboardButton(text="🔐 Заблокировать" if db_seller.block ==0 else "🔓 Разблокировать", callback_data="/seller_block"),
                     InlineKeyboardButton(text="Delete", callback_data="/seller_delete"))
        keyboard.add(InlineKeyboardButton(text="К списку Продавцов", callback_data="/sellers_list"))
        keyboard.add(InlineKeyboardButton(text="❌ Закрыть диалог", callback_data="/admin_panel_close"))

    elif db_user.mode == 130 and SQL.get_admin_panel() > 0: #List Promo
        msg = "<b>Эмиссии</b>"
        db_promo: DBPromo = DBPromo(SQL)
        list_promo: list = db_promo.get_list_promo()
        keyboard = InlineKeyboardMarkup()
        for db_promo in list_promo:
            db_seller: DBSeller = DBSeller(SQL, db_promo.id_seller)
            f_block = "✅" if db_promo.block == 0 else "❌"
            keyboard.add(
                InlineKeyboardButton(text=f"{f_block}{db_seller.Name} [{db_promo.count_key}/{db_promo.count_lic}] {int_to_time_to_str(db_promo.cdate, 3)}",
                                     callback_data=f"/get_promo_{db_promo.ID}"))
        keyboard.add(InlineKeyboardButton(text="🔙 В Админ Панель", callback_data="/admin_panel"))
        keyboard.add(InlineKeyboardButton(text="❌ Закрыть диалог", callback_data="/admin_panel_close"))

    elif db_user.mode == 140 and SQL.get_admin_panel() > 0 and db_user.current_variant_id != 0: #Promo Parametrs
        db_promo: DBPromo = DBPromo(SQL, db_user.current_variant_id)

        db_seller: DBSeller = DBSeller(SQL, db_promo.id_seller)
        msg = "<b>Карточка Эмисии</b>\n\n"
        msg += f"Продавец: {db_seller.Name}\n"
        msg += f"Примечание: {db_promo.Caption}\n"
        msg += f"Время создания (по Москве): {int_to_time_to_str(db_promo.cdate, 3)}\n"
        msg += f"Количество ключей: {db_promo.count_key}\n"
        msg += f"Подписок на ключ: {db_promo.count_lic}\n"
        msg += f"Активироваций: {db_promo.count_activate_key}\n"
        msg += f"Статус: {'✅ Активно' if db_promo.block == 0 else '❌ Заблокированно'}\n"

        keyboard.add(InlineKeyboardButton(text="😎 Показать ключи", callback_data=f"/list_keys_promo_{db_promo.ID}"))
        keyboard.add(InlineKeyboardButton(text="🔐 Заблокировать" if db_promo.block ==0 else "🔓 Разблокировать", callback_data=f"/block_promo_{db_promo.ID}"))
        keyboard.add(InlineKeyboardButton(text="🔙 Эмиссии Список", callback_data="/promo_list"))
        keyboard.add(InlineKeyboardButton(text="❌ Закрыть диалог", callback_data="/admin_panel_close"))

    return msg, keyboard

def set_code_html(text: str)->str:
    a_text, text = text.strip().split('\n'), ""
    cnt = len(a_text)
    for i in range(cnt):
        text += f"<code>{a_text[i].strip()}</code>"
        if i < cnt - 1: text += "\n"
    return text

def PlaySlide(db_user: DBUser):
    SQL = db_user.db_connect
    old_msg_dialog_id = db_user.msg_dialog_id
    db_user.save_message(old_msg_dialog_id, "", 3)
    db_user.save_user(msg_dialog_id = 0)

    bot.delete_reply_msg(db_user)

    if db_user.last_video_id == 0:
        if db_user.current_lesson_id == 0:
            db_user.save_user(msg_dialog_id=old_msg_dialog_id)
            return
        db_slide: DBSlide = DBSlide(SQL)

        if not db_slide.get_from_num(1, db_user.current_lesson_id):
            db_lesson: DBLesson = DBLesson(SQL, db_user.current_lesson_id)
            msg_id=bot.send_message(chat_id=db_user.chat_id, text="\U00002757 Lesson is empty!", reply_markup=keyb_ok).message_id
            db_user.send_admin_message(f"\U00002757 PlaySlide() db_user.last_video_id=0 and db_lesson.Name='{db_lesson.Name}'\n" \
                                       f"Error: slides not found!")
            DeleteOldMessages(db_user)
            db_user.save_message(msg_id)
            db_user.save_user(msg_dialog_id=old_msg_dialog_id)
            return
        db_user.save_user(last_video_id=db_slide.ROWID)

    db_slide: DBSlide = DBSlide(SQL, db_user.last_video_id)

    if db_slide.ROWID == 0:
        msg_id = bot.send_message(chat_id=db_user.chat_id, text="\U00002757 Slide not found!", reply_markup=keyb_ok).message_id
        db_user.send_admin_message(f"\U00002757 PlaySlide()\nError: Slide id={db_user.last_video_id} not found!")
        DeleteOldMessages(db_user)
        db_user.save_message(msg_id)
        db_user.save_user(msg_dialog_id=old_msg_dialog_id)
        return

    if db_user.adm_level != 3 and db_slide.db_rules.command("_not_ready"):
        msg_id = bot.send_message(chat_id=db_user.chat_id, text="\U00002757 Slide not ready!",
                                  reply_markup=keyb_ok).message_id
        db_user.send_admin_message(f"\U00002757 PlaySlide()\nError: Slide id={db_slide.ROWID} not ready!")
        DeleteOldMessages(db_user)
        db_user.save_message(msg_id)
        db_user.save_user(msg_dialog_id=old_msg_dialog_id)
        return

    if db_slide.get_video_size() == 0:
        DeleteOldMessages(db_user)
        keboard = InlineKeyboardMarkup()
        if db_user.adm_level == 3:
            keboard.add(InlineKeyboardButton(text="Edit this Slide", callback_data=f"/get_slide_{db_slide.ROWID}"))
        else:
            keboard = keyb_ok
        msg_id = bot.send_message(chat_id=db_user.chat_id, text="\U00002757 Slide without Video!", reply_markup=keboard).message_id
        db_user.send_admin_message(f"\U00002757 PlaySlide()\nError: Slide id={db_slide.ROWID} Slide without Video!")
        db_user.save_message(msg_id)
        db_user.save_user(msg_dialog_id=old_msg_dialog_id)
        return

    db_game: DBGame = DBGame(SQL, db_user.ROWID, db_slide.id_lesson)
    db_game.save(id_cur_slide=db_slide.ROWID)

    message_begin_slide_id: int = 0
    if db_slide.Message != "-" and db_slide.Message != "":
        if db_user.mode != 5:  # Сообщение Слайда, которое показывается перед самим слайдом (не показывается на контрольной)
            link_preview = telebot.types.LinkPreviewOptions(is_disabled=db_slide.db_rules.command("_disable_link"))
            message_begin_slide_id = bot.send_message(chat_id=db_user.chat_id, text=db_slide.Message,
                                                      parse_mode='html', link_preview_options=link_preview).message_id
            sleep(5)
            # sec: int = int(len(db_slide.Message) / 30)
            # if sec > 5:
            #     msg_id = bot.send_message(chat_id=db_user.chat_id, text=f"<b>Loading Slide - remained {sec} sec...</b>",
            #                               parse_mode='html').message_id
            #     while True:
            #         sleep(10 if sec >= 10 else sec)
            #         # Проверяем не шалит ли наш Пользак с мемню во время ожидания
            #         if db_user.ldate != db_user.get_ldate():
            #             bot.delete_msg(db_user.chat_id, message_begin_slide_id)
            #             bot.delete_msg(db_user.chat_id, msg_id)
            #             return
            #         sec -= 10
            #         if sec <= 0: break
            #         bot.edit_message_text(chat_id=db_user.chat_id, message_id=msg_id,
            #                               text=f"<b>Loading Slide - remained {sec} sec...</b>", parse_mode='html')
            #
            #     bot.delete_msg(db_user.chat_id, msg_id)
            #
            # else: sleep(sec)

    keyboard, msg, a_voice_variants, text, translation_text, \
    translation_voice, subtitles_type, gender_parent = get_settings_PlaySlide(db_user, db_slide, 0, -1)

    bot.send_chat_action(chat_id=db_user.chat_id, action="upload_video")
    if db_slide.get_video_size() > 800: #Предупреждалка от больших видосов
        msg_action_id = bot.send_message(chat_id=db_user.chat_id, text="\U0001F3A5 <b>Loading video...</b>", parse_mode='html').message_id
        db_user.save_message(msg_action_id)

    Caption: str = msg if db_user.mode != 5 else "⁉️<b>Тестовая работа</b>⁉️" #Контрольная

    msg_id=bot.send_video(chat_id=db_user.chat_id, video=db_slide.get_video(), reply_markup=keyboard,
        caption=Caption, parse_mode="html").message_id
    db_user.save_user(msg_dialog_id=msg_id, last_word="")

    db_user.set_null_all_messages()
    if len(a_voice_variants)>0:
        for i  in range(0, len(a_voice_variants)):
            name = a_voice_variants[i]
            gender = ""
            if name[:2] == "M:": gender = "M"
            elif name[:2] == "F:": gender = "F"
            if gender != "": name = name[2:].strip()
            else: gender = "F"
            id_word = SQL.get_word_id(name, "EN")
            voice = SQL.get_voice_id(id_word, "EN", gender)
            if voice is not None:
                if db_user.adm_level ==3:
                    keyboard_voice = InlineKeyboardMarkup()
                    keyboard_voice.add(InlineKeyboardButton(text="ReSound",
                                                    callback_data=f"/set_voice_{id_word}_EN_{gender}"))
                    msg_voice_id = bot.send_audio(db_user.chat_id, voice, f"{a_voice_variants_l[i]} {name}",
                                                reply_markup=keyboard_voice).message_id
                else:
                    msg_voice_id = bot.send_audio(db_user.chat_id, voice, a_voice_variants_l[i]).message_id
                db_user.save_message(msg_voice_id, name, 3)
    sleep(1)
    DeleteOldMessages(db_user, True, 3)

    msg_end_slideid=0
    if db_slide.db_rules.command("_end_slide"):
        if db_slide.db_rules.Text != "":
            msg_end_slideid=bot.send_message(chat_id=db_user.chat_id, text=db_slide.db_rules.Text, parse_mode='html').message_id
            sleep(1)

    #DeleteOldMessages(db_user, True, 3)
    if msg_end_slideid != 0: #Сообщения после _end_slide Слайда
        db_user.save_message(msg_end_slideid)

    # if old_msg_dialog_id != 0: #Старый Слайд или Меню
    #     sleep(1)
    #     bot.delete_msg(db_user.chat_id, old_msg_dialog_id)

    if db_slide.db_rules.command("_message_del_after") and message_begin_slide_id !=0:
        db_user.save_message(message_begin_slide_id, "msg", 3)

def PrintError(err: str): print(f"{datetime.datetime.now().strftime('%Y.%m.%d %H:%M')} ERROR: {err}")

def refresh_dialog(db_user: DBUser)->bool:

    bot.delete_reply_msg(db_user)
    msg, keyboard = get_dialog_message_and_keyboard(db_user)

    try:
        if db_user.msg_dialog_id == 0:
            raise RuntimeError("None")

        bot.edit_message_text(chat_id=db_user.chat_id, message_id=db_user.msg_dialog_id,
                                 text=msg, parse_mode="html", reply_markup=keyboard)
    except Exception as err:
        sleep(1)
        if err.__str__().find("specified new message content and reply markup are exactly") !=-1 :
            PrintError("specified new message content and reply markup are exactly")
            return DeleteOldMessages(db_user, True)
        bot.delete_msg_dialog(db_user)

        try:
            msg_id = bot.send_message(chat_id=db_user.chat_id,
                                      text=msg, reply_markup=keyboard, parse_mode="html").message_id
            db_user.save_user(msg_dialog_id=msg_id)
            return DeleteOldMessages(db_user, True)

        except Exception as err:
            text = err.__str__()
            if len(text) > 256: text = text[:256]
            bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"Error refresh_dialog: {text}")
            PrintError(f"Error refresh_dialog: {err}")
            return DeleteOldMessages(db_user, False)

        #db_user.save_user(msg_dialog_id=msg_id)

        if err.__str__().find("Error code: 400. Description: Bad Request: message caption is too long") != -1:
            PrintError("Caption is too long")
        elif err.__str__() != "None":
            PrintError(f"Error <def refresh_dialog(db_user: DBUser):> {err}")
        else:
            return DeleteOldMessages(db_user, True)

        return DeleteOldMessages(db_user, False)

    return DeleteOldMessages(db_user, True)

def DeleteOldMessages(db_user: DBUser, f: bool = True, except_: int = -1) -> bool:
    list_messages = db_user.get_list_messages()

    if len(list_messages)>0:
        db_user.delete_all_messages(except_) # Удаление из базы SQL

        for message in list_messages: #Удаление из телеги
            if (message[1] != except_):
                bot.delete_msg(db_user.chat_id, message[0])
                sleep(1)
    return f

def print_exception(exc: str):
    global datetime_last_error
    d=datetime.datetime.now()
    print(f"{d.strftime('%Y.%m.%d %H:%M')} {exc}")
    datetime_last_error = d.timestamp()

print("BOT English started - Ok")
datetime_last_error=0
while True:

    if int(datetime.datetime.now().timestamp() - datetime_last_error) < 5: continue

    try: bot.polling(none_stop=True, interval = 1)
    except requests.exceptions.ConnectTimeout:
        print_exception("Exception: requests.exceptions.ConnectTimeout")
    except requests.exceptions.ConnectionError:
        print_exception("Exception: requests.exceptions.ConnectionError")
    except requests.exceptions.ReadTimeout:
        print_exception("Exception: requests.exceptions.ReadTimeout")
    except KeyboardInterrupt:
        break
    except Exception as err:
        print(err.__str__())