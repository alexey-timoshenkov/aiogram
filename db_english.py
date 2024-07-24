#! /usr/bin/env python
# -*- coding: utf-8 -*-

import sqlite3
import datetime
import json
from hashlib import md5
from time import sleep
from telebot.types import InlineKeyboardButton

import requests

def time_int(timedelta: datetime.timedelta = None)->int:
    if timedelta == None:
        timedelta=datetime.timedelta(hours=0)
    d=datetime.datetime.utcnow()+timedelta
    return int(d.timestamp())
def current_time_str(timedelta: datetime.timedelta = None)->str:
    if timedelta == None:
        timedelta=datetime.timedelta(hours=0)
    d=datetime.datetime.utcnow()+timedelta
    return d.strftime('%Y.%m.%d %H:%M')

def current_time_str_sec(timedelta: datetime.timedelta = None)->str:
    if timedelta == None:
        timedelta=datetime.timedelta(hours=0)
    d=datetime.datetime.utcnow()+timedelta
    return d.strftime('%Y.%m.%d %H:%M:%S')

def str_to_time_to_int(str_time: str)->int:
    return int(datetime.datetime.strptime(str_time, '%Y.%m.%d %H:%M').timestamp())
def int_to_time_to_str(int_time: int, hours: int =0)->str:
    timedelta = datetime.timedelta(hours=hours)
    return (datetime.datetime.fromtimestamp(int_time)+timedelta).strftime('%Y.%m.%d %H:%M')
def int_to_time_to_str_sec(int_time: int)->str:
    return datetime.datetime.fromtimestamp(int_time).strftime('%Y.%m.%d %H:%M:%S')
def int_to_time(int_time: int, timedelta: datetime.timedelta = None) -> datetime.datetime:
    if timedelta == None:
        timedelta = datetime.timedelta(hours=0)
    return datetime.datetime.fromtimestamp(int_time)+timedelta


#Создание словаря ListWords для переводчика и для keyboard Слайда
# {
#     "list_line":
#         [
#             {"text": text, "gender": gender, "list_words"[word1, word2, ...], "keyboard_line": InlineKeyboardButton, "keyboard_words": []},
#             {"text": text, "gender": gender, "list_words"[word1, word2, ...], "keyboard_line": InlineKeyboardButton, "keyboard_words": []}
#             ...
#         ]
# }
def get_dict_words(text: str, id_slide: int) -> dict:
    dict_words = { "list_line": [] }
    if text != "":
        list_line_words = text.strip().split('\n')

        for i in range(0, len(list_line_words)):
            line_words = list_line_words[i]
            dict_words["list_line"].append(get_dict_line_words(line_words, i, id_slide))

    return dict_words

def get_dict_line_words(text: str, index: int, id_slide: int) -> dict:
    list_words = text.strip().split(' ')
    cnt = len(list_words)
    GENDER: str = ""
    list_new_words = []
    for i in range(0, cnt):
        list_words[0] = list_words[0].strip()

    if cnt > 0:
        if list_words[0] == "M:":
            GENDER = "M"
        elif list_words[0] == "F:":
            GENDER = "F"

        if GENDER != "":
            list_words.pop(0)
            cnt -= 1
            text = text[2:].strip()
        else:
            GENDER = "F"
    i = 0
    while i < cnt:
        if i < (cnt - 1) and \
           (list_words[i].lower() == "a" or list_words[i].lower() == "the" or list_words[i].lower() == "to"):
            word = f"{list_words[i]} {list_words[i + 1]}"
            list_new_words.append(word)
            i = i + 1
        else:
            list_new_words.append(list_words[i])
        i = i + 1

    keyboard_words = []
    for i in range(0, len(list_new_words)):
        keyboard_words.append(InlineKeyboardButton(text=list_new_words[i], callback_data=f"/select_word_{id_slide}_{index}_{i}").to_json())

    keyboard_line = InlineKeyboardButton(text=text, callback_data=f"/select_word_{id_slide}_{index}").to_json()
    return {"text": text,
            "gender": GENDER,
            "list_words": list_new_words,
            "keyboard_line": keyboard_line,
            "keyboard_words": keyboard_words}

class DBRules:
    Rules: str #= None
    Dict: dict #= None #{"DEFAULT": {"FORMAT": "", "TEXT": ""}}
    current_node: str #= None #= "DEFAULT"
    Text: str #= ""
    Format: str #= ""

    def __init__(self, Rules: str):
        self.Rules = Rules
        #self.Dict.clear()
        self.Dict = {"DEFAULT": {"FORMAT": "", "TEXT": ""}}
        self.current_node = "DEFAULT"
        l_lines_text = self.Rules.split("\n") #Разделяем тексту на строки

        for line in l_lines_text:
            if line.strip()[:1] == "_": #Command
                line = line.strip()
                l_line_format = line.split(" ")
                self.current_node = l_line_format[0] #Command
                self.Dict[self.current_node] = {"FORMAT": "", "TEXT": ""}
                for i in range(1, len(l_line_format)):
                    self.Dict[self.current_node]["FORMAT"] += l_line_format[i]
            else:
                self.Dict[self.current_node]["TEXT"]+=f"{line}\n"

        for i in self.Dict:
            self.Dict[i]["TEXT"] = self.Dict[i]["TEXT"].strip()

        self.command("DEFAULT")

    def command(self, command: str) -> bool:
        f: bool = (command in self.Dict)
        self.current_node = command if f else "DEFAULT"
        self.Text = self.Dict[self.current_node]["TEXT"]
        self.Format = self.Dict[self.current_node]["FORMAT"]
        return f

class SQLiteClient:

    filepath = ""
    token = ""
    id_token_bot: int = 0
    admin_chat_id: int = 0
    conn: sqlite3.Connection = None
    SQL_SAVE_MESSAGE = "INSERT INTO Messages(id_user, id_message, cdate, Message, type, rowid_user) VALUES(?, ?, ?, ?, ?, ?);"

    def __init__(self, filepath: str, token: str, admin_chat_id: int, f_int: bool = False):
        self.filepath = filepath
        self.token=token
        self.admin_chat_id=admin_chat_id

        self.connect()

        list_tuple = self.sql_select("SELECT ROWID FROM Tokens_Bot WHERE token=?;", (token,))
        if len(list_tuple) > 0:
            self.id_token_bot = list_tuple[0][0]
        else:
            self.id_token_bot = self.sql_execute("INSERT INTO Tokens_Bot(token) VALUES(?);", (token,))

        if f_int == False: return

        self.sql_execute("UPDATE VERSION SET QUEUE=0;")
        self.sql_execute("UPDATE VERSION SET ACCESS=0;")

        if len(self.sql_select("SELECT name FROM sqlite_master WHERE type='table' AND name='VERSION';"))==0:
            # - создаём базу с нуля
            self.sql_execute("""CREATE TABLE IF NOT EXISTS VERSION(
                VER int, QUEUE INT DEFAULT 0, ACCESS INT DEFAULT 0, ADMIN_PANEL INT DEFAULT 0, ADMIN_MD5 TXT)""")
            self.sql_execute(f"INSERT INTO VERSION(VER) VALUES(1)")

            self.sql_execute("""CREATE TABLE IF NOT EXISTS Users(
                    chat_id INT PRIMARY KEY, Name TXT, UserName TXT DEFAULT '', 
                    mode int, adm_level INT, cdate INT, ldate INT,
                    current_lesson_id INT, current_video_id INT,
                    msg_dialog_id INT, msg_reply_id INT, last_video_id INT, current_variant_id INT,
                    keyboard TXT DEFAULT '', last_word TXT DEFAULT '', skill INT DEFAULT 0, subtitle_type INT DEFAULT 0,
                    id_token_bot INT DEFAULT 1, license_date INT DEFAULT 0);""")

            self.sql_execute("""CREATE TABLE IF NOT EXISTS Lessons(
                num INT, Name TXT, Caption TXT, skill INT DEFAULT 0, id_chapter INT DEFAULT 0, type INT DEFAULT 0,
                test_time INT DEFAULT 0, test_num_errors INT DEFAULT 0, test_skill_decrement INT DEFAULT 1);""")

            self.sql_execute("""CREATE TABLE IF NOT EXISTS Slides(
                id_lesson INT, num INT, Name TXT, Caption TXT, List_Words TXT,
                Video BLOB, Video_Size INT, Rules TXT DEFAULT '', Message TXT DEFAULT '',
                is_test INT DEFAULT 0, keyboard_dict TXT DEFAULT '');""")

            self.sql_execute("CREATE TABLE IF NOT EXISTS Variants(id_slide INT, Name TXT, Caption TXT, id_next_slide INT);")
            self.sql_execute("""CREATE TABLE IF NOT EXISTS Messages(id_user INT, id_message INT, cdate INT, Message TXT,"
                             "type INT, rowid_user INT DEFAULT 0);""") #Таблица сообщений телеграм пользователей
            self.sql_execute("""CREATE TABLE IF NOT EXISTS Dictionary(
                EN TXT DEFAULT '', EN_VOICE_M BLOB, EN_VOICE_F BLOB,
                RU TXT DEFAULT '', RU_VOICE_M BLOB, RU_VOICE_F BLOB, RU_FIX INT DEFAULT 0);""")
            self.sql_execute("""CREATE TABLE IF NOT EXISTS Games(
                            id_user INT, id_lesson INT, id_cur_slide INT, user_skill INT, cdate INT, ldate INT,
                            control_cdate INT, control_edate INT, control_result INT, control_time INT, 
                            control_num_errors INT, control_list_id_slides TXT, id_variant_click INT DEFAULT 0);""")
            self.sql_execute("CREATE TABLE IF NOT EXISTS Messages_Group(id_group INT, id_message INT);")
            self.sql_execute("CREATE TABLE IF NOT EXISTS Tokens_Bot(token TXT);")

            self.sql_execute("""CREATE TABLE IF NOT EXISTS Sellers(ID INTEGER PRIMARY KEY AUTOINCREMENT,
                            cdate INT, Name TXT, Caption TXT, S_TEXT TXT, I_INT INT, Block INT DEFAULT 0);""")
            self.sql_execute("""CREATE TABLE IF NOT EXISTS Promos(ID INTEGER PRIMARY KEY AUTOINCREMENT,
                            cdate INT, id_creater INT, Caption TXT, count_lic INT, license_period INT, edate INT,
                            id_seller INT, Block INT DEFAULT 0);""")
            self.sql_execute("""CREATE TABLE IF NOT EXISTS Keys(ID INTEGER PRIMARY KEY AUTOINCREMENT,
                            S_Number TEXT UNIQUE, id_promo INT);""")
            self.sql_execute("""CREATE TABLE IF NOT EXISTS User_Active_Key(ID INTEGER PRIMARY KEY AUTOINCREMENT,
                            id_user INT, id_key INT, cdate INT, Caption TXT);""")

            self.sql_execute("""CREATE TABLE IF NOT EXISTS Invites(ID INTEGER PRIMARY KEY AUTOINCREMENT,
                                        cdate INT, S_Number TXT UNIQUE, chat_id INT);""")
            self.sql_execute("""CREATE TABLE IF NOT EXISTS User_Invite(ID INTEGER PRIMARY KEY AUTOINCREMENT,
                                                    cdate INT, id_user INT, id_invite INT, chat_id INT);""")
            self.sql_execute("""CREATE TABLE IF NOT EXISTS Subscription_Telegram(ID INTEGER PRIMARY KEY AUTOINCREMENT,
                                                                cdate INT, id_user INT, amount INT, caption TXT);""")
        else:
            new_ver = 44
            cursor = self.sql_select("SELECT * FROM VERSION""")

            if cursor and cursor[0][0] < new_ver:

                version = cursor[0][0]

                if version < 25:
                    self.sql_execute("DROP TABLE Users_Queue;")

                    self.sql_execute("ALTER TABLE Users RENAME TO _Users;")

                    self.sql_execute("""CREATE TABLE IF NOT EXISTS Users(
                                        chat_id INT PRIMARY KEY, Name TXT, UserName TXT DEFAULT '', 
                                        mode int, adm_level INT, cdate INT, ldate INT,
                                        current_lesson_id INT, current_video_id INT,
                                        msg_dialog_id INT, msg_reply_id INT, last_video_id INT, current_variant_id INT,
                                        keyboard TXT DEFAULT '', last_word TXT DEFAULT '', skill INT DEFAULT 0);""")
                    self.sql_execute("""INSERT INTO Users SELECT chat_id, Name, UserName, 
                                            mode, adm_level, cdate, ldate,
                                            current_lesson_id, current_video_id,
                                            msg_dialog_id, msg_reply_id, last_video_id, current_variant_id,
                                            keyboard, last_word, skill FROM _Users;""")
                    self.sql_execute("""DROP TABLE _Users;""")

                    version = 25

                if version < 26:
                    self.sql_execute("ALTER TABLE Lessons ADD COLUMN test_skill_decrement INT DEFAULT 1;")
                    version = 26
                if version < 27:
                    self.sql_execute("ALTER TABLE Dictionary ADD COLUMN RU_VOICE BLOB;")
                    self.sql_execute("ALTER TABLE Dictionary ADD COLUMN EN_VOICE BLOB;")
                    version = 27
                if version < 28:
                    self.sql_execute("ALTER TABLE Users ADD COLUMN subtitle_type INT DEFAULT 0;")
                    version = 28

                if version < 30:
                    self.sql_execute("DELETE FROM Dictionary;")
                    version = 30

                if version < 31:
                    self.sql_execute("ALTER TABLE Dictionary RENAME TO _Dictionary;")
                    self.sql_execute("""CREATE TABLE IF NOT EXISTS Dictionary(
                                    EN TXT DEFAULT '', EN_VOICE_M BLOB, EN_VOICE_F BLOB,
                                    RU TXT DEFAULT '', RU_VOICE_M BLOB, RU_VOICE_F BLOB);""")
                    self.sql_execute("""INSERT INTO Dictionary(EN, EN_VOICE_F, RU, RU_VOICE_F) SELECT 
                                    EN, EN_VOICE, RU, RU_VOICE FROM _Dictionary;""")
                    self.sql_execute("""DROP TABLE _Dictionary;""")

                    version = 31

                if version < 33:
                    self.sql_execute("CREATE TABLE IF NOT EXISTS Messages_Group(id_group INT, id_message INT);")
                    version = 33

                if version < 34:
                    self.sql_execute("ALTER TABLE Dictionary ADD COLUMN RU_FIX INT DEFAULT 0;")
                    version = 34

                if version < 35:
                    self.sql_execute("ALTER TABLE Users ADD COLUMN id_token_bot INT DEFAULT 1;")
                    self.sql_execute("CREATE TABLE IF NOT EXISTS Tokens_Bot(token TXT);")
                    rowid = self.sql_execute("INSERT INTO Tokens_Bot(token) VALUES(?);", ("6468182008:AAHNx6GZT9PhTsI3Mc9Dsm4wc6qCl5HuyPU", ))
                    self.sql_execute(f"UPDATE Users SET id_token_bot=?", (rowid, ))
                    version = 35

                if version < 36:
                     self.sql_execute("ALTER TABLE Users RENAME TO _Users;")
                     self.sql_execute("""CREATE TABLE IF NOT EXISTS Users(
                        chat_id INT, Name TXT, UserName TXT DEFAULT '',
                        mode int, adm_level INT, cdate INT, ldate INT,
                        current_lesson_id INT, current_video_id INT,
                        msg_dialog_id INT, msg_reply_id INT, last_video_id INT, current_variant_id INT,
                        keyboard TXT DEFAULT '', last_word TXT DEFAULT '', skill INT DEFAULT 0, subtitle_type INT DEFAULT 0,
                        id_token_bot INT DEFAULT 1);""")
                     self.sql_execute("""INSERT INTO Users SELECT
                        chat_id, Name, UserName, 
                        mode, adm_level, cdate, ldate,
                        current_lesson_id, current_video_id,
                        msg_dialog_id, msg_reply_id, last_video_id, current_variant_id,
                        keyboard, last_word, skill, subtitle_type, id_token_bot FROM _Users;""")
                     self.sql_execute("""DROP TABLE _Users;""")
                     version = 36

                if version < 38:
                    list_tuple = self.sql_select("SELECT ROWID, id_user FROM Games;")
                    for l in list_tuple:
                        rowid = int(l[0])
                        id_user = int(l[1])
                        list_tuple_2 = self.sql_select("SELECT ROWID FROM Users WHERE chat_id=?;", (id_user, ))
                        if len(list_tuple_2)>0:
                            row_id_user = list_tuple_2[0][0]
                            self.sql_execute("UPDATE Games SET id_user=? WHERE ROWID=?;", (row_id_user, rowid))
                    version = 38

                if version < 39:
                    self.sql_execute("ALTER TABLE Messages ADD COLUMN rowid_user INT DEFAULT 0;")

                    list_tuple = self.sql_select("SELECT ROWID, id_user FROM Messages;")
                    for l in list_tuple:
                        rowid = int(l[0])
                        id_user = int(l[1])
                        list_tuple_2 = self.sql_select("SELECT ROWID FROM Users WHERE chat_id=?;", (id_user,))
                        if len(list_tuple_2) > 0:
                            row_id_user = list_tuple_2[0][0]
                            self.sql_execute("UPDATE Messages SET rowid_user=? WHERE ROWID=?;", (row_id_user, rowid))
                    version = 39

                if version < 40:
                    self.sql_execute("ALTER TABLE Users ADD COLUMN license_date INT DEFAULT 0;")
                    self.sql_execute("ALTER TABLE Users ADD COLUMN bonuses INT DEFAULT 0;")
                    self.sql_execute("ALTER TABLE VERSION ADD COLUMN ADMIN_PANEL INT DEFAULT 0;")
                    self.sql_execute("ALTER TABLE VERSION ADD COLUMN ADMIN_MD5 TXT;")
                    self.sql_execute("""CREATE TABLE IF NOT EXISTS Sellers(ID INTEGER PRIMARY KEY AUTOINCREMENT,
                                    cdate INT, Name TXT, Caption TXT, S_TEXT TXT, I_INT INT);""")
                    self.sql_execute(f"UPDATE VERSION SET ADMIN_MD5='F10672E9344BA0C2DB69C66A0E568FF0'")
                    version = 40

                if version < 41:
                    self.sql_execute("""CREATE TABLE IF NOT EXISTS Promos(ID INTEGER PRIMARY KEY AUTOINCREMENT,
                        cdate INT, id_creater INT, Caption TXT, count_lic INT, license_period INT, edate INT, id_seller INT);""")
                    self.sql_execute("""CREATE TABLE IF NOT EXISTS Keys(ID INTEGER PRIMARY KEY AUTOINCREMENT,
                                    S_Number TEXT UNIQUE, id_promo INT);""")
                    self.sql_execute("""CREATE TABLE IF NOT EXISTS User_Active_Key(ID INTEGER PRIMARY KEY AUTOINCREMENT,
                                    id_user INT, id_key INT, cdate INT, Caption TXT);""")
                    version = 41

                if version < 42:
                    self.sql_execute("ALTER TABLE Sellers ADD COLUMN Block INT DEFAULT 0;")
                    self.sql_execute("ALTER TABLE Promos ADD COLUMN Block INT DEFAULT 0;")
                    version = 42

                if version < 43:
                    self.sql_execute("""CREATE TABLE IF NOT EXISTS Invites(ID INTEGER PRIMARY KEY AUTOINCREMENT,
                                                            cdate INT, S_Number TXT UNIQUE, chat_id INT);""")
                    self.sql_execute("""CREATE TABLE IF NOT EXISTS User_Invite(ID INTEGER PRIMARY KEY AUTOINCREMENT,
                                                            cdate INT, id_user INT, id_invite INT, chat_id);""")
                    version = 43

                if version < 44:
                    self.sql_execute("""CREATE TABLE IF NOT EXISTS Subscription_Telegram(ID INTEGER PRIMARY KEY AUTOINCREMENT,
                                        cdate INT, id_user INT, amount INT, caption TXT);""")
                    version = 44

                self.sql_execute(f"UPDATE VERSION SET VER=?", (new_ver, ))

    def set_subscription_telegram(self, id_user: int, amount: int, caption: str):
        self.sql_execute("INSERT INTO Subscription_Telegram(cdate, id_user, amount, caption) VALUES(?, ?, ?, ?);",
                         (time_int(), id_user, amount, caption))

    def get_admin_pass_md5(self):
        cursor = self.sql_select("SELECT ADMIN_MD5 FROM VERSION")
        return cursor[0][0]

    def get_admin_panel(self):
        cursor = self.sql_select("SELECT ADMIN_PANEL FROM VERSION")
        return cursor[0][0]

    def set_admin_panel(self, val: int):
        cursor = self.sql_select("UPDATE VERSION SET ADMIN_PANEL=?", (val,))

    def close(self):
        if self.conn is not None and isinstance(self.conn, sqlite3.Connection):
            self.conn.close()
        self.conn = None

    def save_message_group(self, id_group: int, id_message: int):
        self.sql_execute("INSERT INTO Messages_Group(id_group, id_message) VALUES(?, ?);", (id_group, id_message))

    def get_messages_group(self, id_group: int) -> list:
        a_messages_group_id =[]
        list_tuple = self.sql_select("SELECT id_message FROM Messages_Group WHERE id_group=?;", (id_group, ))
        for l in list_tuple:
            a_messages_group_id.append(l[0])
        return a_messages_group_id

    def delete_message_group(self, id_group: int):
        self.sql_execute("DELETE FROM Messages_Group WHERE id_group=?;", (id_group, ))

    def is_voice_row(self, ROWID: int, LANG: str, GENDER: str)->bool:
        list_tuple = self.sql_select("SELECT ROWID FROM Dictionary WHERE ROWID=? AND %s_VOICE_%s IS NOT NULL" % (LANG, GENDER), (ROWID, ))
        return 1 if len(list_tuple)>0 else 0

    def get_word_from_row(self, ROWID: int, LANG: str):
        list_tuple = self.sql_select("SELECT %s FROM Dictionary WHERE ROWID=?" % LANG, (ROWID, ))
        return list_tuple[0][0] if len(list_tuple)>0 else None

    def get_word_id(self, text: str, LANG: str):
        list_tuple = self.sql_select("SELECT ROWID FROM Dictionary WHERE %s=?" % LANG, (text, ))
        return list_tuple[0][0] if len(list_tuple)>0 else None

    def get_fix_word(self, rowid: int, LANG: str):
        list_tuple: list[tuple]
        try: list_tuple = self.sql_select("SELECT %s_FIX FROM Dictionary WHERE ROWID=?;" % LANG, (rowid, ))
        except: pass

        return list_tuple[0][0] if len(list_tuple)>0 else 0

    def send_massage_admin_chat(self, msg: str, if_save_msg: bool = False) -> int:
        message_id: int = 0
        try:
            res: requests.Response = requests.post(f"https://api.telegram.org/bot{self.token}/sendMessage?chat_id={self.admin_chat_id}&text={msg}&parse_mode=html")
            js: dict = res.json()
            ok: str = js.get('ok')
            if ok is not None and ok == True:
                result: dict = js.get('result')
                if result is not None:
                    message_id =result.get('message_id')
                    if message_id is None:
                        message_id = 0
        except: pass
        print(f"{current_time_str()} {msg}")

        if if_save_msg and message_id != 0:
            users = self.sql_select("SELECT ROWID FROM Users WHERE chat_id=? and id_token_bot=?;",
                                               (self.admin_chat_id, self.id_token_bot))
            if len(users)>0:
                admmin_rowid = users[0][0]
                self.sql_execute(self.SQL_SAVE_MESSAGE,
                                (self.admin_chat_id, message_id, time_int(), "", 0, admmin_rowid))
        return message_id

    def connect(self):
        try:
            if self.conn is None:
                self.conn: sqlite3.connect = sqlite3.connect(self.filepath, check_same_thread=False)
                if self.conn is None:
                    raise ConnectionError("you need to create connection to databese!")
        except Exception as err:
            self.send_massage_admin_chat("ERROR connect() "+err.__str__(), False)
            self.conn = None
            return False
        return True

    def sql_execute(self, query: str, params=(), f_print: bool=True)->int:
        if self.conn is None and self.connect() == False: return -1
        try:
            self.conn.isolation_level = None
            cursor = self.conn.cursor()
            cursor.execute(query, params)
            self.conn.commit()
        except Exception as err:
            if f_print:
                self.send_massage_admin_chat("ERROR sql_execute() "+err.__str__(), False)
                print(err)
                print(query)
            return -1
        return cursor.lastrowid

    def sql_select(self, query: str, params=(), f_print: bool=True):
        if self.conn is None and self.connect() == False: return -1
        try:
            cursor = self.conn.cursor()
            cursor.execute(query, params)
        except Exception as err:
            if f_print:
                self.send_massage_admin_chat("ERROR sql_select() "+err.__str__(), False)
                print(err)
                print(query)
            return []
        return cursor.fetchall()

    SQL_GET_WORD = "SELECT ROWID FROM Dictionary WHERE %s=?;"
    SQL_GET_VOICE = "SELECT %s_VOICE_%s FROM Dictionary WHERE ROWID=?;"
    SQL_SET_VOICE = "UPDATE Dictionary SET %s_VOICE_%s=? WHERE ROWID=?;"
    SQL_INSERT_WORD = "INSERT INTO Dictionary(%s, %s_VOICE_%s, %s_VOICE_%s, %s) VALUES(?, ?, ?, ?)"
    SQL_UPDATE_WORD = "UPDATE Dictionary SET %s=?, %s_VOICE_%s=?, %s_VOICE_%s=?, %s_FIX=? WHERE %s=?"
    SQL_SAVE_COLUMN_WORD = "ALTER TABLE Dictionary ADD COLUMN %s TXT DEFAULT '';"
    SQL_SAVE_COLUMN_WORD_2 = "ALTER TABLE Dictionary ADD COLUMN %s_VOICE_M BLOB;"
    SQL_SAVE_COLUMN_WORD_3 = "ALTER TABLE Dictionary ADD COLUMN %s_VOICE_F BLOB;"
    SQL_SAVE_COLUMN_WORD_4 = "ALTER TABLE Dictionary ADD COLUMN %s_FIX INT;"

    def save_word_to_dict(self, word: str, FROM: str, VOICE_FROM: bytes,
                          translate: str, TO: str, VOICE_TO: bytes, GENDER: str = "F", fix: int = 0):

        id_word = self.get_word_id(word, FROM) #Слово уже есть в словаре
        f_fix = self.get_fix_word(id_word, TO) if id_word is not None else 0
        if VOICE_FROM is None and id_word is not None:
            VOICE_FROM = self.get_voice_id(id_word, FROM, GENDER)
        if VOICE_TO is None and id_word is not None:
            VOICE_TO = self.get_voice_id(id_word, TO, GENDER)
        try:
            #"UPDATE Dictionary SET %s=?, %s_VOICE_%s=?, %s_VOICE_%s=?, %s_FIX=? WHERE %s=?"
            if id_word is not None:
                if fix == 0 and f_fix == 1:
                    translate = self.get_word_from_row(id_word, TO)
                    VOICE_TO = self.get_voice_id(id_word, TO, GENDER)
                    fix = 1
                SQL = self.SQL_UPDATE_WORD % (TO, TO, GENDER, FROM, GENDER, TO, FROM)
                self.sql_execute(SQL, (translate, VOICE_TO, VOICE_FROM, fix, word))
            #"INSERT INTO Dictionary(%s, %s_VOICE_%s, %s_VOICE_%s, %s) VALUES(?, ?, ?, ?)"
            else: self.sql_execute(
                self.SQL_INSERT_WORD % (TO, TO, GENDER, FROM, GENDER, FROM), (translate, VOICE_TO, VOICE_FROM, word))
        except:
            self.sql_execute(self.SQL_SAVE_COLUMN_WORD % TO)
            self.sql_execute(self.SQL_SAVE_COLUMN_WORD_2 % TO)
            self.sql_execute(self.SQL_SAVE_COLUMN_WORD_3 % TO)
            self.sql_execute(self.SQL_SAVE_COLUMN_WORD_4 % TO)
            if id_word is not None:
                self.sql_execute(self.SQL_UPDATE_WORD % (TO, TO, GENDER, FROM, GENDER, FROM),
                    (translate, VOICE_TO, VOICE_FROM, fix, word))
            else:
                self.sql_execute(self.SQL_INSERT_WORD % (TO, TO, GENDER, FROM, GENDER, FROM),
                    (translate, VOICE_TO, VOICE_FROM, word))

    def get_voice_id(self, rowid: int, LANG: str, GENDER: str = "F"):
        list_tuple: list[tuple] = None
        try:
            list_tuple = self.sql_select(self.SQL_GET_VOICE % (LANG, GENDER), (rowid, ))
        except:
            pass

        return list_tuple[0][0] if list_tuple is not None and len(list_tuple)>0 else None

    def set_voice_id(self, rowid: int, voice: bytes, LANG: str, GENDER: str = "F"):
        self.sql_execute(self.SQL_SET_VOICE % (LANG, GENDER), (voice, rowid))

    SQL_GET_ACCESS = "SELECT ACCESS FROM VERSION;"
    SQL_SET_ACCESS = "UPDATE VERSION SET ACCESS=?;"
    SQL_UPDATE_QUEUE = "UPDATE VERSION SET QUEUE = QUEUE %s;"

    def get_access_system(self) -> bool:
        list = self.sql_select(self.SQL_GET_ACCESS)
        return len(list)>0 and list[0][0] >= 0

    def set_access_system(self, i: int) -> bool:
        return self.sql_execute(self.SQL_SET_ACCESS, (i, ))

    def set_queue(self, i: int):
        if i > 0: self.sql_execute(self.SQL_UPDATE_QUEUE % "+1")
        if i < 0: self.sql_execute(self.SQL_UPDATE_QUEUE % "-1")

    def create_nuber_code(self, type_code: str)->str:
        t = str(datetime.datetime.now())
        md = md5(t.encode('utf-8')).hexdigest().upper()
        prev = md[:8]
        post = md[-24:]
        return prev + type_code + post

    SQL_GET_PROMO_ROWID = "SELECT ID FROM Promos WHERE ROWID=?;"
    SQL_INSERT_PROMO = """INSERT INTO Promos
                    (cdate, id_creater, Caption, count_lic, license_period, edate, id_seller)
                    VALUES(?, ?, ?, ?, ?, ?, ?)"""

    # self.sql_execute("""CREATE TABLE IF NOT EXISTS Promos(ID INTEGER PRIMARY KEY AUTOINCREMENT,
    #                     cdate INT, id_creater INT, Caption TXT, count_lic INT, license_period INT, edate INT, id_seller INT);""")
    #type_code: "6DC2A7B34E" -promo, "BC584D0A9D" - invite
    def create_promocodes(self, id_seller: int, Caption: str, count_key: int, count_lic: int, period: int, id_user: int)->int:
        rowid = self.sql_execute(self.SQL_INSERT_PROMO, (time_int(), id_user, Caption, count_lic, period, 0, id_seller))
        list_tuple = self.sql_select(self.SQL_GET_PROMO_ROWID, (rowid, ))
        if len(list_tuple)>0:
            id_promo = int(list_tuple[0][0])
            for i in range(count_key):
                S_Number = self.create_nuber_code("6DC2A7B34E")
                while DBKey(self, S_Numbr_Create=S_Number, id_promo=id_promo).ROWID == 0:
                    S_Number = self.create_nuber_code("6DC2A7B34E")
            return id_promo
        return 0

    SQL_GET_INVITE_ROWID = "SELECT S_Number FROM Invites WHERE ROWID=?;"
    SQL_GET_INVITE_CHAT_ID = "SELECT S_Number FROM Invites WHERE chat_id=?;"
    SQL_INSERT_INVITE = """INSERT INTO Invites(cdate, S_Number, chat_id) VALUES(?, ?, ?)"""

    def create_invites(self, chat_id: int):
        list_tuple = self.sql_select(self.SQL_GET_INVITE_CHAT_ID, (chat_id,))
        if len(list_tuple)>0: return str(list_tuple[0][0])

        rowid = -1
        while rowid == -1:
            S_Number = self.create_nuber_code("BC584D0A9D")
            rowid = self.sql_execute(self.SQL_INSERT_INVITE, (time_int(), S_Number, chat_id), False)

        list_tuple = self.sql_select(self.SQL_GET_INVITE_ROWID, (rowid, ))

        return str(list_tuple[0][0]) if len(list_tuple)>0 else "" #Возвращаем S_Number нового инвайта

    # self.sql_execute("""CREATE TABLE IF NOT EXISTS User_Invite(ID INTEGER PRIMARY KEY AUTOINCREMENT,
    #                                                             cdate INT, id_user INT, id_invite INT, chat_id INT);""")
    SQL_GET_INVITE_S_NUMBER = "SELECT ID, chat_id FROM Invites WHERE S_Number=?;"
    SQL_GET_INVITE_USER = "SELECT COUNT() FROM User_Invite WHERE id_user=?;"
    SQL_GET_INVITE_CHAT_ID_INVITE = "SELECT COUNT() FROM User_Invite WHERE chat_id=? AND id_invite=?;"
    SQL_INSERT_INVITE_USER = """INSERT INTO User_Invite(cdate, id_user, id_invite, chat_id) VALUES(?, ?, ?, ?)"""

    #return -2 - нет такого S_Number, -1 - пригласил сам себя, 0 - пользователь уже пользоавлся приграшением, 1 - есть S_Number и есть возможность приглашения
    def test_invite(self, id_user: int, chat_id: int, S_Number: str):
        list_tuple = self.sql_select(self.SQL_GET_INVITE_S_NUMBER, (S_Number,))
        if len(list_tuple)>0: #Есть такой Invite-код приглашения
            id_invite = int(list_tuple[0][0])
            chat_id_invite = int(list_tuple[0][1])
            if chat_id != chat_id_invite:
                list_tuple = self.sql_select(self.SQL_GET_INVITE_USER, (id_user,))
                if list_tuple[0][0]==0: #Юзер ещё не активировал приглашение
                    # Проверяем приглашал ли уже этого пользоватея на других зеркалах
                    list_tuple = self.sql_select(self.SQL_GET_INVITE_CHAT_ID_INVITE, (chat_id, id_invite))
                    if list_tuple[0][0]==0:  # Приглашение для этого пользователя (в другом зеркале) пока не было - начисляем бонусы за приглашение
                        self.sql_execute("UPDATE Users SET bonuses=bonuses+100 WHERE chat_id=?", (chat_id_invite,))
                    self.sql_execute(self.SQL_INSERT_INVITE_USER, (time_int(), id_user, id_invite, chat_id))
                    self.sql_execute("UPDATE Users SET bonuses=bonuses+100 WHERE ROWID=?", (id_user,))
                    return 100
                return 0
            return -1
        return -2

class DBSeller:
    ROWID: int = 0
    ID: int = 0
    cdate: int = 0
    Name: str = ""
    Caption: str = ""
    S_TEXT: str = ""
    I_INT: int = 0
    block: int = 0

    db_connect: SQLiteClient = None
    table_name = "Sellers"

    # self.sql_execute("""CREATE TABLE IF NOT EXISTS Sellers(ID INTEGER PRIMARY KEY AUTOINCREMENT,
    #                                                 cdate INT, Name TXT, Caption TXT, S_TEXT TXT, I_INT INT);""")

    SQL_GET = f"SELECT ROWID, * FROM {table_name} WHERE ID=?;"
    SQL_GET_ROWID = f"SELECT ROWID, * FROM {table_name} WHERE ROWID=?;"
    SQL_GET_LIST_ID = f"SELECT ID FROM {table_name};"
    SQL_DELETE = f"DELETE FROM {table_name} WHERE ID=?;"

    SQL_INSERT = f"""INSERT INTO {table_name}
                    (cdate, Name, Caption, S_TEXT, I_INT)
                    VALUES(?, ?, ?, '', 0)"""
    SQL_UPDATE = f"UPDATE {table_name} SET Name=?, Caption=?, S_TEXT=?, I_INT=?, Block=? WHERE ID=?;"

    def get_list_sellers(self)->list:
        list_tuple = self.db_connect.sql_select(self.SQL_GET_LIST_ID)
        list_sliders=[]
        for id in list_tuple:
            db_slider: DBSeller = DBSeller(self.db_connect, id[0])
            list_sliders.append(db_slider)
        return list_sliders

    def __init__(self, SQL: SQLiteClient, ID: int = -1):
        self.db_connect = SQL

        if ID != -1:
            self.get_id(ID)

    def get_id(self, ID: int) -> bool:
        list_tuple = self.db_connect.sql_select(self.SQL_GET, (ID, ))
        return self.set_from_tuple(list_tuple)

    def get_rowid(self, ROWID: int) -> bool:
        list_tuple = self.db_connect.sql_select(self.SQL_GET_ROWID, (ROWID, ))
        return self.set_from_tuple(list_tuple)

    def set_from_tuple(self, list_tuple: tuple) -> bool:
        if list_tuple:
            self.ROWID = int(list_tuple[0][0])
            self.ID = str(list_tuple[0][1])
            self.cdate = int(list_tuple[0][2])
            self.Name = str(list_tuple[0][3])
            self.Caption = str(list_tuple[0][4])
            self.S_TEXT = str(list_tuple[0][5])
            self.I_INT = int(list_tuple[0][6])
            self.block = int(list_tuple[0][7])
            return True
        return False

    def delete(self):
        self.db_connect.sql_execute(self.SQL_DELETE, (self.ID, ))

    def save(self, Name=None, Caption=None, S_TEXT=None, I_INT=None, block=None):
        if Name is not None: self.Name = Name
        if Caption is not None: self.Caption = Caption
        if S_TEXT is not None: self.S_TEXT = S_TEXT
        if I_INT is not None: self.I_INT = I_INT
        if block is not None: self.block = block
        if self.ROWID == 0:
            ROWID = self.db_connect.sql_execute(self.SQL_INSERT, (time_int(), self.Name, self.Caption))
            self.get_rowid(ROWID)
        else:
            self.db_connect.sql_execute(self.SQL_UPDATE, (self.Name, self.Caption, self.S_TEXT, self.I_INT,
                                                          self.block, self.ID))

class DBActiveKey:
    ROWID: int = 0
    ID: int = 0
    id_user: str = ""
    id_key: int = 0
    cdate: int = 0
    Caption: str = ""

    db_connect:SQLiteClient = None
    # self.sql_execute("""CREATE TABLE IF NOT EXISTS User_Active_Key(ID INTEGER PRIMARY KEY AUTOINCREMENT,
    #                 id_user INT, id_key INT, cdate INT, Caption TXT);""")
    SQL_GET_ID = f"SELECT ROWID, * FROM User_Active_Key WHERE ID=?;"
    SQL_GET_KEY = f"SELECT ID FROM User_Active_Key WHERE id_key=?;"

    SQL_INSERT_KEY = f"""INSERT INTO User_Active_Key(id_user, id_key, cdate, Caption) VALUES(?, ?, ?, ?)"""
    #SQL_UPDATE_PROMO = "UPDATE Promo_Active_User SET id_user=?, cdate_active=?, Caption=? WHERE S_Number=?;"

    def __init__(self, SQL: SQLiteClient, ID: int = -1):
        self.db_connect = SQL
        if ID != -1:
            self.get_id(ID)

    def get_list_activate(self, id_key: int = None):
        if id_key is None: id_key = self.id_key

        list_tuple = self.db_connect.sql_select(self.SQL_GET_KEY, (id_key, ))
        list_activate = []
        for id in list_tuple:
            db_active_key: DBActiveKey = DBActiveKey(self.db_connect, id[0])
            list_activate.append(db_active_key)

        return list_activate

    def get_id(self, ID: int) -> bool:
        list_tuple = self.db_connect.sql_select(self.SQL_GET_ID, (ID, ))
        return self.set_from_tuple(list_tuple)

    def set_from_tuple(self, list_tuple: tuple) -> bool:
        if list_tuple:
            self.ROWID = int(list_tuple[0][0])
            self.ID = int(list_tuple[0][1])
            self.id_user = int(list_tuple[0][2])
            self.id_key = int(list_tuple[0][3])
            self.cdate = int(list_tuple[0][4])
            self.Caption = str(list_tuple[0][5])
            return True
        return False

class DBPromo:
    ROWID: int = 0
    ID: int = 0
    cdate: int = 0
    id_creater: int = 0
    Caption: str = ""
    count_lic: int = 0
    license_period: int = 0
    edate: int = 0
    id_seller: int = 0
    block: int = 0

    count_key: int =0
    count_activate_key: int = 0

    SQL_GET_PROMO = "SELECT ROWID, * FROM Promos WHERE ID=?;"
    SQL_GET_LIST = "SELECT ID FROM Promos;"
    SQL_GET_KEYS = "SELECT ID FROM Keys WHERE id_promo=?;"
    SQL_GET_COUNT_KEY = "SELECT COUNT() FROM Keys WHERE id_promo=?;"
    SQL_GET_COUNT_ACTIVATE_KEY = """SELECT COUNT() FROM Keys JOIN User_Active_Key ON
      Keys.ID=User_Active_Key.id_key WHERE id_promo=?;"""

    # self.sql_execute("""CREATE TABLE IF NOT EXISTS User_Active_Key(ID INTEGER PRIMARY KEY AUTOINCREMENT,
    #                 id_user INT, id_key INT, cdate INT, Caption TXT);""")

    def __init__(self, SQL: SQLiteClient, ID: int = -1):
        self.db_connect = SQL

        if ID != -1:
            self.get_promo(ID)

    def get_list_keys(self, id_promo: int = None)->list:
        if id_promo is None: id_promo=self.ID
        list_tuple = self.db_connect.sql_select(self.SQL_GET_KEYS, (id_promo,))
        list_keys = []
        for id in list_tuple:
            db_key:DBKey = DBKey(self.db_connect, ID=id[0])
            list_keys.append(db_key)

        return list_keys

    def get_list_promo(self)->list:
        list_tuple = self.db_connect.sql_select(self.SQL_GET_LIST)
        list_promo = []
        for id in list_tuple:
            db_promo:DBPromo = DBPromo(self.db_connect, id[0])
            list_promo.append(db_promo)

        return list_promo

    def get_promo(self, id_promo: int):
        list_tuple = self.db_connect.sql_select(self.SQL_GET_PROMO, (id_promo, ))
        if list_tuple:
            self.ROWID = int(list_tuple[0][0])
            self.ID = int(list_tuple[0][1])
            self.cdate = int(list_tuple[0][2])
            self.id_creater = int(list_tuple[0][3])
            self.Caption = str(list_tuple[0][4])
            self.count_lic = int(list_tuple[0][5])
            self.license_period = int(list_tuple[0][6])
            self.edate = int(list_tuple[0][7])
            self.id_seller = int(list_tuple[0][8])
            self.block = int(list_tuple[0][9])

            list_tuple = self.db_connect.sql_select(self.SQL_GET_COUNT_KEY, (id_promo,))
            self.count_key = list_tuple[0][0]

            list_tuple = self.db_connect.sql_select(self.SQL_GET_COUNT_ACTIVATE_KEY, (id_promo,))
            self.count_activate_key = list_tuple[0][0]

    SQL_UPDATE = f"UPDATE Promos SET Block=? WHERE ID=?;"

    def save(self, block=None):
        if block is not None: self.block = block
        self.db_connect.sql_execute(self.SQL_UPDATE, (self.block, self.ROWID))

class DBKey:
    ROWID: int = 0
    ID: int = 0
    S_Number: str = ""
    id_promo: int = 0

    db_connect: SQLiteClient = None
    table_name = "Keys"

    # self.sql_execute("""CREATE TABLE IF NOT EXISTS Promos(ID INTEGER PRIMARY KEY AUTOINCREMENT,
    #                 cdate INT, id_creater INT, Caption TXT, count_lic INT, license_period INT, edate INT, id_seller INT);""")

    # self.sql_execute("""CREATE TABLE IF NOT EXISTS Keys(ID INTEGER PRIMARY KEY AUTOINCREMENT,
    #                 S_Number TEXT UNIQUE, id_promo INT);""")

    SQL_GET_S_Number = f"SELECT ROWID, * FROM {table_name} WHERE S_Number=?;"
    SQL_GET_ID = f"SELECT ROWID, * FROM {table_name} WHERE ID=?;"

    SQL_INSERT_KEY = f"""INSERT INTO {table_name}(S_Number, id_promo) VALUES(?, ?)"""

    # self.sql_execute("""CREATE TABLE IF NOT EXISTS User_Active_Key(ID INTEGER PRIMARY KEY AUTOINCREMENT,
    #                 id_user INT, id_key INT, cdate INT, Caption TXT);""")
    SQL_INSERT_ACTIVATE_KEY = f"""INSERT INTO User_Active_Key(id_user, id_key, cdate, Caption) VALUES(?, ?, ?, ?)"""

    def activate(self, id_user: int):
        self.db_connect.sql_execute(self.SQL_INSERT_ACTIVATE_KEY, (id_user, self.ID, time_int(), "Caption"))

    def __init__(self, SQL: SQLiteClient, ID: int = None, S_Nunber: str = None,  S_Numbr_Create: str = None, id_promo: int = None):
        self.db_connect = SQL

        if ID is not None:
            self.get_id(ID)

        if S_Nunber is not None:
            self.get_s_number(S_Nunber)

        elif S_Numbr_Create is not None and id_promo is not None:
            if self.db_connect.sql_execute(self.SQL_INSERT_KEY, (S_Numbr_Create, id_promo), False) != -1:
                self.get_s_number(S_Numbr_Create)

    def get_list_activate(self):
        db_active_key: DBActiveKey = DBActiveKey(self.db_connect)
        return db_active_key.get_list_activate(self.ID)

    def get_id(self, ID: int) -> bool:
        list_tuple = self.db_connect.sql_select(self.SQL_GET_ID, (ID, ))
        return self.set_from_tuple(list_tuple)

    def get_s_number(self, S_Number: str) -> bool:
        list_tuple = self.db_connect.sql_select(self.SQL_GET_S_Number, (S_Number, ))
        return self.set_from_tuple(list_tuple)

    def set_from_tuple(self, list_tuple: tuple) -> bool:
        if list_tuple:
            self.ROWID = int(list_tuple[0][0])
            self.ID = int(list_tuple[0][1])
            self.S_Number = str(list_tuple[0][2])
            self.id_promo = int(list_tuple[0][3])
            return True
        return False

class DBUser:
    ROWID: int = 0
    chat_id = 0     #chart_id telegram
    Name = ''
    UserName: str = ""
    mode: int = 0
    adm_level: int = 0
    cdate: int = 0
    ldate: int = 0
    current_lesson_id: int = 0
    current_video_id: int = 0
    msg_dialog_id: int = 0
    msg_reply_id: int = 0
    last_video_id: int = 0
    current_variant_id: int = 0
    keyboard: str = ""
    last_word: str = ""
    skill: int = 0
    subtitle_type: int = 0
    id_token_bot: int = 0
    license_date: int =0
    bonuses: int =0

    db_connect: SQLiteClient = None
    table_name = 'Users'

    GET_USER=f"SELECT *, ROWID FROM {table_name} WHERE chat_id=? and id_token_bot=?;"
    SQL_GET_LDATE=f"SELECT ldate FROM {table_name} WHERE chat_id=?;"
    SQL_LIST_SLIDERS = f"SELECT ROWID FROM Sliders ORDER BY num;"
    SQL_CREATE_USER =f"""INSERT INTO {table_name}(
        chat_id, Name, UserName, mode, adm_level, cdate, ldate, id_token_bot,
        current_lesson_id, current_video_id, msg_dialog_id, msg_reply_id, last_video_id, current_variant_id, 
        keyboard, last_word, skill)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?,
               0, 0, 0, 0, 0, 0, '', '', 0);"""
    SAVE_USER = f"""UPDATE {table_name} SET Name=?, UserName=?, mode=?, adm_level=?, ldate=?,
                    current_lesson_id=?, current_video_id=?, msg_dialog_id=?, msg_reply_id=?,
                    last_video_id=?, current_variant_id=?, keyboard=?, last_word=?, skill=?,
                    subtitle_type=?, license_date=?, bonuses=? WHERE ROWID=?;"""

    SQL_DELETE_ALL_MESSAGES = "DELETE FROM Messages WHERE id_user=? AND type<>? AND rowid_user=?;"
    SQL_GET_MESSAGES = "SELECT id_message, type FROM Messages WHERE id_user=? AND type<>? AND rowid_user=?;"
    SQL_NULL_MESSAGES = "UPDATE Messages SET type=0 WHERE id_user=? and rowid_user=?;"

    def __del__(self):
        if self.ROWID > 0: self.db_connect.set_queue(-1)
        self.db_connect.close()

    def get_access(self, adm_level:int, chat_id: int) -> bool:
        access = self.db_connect.get_access_system()
        if access: self.db_connect.set_queue(+1)
        return access

    def __init__(self, SQL: SQLiteClient, chat_id: int, adm_level: int=-2, Name: str=None, UserName: str=None):
        self.db_connect = SQL
        if not self.get_access(adm_level, chat_id):
            self.ROWID = -1
            return

        if not self.get_char_id(chat_id, SQL.id_token_bot):
            if UserName is None: UserName = ""
            #try:
            self.create_user(chat_id, adm_level, Name, UserName, SQL.id_token_bot)
            self.db_connect.send_massage_admin_chat(
                f"New User <b>{Name}</b> {f'@{UserName}' if UserName != '' else ''}")
            # except:
            #     self.db_connect.send_massage_admin_chat(
            #         f"Error create user chat_id={chat_id} <b>{Name}</b> {f'@{UserName}' if UserName != '' else ''}")
            #     self.chat_id = -1
            #     return
            return

        if adm_level!=-2 and self.adm_level != adm_level:
            self.adm_level = adm_level

        if Name is not None and self.Name != Name:
            self.Name = Name

        if UserName is not None and self.UserName != UserName:
            self.UserName = UserName
        elif UserName is None and self.UserName != "":
            self.UserName = ""

        self.save_user(ldate=time_int())

    def send_admin_message(self, msg: str, if_save_msg: bool = False)->int:
        return self.db_connect.send_massage_admin_chat(
            f"User <b>{self.Name}</b> {f'@{self.UserName}' if self.UserName != '' else ''}\n{msg}", if_save_msg)

    def get_ldate(self) -> int:
        list_tuple = self.db_connect.sql_select(self.SQL_GET_LDATE, (self.chat_id, ))
        if len(list_tuple) == 0:
            return 0
        else:
            return list_tuple[0][0]

    def save_message(self, id_message: int, message: str = "", type: int = 1, id_user: int = None):
        rowid = self.ROWID if id_user is None else DBUser(self.db_connect, id_user).ROWID
        if id_user is None: id_user = self.chat_id
        self.db_connect.sql_execute(self.db_connect.SQL_SAVE_MESSAGE, (id_user, id_message, time_int(), message, type, rowid))

    def delete_all_messages(self, except_: int = -1):
        self.db_connect.sql_execute(self.SQL_DELETE_ALL_MESSAGES, (self.chat_id, except_, self.ROWID))

    def set_null_all_messages(self):
        self.db_connect.sql_execute(self.SQL_NULL_MESSAGES, (self.chat_id, self.ROWID))

    def get_list_messages(self, except_: int = -1) -> list:
        return self.db_connect.sql_select(self.SQL_GET_MESSAGES, (self.chat_id, except_, self.ROWID))

    def get_char_id(self, char_id: int, id_token_bot: int) -> bool:
        users = self.db_connect.sql_select(self.GET_USER, (char_id, id_token_bot))
        if len(users)>0:
            self.chat_id = int(users[0][0])
            self.Name = str(users[0][1])
            self.UserName = str(users[0][2])
            self.mode = int(users[0][3])
            self.adm_level = int(users[0][4])
            self.cdate   = int(users[0][5])
            self.ldate   = int(users[0][6])
            self.current_lesson_id = int(users[0][7])
            self.current_video_id = int(users[0][8])
            self.msg_dialog_id = int(users[0][9])
            self.msg_reply_id = int(users[0][10])
            self.last_video_id = int(users[0][11])
            self.current_variant_id = int(users[0][12])
            self.keyboard = str(users[0][13])
            self.last_word = str(users[0][14])
            self.skill = int(users[0][15])
            self.subtitle_type = int(users[0][16])
            self.id_token_bot = int(users[0][17])
            self.license_date = int(users[0][18])
            self.bonuses = int(users[0][19])
            self.ROWID = int(users[0][20])

        return len(users)>0

    def create_user(self, chat_id: int, adm_level, Name: str, UserName: str, id_toke_bot: int):
        time_current=time_int()
        if Name == None: Name = ""
        if UserName == None: UserName = ""
        self.db_connect.sql_execute(self.SQL_CREATE_USER, (chat_id, Name, UserName, 0, adm_level, time_current, time_current, id_toke_bot))
        self.get_char_id(chat_id, id_toke_bot)

    def save_user(self, ldate=None, Name=None, adm_level=None,
                  mode=None, current_lesson_id=None, current_video_id=None, msg_dialog_id=None,
                  msg_reply_id=None, last_video_id=None, UserName=None, current_variant_id=None,
                  keyboard=None, last_word=None, skill=None, subtitle_type=None, license_date=None,
                  bonuses=None):

        self.ldate = ldate if ldate is not None else time_int()
        if Name is not None: self.Name = Name
        if UserName is not None: self.UserName = UserName
        if adm_level is not None: self.adm_level = adm_level
        if mode is not None: self.mode = mode
        if current_lesson_id is not None: self.current_lesson_id = current_lesson_id
        if current_video_id is not None: self.current_video_id = current_video_id
        if msg_dialog_id is not None: self.msg_dialog_id = msg_dialog_id
        if msg_reply_id is not None: self.msg_reply_id = msg_reply_id
        if last_video_id is not None: self.last_video_id = last_video_id
        if current_variant_id is not None: self.current_variant_id = current_variant_id
        if keyboard is not None: self.keyboard = keyboard
        if last_word is not None: self.last_word = last_word
        if skill is not None: self.skill = skill
        if subtitle_type is not None: self.subtitle_type = subtitle_type
        if license_date is not None: self.license_date = license_date
        if bonuses is not None: self.bonuses = bonuses
        self.db_connect.sql_execute(self.SAVE_USER, (self.Name, self.UserName, self.mode, self.adm_level,
                                    self.ldate, self.current_lesson_id, self.current_video_id, self.msg_dialog_id,
                                    self.msg_reply_id, self.last_video_id, self.current_variant_id,
                                    self.keyboard, self.last_word, self.skill, self.subtitle_type,
                                    self.license_date, self.bonuses,
                                    self.ROWID))

class DBLesson:
    ROWID = 0
    num = 0
    Name: str = ""
    Caption: str = ""
    skill: int = 0
    id_chapter: int = 0
    type: int = 0 #0-неопределён 1-каталог 2-слайды
    s_type: str = ""
    test_time: int = 0
    test_num_errors: int = 0
    test_skill_decrement: int

    db_rules: DBRules
    db_connect: SQLiteClient = None
    table_name = 'Lessons'

    SQL_GET = f"SELECT ROWID, * FROM {table_name} WHERE ROWID=?;"
    SQL_GET_FROM_num = f"SELECT ROWID, * FROM {table_name} WHERE num=? AND id_chapter=?;"
    SQL_GET_MAX_NUM = f"SELECT MAX(num) FROM {table_name} WHERE id_chapter=?;"
    SQL_LIST_LESSONS = f"SELECT ROWID FROM {table_name} WHERE id_chapter=? ORDER BY num;"
    SQL_LIST_SLIDES = f"""SELECT ROWID FROM Slides WHERE id_lesson=? ORDER BY num ASC, ROWID ASC;"""
    SQL_LIST_SLIDES_TEST = f"""SELECT ROWID FROM Slides WHERE is_test=1 AND id_lesson=? ORDER BY RANDOM();"""
    SQL_CREATE = f"INSERT INTO {table_name}(num, Name, Caption, skill, id_chapter, type, test_num_errors) VALUES(?, ?, ?, 0, ?, 0, 1);"
    SQL_SAVE = f"""UPDATE {table_name} SET num=?, Name=?, Caption=?, skill=?, id_chapter=?, type=?, test_time=?,
                   test_num_errors=?, test_skill_decrement=? WHERE ROWID=?;"""
    SQL_DELETE_LESSON = f"DELETE FROM {table_name} WHERE ROWID=?;"
    #SQL_DECREMENT_NUM = f"UPDATE {table_name} SET num=num+1 WHERE num>?;"
    SQL_GET_MAX_NUM_LESSONS = f"SELECT MAX(num) FROM Lessons WHERE id_chapter=?;"

    def __del__(self):
        pass

    def __init__(self, SQL: SQLiteClient, ROWID: int = -1, num: int = None, id_chapter=None):
        self.db_connect = SQL

        if num is not None and id_chapter is not None:
            if self.get_from_num(num, id_chapter) is False:
                self.normalize_num_lessons()
                self.get_from_num(num, id_chapter)
        elif not self.get_id(ROWID) and ROWID == 0 and id_chapter != None:
            self.create("Урок", "Caption", id_chapter)

    def get_max_num_lessons(self, id_chapter: int = None) -> int:
        if id_chapter is None: id_chapter = self.ROWID
        max_num: int = self.db_connect.sql_select(self.SQL_GET_MAX_NUM_LESSONS, (id_chapter, ))[0][0]
        return 0 if max_num is None else max_num

    def get_list_lessons(self, id_chapter: int = None) -> list:
        if id_chapter is None: id_chapter = self.ROWID
        list_tuple = self.db_connect.sql_select(self.SQL_LIST_LESSONS, (id_chapter, ))
        list_lessons = []
        for ROWID in list_tuple:
            list_lessons.append(DBLesson(self.db_connect, ROWID[0]))
        return list_lessons

    def copy(self):
        #self.decrement_last_lessons_num()
        db_lesson_new: DBLesson = DBLesson(self.db_connect, 0, None, self.id_chapter)
        max_num: int = self.db_connect.sql_select(self.SQL_GET_MAX_NUM, (self.id_chapter,))[0][0]
        num = 1 if max_num is None else max_num + 1
        db_lesson_new.save(num = num, Name = self.Name, Caption = self.Caption, type=self.type,
                           skill=self.skill, test_time = self.test_time, test_num_errors = self.test_num_errors,
                           test_skill_decrement = self.test_skill_decrement)

        if self.type == 1: # Каталог
            list_lessons = self.get_list_lessons()
            db_lesson: DBLesson
            for db_lesson in list_lessons:
                db_lesson.copy().save(id_chapter=db_lesson_new.ROWID)

        elif self.type == 2: # Слайды
            list_slides = self.get_list_slides()
            db_slide: DBSlide
            dict_id_slides = {} # - Таблица соответствия id_next_slide
            for db_slide in list_slides:
                db_new_slide: DBSlide = db_slide.copy(db_lesson_new.ROWID)
                dict_id_slides[db_slide.ROWID] = db_new_slide.ROWID

            #Перелинкуем переходы Вариантов на новые Слайды
            list_slides = db_lesson_new.get_list_slides()
            for db_slide in list_slides:
                list_variants = db_slide.get_list_variants()
                db_variant: DBVariant
                for db_variant in list_variants:
                    if db_variant.id_next_slide != 0 and dict_id_slides.get(db_variant.id_next_slide) is not None:
                        db_variant.save(id_next_slide=dict_id_slides[db_variant.id_next_slide])

        return db_lesson_new

    def normalize_num_lessons(self, id_chapter: int = None) -> int:
        if id_chapter is None: id_chapter = self.ROWID
        list_lessons = self.get_list_lessons(id_chapter)
        for i in range(0, len(list_lessons)):
            db_lesson: DBLesson = list_lessons[i]
            db_lesson.save(num=i + 1)
        return len(list_lessons)

    def normalize_num_slides(self) -> int:
        list_slides= self.get_list_slides()
        for i in range(0, len(list_slides)):
            db_slide: DBSlide = list_slides[i]
            db_slide.save(num = i + 1)
        return len(list_slides)

    # def decrement_last_lessons_num(self):
    #     self.db_connect.sql_execute(self.SQL_DECREMENT_NUM, (self.num, ))

    def get_list_slides(self) -> list:
        list_tuple = self.db_connect.sql_select(self.SQL_LIST_SLIDES, (self.ROWID, ))
        list_slides = []
        for ROWID in list_tuple:
            list_slides.append(DBSlide(self.db_connect, ROWID[0]))
        return list_slides

    def get_list_slides_test(self, id_lessons: int = None) -> list:
        if id_lessons is None: id_lessons = self.ROWID
        list_tuple = self.db_connect.sql_select(self.SQL_LIST_SLIDES_TEST, (id_lessons, ))
        list_lessons = []
        for ROWID in list_tuple:
            list_lessons.append(DBSlide(self.db_connect, ROWID[0]))
        return list_lessons

    def set_from_tuple(self, list_tuple: tuple) -> bool:
        if list_tuple:
            self.ROWID = int(list_tuple[0][0])
            self.num = int(list_tuple[0][1])
            self.Name = str(list_tuple[0][2])
            self.Caption = str(list_tuple[0][3])
            self.skill = int(list_tuple[0][4])
            self.id_chapter = int(list_tuple[0][5])
            self.type = int(list_tuple[0][6])
            self.test_time = int(list_tuple[0][7])
            self.test_num_errors = int(list_tuple[0][8])
            self.test_skill_decrement = int(list_tuple[0][9])
            self.db_rules = DBRules(self.Caption)
            self.s_type = '📄' if self.type == 2 else '🗂' if self.type == 1 else '\U0001F4D9'
            return True
        return False

    def get_from_num(self, num: int, id_chapter: int) -> bool:
        list_tuple = self.db_connect.sql_select(self.SQL_GET_FROM_num, (num, id_chapter))
        return self.set_from_tuple(list_tuple)

    def get_id(self, ROWID: int) -> bool:
        if ROWID < 0: return False
        list_tuple = self.db_connect.sql_select(self.SQL_GET, (ROWID, ))
        return self.set_from_tuple(list_tuple)

    def create(self, Name: str, Caption: str, id_chapter: int):
        max_num: int = self.db_connect.sql_select(self.SQL_GET_MAX_NUM, (id_chapter, ))[0][0]
        num = 1 if max_num is None else max_num + 1
        self.ROWID=self.db_connect.sql_execute(self.SQL_CREATE, (num, f"{Name} - {num}", Caption, id_chapter))
        self.get_id(self.ROWID)

    def delete(self):
        db_slide: DBSlide
        list_slides = self.get_list_slides()
        for db_slide in list_slides:
            db_slide.delete()

        self.db_connect.sql_execute(self.SQL_DELETE_LESSON, (self.ROWID, ))

        db_lesson: DBLesson
        list_lessons = self.get_list_lessons()
        for db_lesson in list_lessons:
            db_lesson.delete()

        if self.id_chapter > 0:
            db_lesson = DBLesson(self.db_connect, self.id_chapter)
            if db_lesson.normalize_num_lessons()==0:
                db_lesson.save(type=0)

    def save(self, num=None, Name=None, Caption=None, skill=None, id_chapter=None, type=None, test_time=None,
             test_num_errors=None, test_skill_decrement=None):
        if num is not None: self.num = num
        if Name is not None: self.Name = Name
        if Caption is not None: self.Caption = Caption
        if skill is not None: self.skill = skill
        if id_chapter is not None: self.id_chapter = id_chapter
        if type is not None: self.type = type
        if test_time is not None: self.test_time = test_time
        if test_num_errors is not None: self.test_num_errors = test_num_errors
        if test_skill_decrement is not None: self.test_skill_decrement = test_skill_decrement
        self.db_rules = DBRules(self.Caption)
        self.s_type = '📄' if self.type == 2 else '🗂' if self.type == 1 else '\U0001F4D9'
        self.db_connect.sql_execute(self.SQL_SAVE, (self.num, self.Name, self.Caption, self.skill,
            self.id_chapter, self.type, self.test_time, self.test_num_errors, self.test_skill_decrement, self.ROWID))

class DBSlide:
    ROWID: int = 0
    id_lesson: int = 0
    num: int = 0
    Name: str
    Caption: str
    List_Words: str
    Video_Size: int
    Rules: str
    Message: str
    is_test: int = 0
    keyboard_dict: str

    db_rules: DBRules
    table_name = 'Slides'

    SQL_GET_FROM_num = f"""SELECT ROWID, id_lesson, num, Name, Caption, List_Words, 
                           Video_Size, Rules, Message, is_test, keyboard_dict FROM {table_name} WHERE num=? AND id_lesson=?;"""
    SQL_GET = f"""SELECT ROWID, id_lesson, num, Name, Caption, List_Words, Video_Size, Rules, Message,
               is_test, keyboard_dict FROM {table_name} WHERE ROWID=?;"""
    SQL_GET_MAX_NUM = f"""SELECT MAX(num) FROM {table_name} WHERE id_lesson=?;"""
    SQL_CREATE = f"""INSERT INTO {table_name}(id_lesson, num, Name, Caption, List_Words, Video_Size, Rules, Message) 
                VALUES(?, ?, ?, ?, '', 0, '', '-');"""
    SQL_SAVE = f"""UPDATE {table_name} SET num=?, Name=?, Caption=?, List_Words=?, Rules=?, Message=?, is_test=?,
                keyboard_dict=? WHERE ROWID=?;"""
    SQL_LIST_VARIANTS = f"""SELECT ROWID FROM Variants WHERE id_slide=?;"""
    SQL_SAVE_VIDEO = f"UPDATE {table_name} SET Video=?, Video_Size=? WHERE ROWID=?;"
    SQL_GET_VIDEO = f"SELECT Video FROM {table_name} WHERE ROWID=?;"
    SQL_GET_VIDEO_SIZE = f"SELECT Video_Size FROM {table_name} WHERE ROWID=?;"
    SQL_DELETE_VIDEO = f"UPDATE {table_name} SET Video='', Video_Size=0 WHERE ROWID=?;"
    SQL_DELETE_SLIDE = f"DELETE FROM {table_name} WHERE ROWID=?;"
    SQL_INCREMENT_NUM = f"UPDATE {table_name} SET num=num-1 WHERE num>?;"
    SQL_DELETE_NEXT_SLIDE = f"UPDATE Variants SET id_next_slide=0 WHERE id_next_slide=?;"

    SQL_LIST_ALL_SLIDES = f"""SELECT ROWID FROM {table_name};"""

    SQL_DECREMENT_NUM = f"UPDATE {table_name} SET num=num+1 WHERE num>?;"

    def __del__(self):
        pass

    def __init__(self, db_connect: SQLiteClient, ROWID: int = -1, id_lesson: int =-1, num: int = None):
        self.db_connect=db_connect

        if num is not None and id_lesson > 0:
            if self.get_from_num(num, id_lesson) is False and id_lesson > 0:
                DBLesson(self.db_connect, self.id_lesson).normalize_num_lessons()
                self.get_from_num(num, id_lesson)

        elif not self.get_id(ROWID) and ROWID == 0 and id_lesson > 0:
            self.create(id_lesson, "Slide", "-")

    def get_all_slides(self):
        list_tuple = self.db_connect.sql_select(self.SQL_LIST_ALL_SLIDES)
        list_slides = []
        for ROWID in list_tuple:
            list_slides.append(DBSlide(self.db_connect, ROWID[0]))
        return list_slides

    def set_from_tuple(self, list_tuple: tuple) -> bool:
        if list_tuple:
            self.ROWID = int(list_tuple[0][0])
            self.id_lesson = int(list_tuple[0][1])
            self.num = int(list_tuple[0][2])
            self.Name = str(list_tuple[0][3])
            self.Caption = str(list_tuple[0][4])
            self.List_Words = str(list_tuple[0][5])
            self.Video_Size = int(list_tuple[0][6])
            self.Rules = str(list_tuple[0][7])
            self.Message = str(list_tuple[0][8])
            self.is_test = int(list_tuple[0][9])
            self.keyboard_dict = str(list_tuple[0][10])
            self.db_rules = DBRules(self.Rules)
            return True
        return False

    def get_from_num(self, num: int, id_lesson: int = None) -> bool:
        if num is None or num < 1: return False
        if id_lesson is None: id_lesson=self.id_lesson
        list_tuple = self.db_connect.sql_select(self.SQL_GET_FROM_num, (num, id_lesson))
        return self.set_from_tuple(list_tuple)

    def decrement_last_slide_num(self):
        self.db_connect.sql_execute(self.SQL_DECREMENT_NUM, (self.num, ))

    def copy(self, id_lesson: int):
        db_slide_new: DBSlide = DBSlide(self.db_connect, 0, id_lesson)
        dict_list_words: dict = get_dict_words(self.List_Words, db_slide_new.ROWID)
        db_slide_new.save(num=self.num, Name = self.Name, Caption = self.Caption, List_Words = self.List_Words,
                          Rules = self.Rules, Message=self.Message, is_test=self.is_test,
                          keyboard_dict=json.dumps(dict_list_words))

        db_slide_new.save_video(self.get_video(), self.Video_Size)

        list_variants = self.get_list_variants()
        db_variant: DBVariant
        for db_variant in list_variants:
            db_variant.copy(db_slide_new.ROWID)

        return db_slide_new

    def increment_las_indexes_num(self):
        self.db_connect.sql_execute(self.SQL_INCREMENT_NUM, (self.num, ))

    # def delete_video(self):
    #     self.db_connect.sql_execute(self.SQL_DELETE_VIDEO, (self.ROWID, ))
    #     self.Video_Size = 0

    def save_video(self, video: bytes, size: int):
        self.db_connect.sql_execute(self.SQL_SAVE_VIDEO, (video, size, self.ROWID))
        self.Video_Size = size

    def get_video(self) -> bytes:
        return self.db_connect.sql_select(self.SQL_GET_VIDEO, (self.ROWID, ))[0][0]

    def get_video_size(self) -> int:
        list_tuple = self.db_connect.sql_select(self.SQL_GET_VIDEO_SIZE, (self.ROWID, ))
        if len(list_tuple)==0:
            return 0
        return list_tuple[0][0]/1024

    def get_list_variants(self) -> list:
        list_tuple = self.db_connect.sql_select(self.SQL_LIST_VARIANTS, (self.ROWID, ))
        list_lessons = []
        for ROWID in list_tuple:
            list_lessons.append(DBVariant(self.db_connect, ROWID[0]))
        return list_lessons

    def get_id(self, ROWID: int) -> bool:
        if isinstance(ROWID, int) and ROWID < 0: return False
        list_tuple = self.db_connect.sql_select(self.SQL_GET, (ROWID, ))
        return self.set_from_tuple(list_tuple)

    def create(self, id_lessons: int, Name: str, Caption: str):
        num: int = self.get_max_num(id_lessons) + 1
        self.ROWID = self.db_connect.sql_execute(self.SQL_CREATE, (id_lessons, num , f"{Name} - {num}", Caption))
        self.get_id(self.ROWID)

    def get_max_num(self, id_lessons: int = None) -> int:
        if id_lessons is None: id_lessons = self.id_lesson
        max_num = self.db_connect.sql_select(self.SQL_GET_MAX_NUM, (id_lessons, ))[0][0]
        return 0 if max_num is None else max_num

    def delete(self):
        db_variant: DBVariant
        list_variants = self.get_list_variants()
        for db_variant in list_variants:
            db_variant.delete()
        self.increment_las_indexes_num()
        self.db_connect.sql_execute(self.SQL_DELETE_NEXT_SLIDE, (self.ROWID, ))
        self.db_connect.sql_execute(self.SQL_DELETE_SLIDE, (self.ROWID, ))
        db_lesson = DBLesson(self.db_connect, self.id_lesson)
        if db_lesson.normalize_num_slides() == 0:
            db_lesson.save(type=0)

    def save(self, num=None, Name=None, Caption=None, List_Words=None, Rules=None, Message=None, is_test=None, keyboard_dict=None):
        if num is not None: self.num = num
        if Name is not None: self.Name = Name
        if Caption is not None: self.Caption = Caption
        if List_Words is not None: self.List_Words = List_Words
        if Rules is not None: self.Rules = Rules
        if Message is not None: self.Message = Message
        if is_test is not None: self.is_test = is_test
        if keyboard_dict is not None: self.keyboard_dict = keyboard_dict
        self.db_connect.sql_execute(self.SQL_SAVE, (self.num, self.Name, self.Caption, self.List_Words, self.Rules,
                                                    self.Message, self.is_test, self.keyboard_dict, self.ROWID))

class DBVariant:
    ROWID: int = 0
    id_slide: int = 0
    Name: str = ""
    Caption: str = ""
    id_next_slide: int = 0

    db_rules: DBRules
    table_name = 'Variants'

    SQL_GET = f"SELECT * FROM {table_name} WHERE ROWID=?;"
    SQL_CREATE = f"INSERT INTO {table_name}(id_slide, Name, Caption, id_next_slide) VALUES(?, ?, ?, 0);"
    SQL_SAVE = f"UPDATE {table_name} SET Name=?, Caption=?, id_next_slide=? WHERE ROWID=?;"
    SQL_DELETE_VARIANT = f"DELETE FROM {table_name} WHERE ROWID=?;"

    def __del__(self):
        pass

    def __init__(self, db_connect: SQLiteClient, ROWID: int = -1, id_slide: int = -1):
        self.db_connect=db_connect

        if not self.get_id(ROWID) and ROWID == 0 and id_slide>0:
            self.create(id_slide, "Variant", "Caption")

    def copy(self, id_slide: int):
        db_variant_new: DBVariant = DBVariant(self.db_connect, 0, id_slide)
        db_variant_new.save(Name=self.Name, Caption=self.Caption, id_next_slide=self.id_next_slide)
        return db_variant_new

    def get_id(self, ROWID: int) -> bool:
        if ROWID < 0: return False

        list_tuple = self.db_connect.sql_select(self.SQL_GET, (ROWID, ))
        if list_tuple:
            self.ROWID = ROWID
            self.id_slide = int(list_tuple[0][0])
            self.Name = str(list_tuple[0][1])
            self.Caption = str(list_tuple[0][2])
            self.id_next_slide = int(list_tuple[0][3])
            self.db_rules = DBRules(self.Caption)
            return True
        return False

    def create(self, id_slide: int, Name: str, Caption: str):
        self.ROWID = self.db_connect.sql_execute(self.SQL_CREATE, (id_slide, Name, Caption))
        self.get_id(self.ROWID)

    def delete(self):
        self.ROWID = self.db_connect.sql_execute(self.SQL_DELETE_VARIANT, (self.ROWID, ))

    def save(self, Name=None, Caption=None, id_next_slide=None):
        if Name is not None: self.Name = Name
        if Caption is not None: self.Caption = Caption
        if id_next_slide is not None: self.id_next_slide = id_next_slide
        self.db_connect.sql_execute(self.SQL_SAVE, (self.Name, self.Caption, self.id_next_slide, self.ROWID))

class DBGame:
    ROWID: int = 0
    id_user: int = 0
    id_lesson: int = 0
    id_cur_slide: int = 0
    user_skill: int = 0
    cdate: int = 0
    ldate: int = 0
    control_cdate: int = 0
    control_edate: int = 0
    control_result: int = 0
    control_time: int = 0
    control_num_errors: int = 0
    control_list_id_slides: str = ""
    id_variant_click: int = 0

    table_name = 'Games'

    SQL_GET = f"SELECT ROWID, * FROM {table_name} WHERE ROWID=?;"
    SQL_GET_ID_USER_ID_LESSON = f"SELECT ROWID, * FROM {table_name} WHERE id_user=? and id_lesson=?;"
    SQL_CREATE = f"""INSERT INTO {table_name}(id_user, id_lesson, id_cur_slide, user_skill, cdate, ldate,
        control_cdate, control_edate, control_result, control_time, control_num_errors, control_list_id_slides,
        id_variant_click)
        VALUES(?, ?, 0, ?, ?, ?,
               0, 0, 0, 0, 0, '', 0);"""
    SQL_SAVE = f"""UPDATE {table_name} SET id_cur_slide=?, user_skill=?, ldate=?, control_cdate=?, control_edate=?,
        control_result=?, control_time=?, control_num_errors=?, control_list_id_slides=?, id_variant_click=? WHERE ROWID=?;"""
    SQL_DELETE = f"DELETE FROM {table_name} WHERE ROWID=?;"

    def __del__(self):
        pass

    def __init__(self, db_connect: SQLiteClient, id_user: int, id_lesson: int, ROWID: int = None):
        self.db_connect=db_connect

        if not self.get_id_user_id_lesson(id_user, id_lesson):
            self.create(id_user, id_lesson)

    #Проверяем исполнение всех уроков по данному разделу
    def check_result_all_lessons(self) -> bool:
        db_lesson: DBLesson = DBLesson(self.db_connect, self.id_lesson)
        if db_lesson.type == 1:
            list_lessons = db_lesson.get_list_lessons(self.id_lesson)
            _F_ = True
            for db_lesson in list_lessons:
                db_game: DBGame = DBGame(self.db_connect, self.id_user, db_lesson.ROWID)
                if db_game.control_result != 2:
                    _F_ = False
                    break
            control_result = 2 if len(list_lessons) > 0 and _F_ == True else 0
            if control_result != self.control_result:
                self.save(control_result = control_result)

            return control_result == 2
        return False

    def get_id_user_id_lesson(self, id_user: int, id_lesson: int) -> bool:
        list_tuple = self.db_connect.sql_select(self.SQL_GET_ID_USER_ID_LESSON, (id_user, id_lesson))
        return self.set_from_tuple(list_tuple)

    def set_from_tuple(self, list_tuple: tuple) -> bool:
        if list_tuple:
            self.ROWID = int(list_tuple[0][0])
            self.id_user: int = int(list_tuple[0][1])
            self.id_lesson: int = int(list_tuple[0][2])
            self.id_cur_slide: int = int(list_tuple[0][3])
            self.user_skill: int = int(list_tuple[0][4])
            self.cdate: int = int(list_tuple[0][5])
            self.ldate: int = int(list_tuple[0][6])
            self.control_cdate: int = int(list_tuple[0][7])
            self.control_edate: int = int(list_tuple[0][8])
            self.control_result: int = int(list_tuple[0][9])
            self.control_time: int = int(list_tuple[0][10])
            self.control_num_errors: int = int(list_tuple[0][11])
            self.control_list_id_slides: str = str(list_tuple[0][12])
            self.id_variant_click: int = int(list_tuple[0][13])
            return True
        return False

    def get_id(self, ROWID: int) -> bool:
        if ROWID < 0: return False
        list_tuple = self.db_connect.sql_select(self.SQL_GET, (ROWID, ))
        return self.set_from_tuple(list_tuple)

    def create(self, id_user: int, id_lesson: int):
        db_lesson: DBLesson = DBLesson(self.db_connect, id_lesson)
        cur_time = time_int()
        self.ROWID = self.db_connect.sql_execute(self.SQL_CREATE, (id_user, id_lesson, 0, cur_time, cur_time))
        self.get_id(self.ROWID)

    def delete(self):
        self.ROWID = self.db_connect.sql_execute(self.SQL_DELETE, (self.ROWID, ))

    def save(self, id_cur_slide=None, user_skill=None, control_cdate=None, control_edate=None,
             control_result=None, control_time=None, control_num_errors=None, control_list_id_slides=None,
             id_variant_click=None):
        if id_cur_slide is not None: self.id_cur_slide = id_cur_slide
        if user_skill is not None: self.user_skill = user_skill
        self.ldate = time_int()
        if control_cdate is not None: self.control_cdate = control_cdate
        if control_edate is not None: self.control_edate = control_edate
        if control_result is not None: self.control_result = control_result
        if control_time is not None: self.control_time = control_time
        if control_num_errors is not None: self.control_num_errors = control_num_errors
        if control_list_id_slides is not None: self.control_list_id_slides = control_list_id_slides
        if id_variant_click is not None: self.id_variant_click = id_variant_click

        self.db_connect.sql_execute(self.SQL_SAVE, (self.id_cur_slide, self.user_skill, self.ldate, self.control_cdate,
                self.control_edate, self.control_result, self.control_time, self.control_num_errors,
                self.control_list_id_slides, self.id_variant_click, self.ROWID))



