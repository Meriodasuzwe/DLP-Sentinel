import sys
import os
import time
import requests
import threading
import winsound
import cv2
import psutil
import telebot 
from telebot.types import ReplyKeyboardMarkup, KeyboardButton # ИМПОРТ ДЛЯ КНОПОК
import random  
import shutil 
from dotenv import load_dotenv
from datetime import datetime
import re
import sqlite3
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QFileDialog,
                             QListWidget, QListWidgetItem,
                             QGroupBox, QMessageBox, QInputDialog, QLineEdit, QCheckBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject, QSettings
from PyQt5.QtGui import QFont, QColor, QCursor, QIcon

# Загружаем переменные из .env
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
ADMIN_PIN = os.getenv("ADMIN_PIN", "1234") 
INTRUDER_FOLDER = os.getenv("INTRUDER_FOLDER", "_INTRUDERS")
QUARANTINE_FOLDER = os.getenv("QUARANTINE_FOLDER", "_QUARANTINE")
DB_NAME = os.getenv("DATABASE_NAME", "dlp_logs.db") 
EXTS_CONFIG = os.getenv("PROTECTED_EXTS", ".docx,.doc,.xlsx,.pdf,.jpg,.png,.jpeg,.txt,.exe,.bat,.py").split(",")

for folder in [INTRUDER_FOLDER, QUARANTINE_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)

# --- TELEGRAM ALERTS ---
def send_telegram_thread(message):
    if not TELEGRAM_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": f"🚨 SecureCopyGuard:\n{message}"}
    try: requests.post(url, data=data, timeout=5)
    except: pass

def send_telegram_alert(message):
    threading.Thread(target=send_telegram_thread, args=(message,), daemon=True).start()

def send_photo_thread(caption, photo_path):
    if not TELEGRAM_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    try:
        with open(photo_path, 'rb') as f:
            requests.post(url, data={'chat_id': TELEGRAM_CHAT_ID, 'caption': caption}, files={'photo': f}, timeout=15)
    except: pass

def send_telegram_photo(caption, photo_path):
    threading.Thread(target=send_photo_thread, args=(caption, photo_path), daemon=True).start()

# --- 5. TELEGRAM-АДМИНКА (КНОПОЧНАЯ ВЕРСИЯ) ---
class TelegramAdminBot(QThread):
    arm_signal = pyqtSignal()
    disarm_signal = pyqtSignal()

    def __init__(self, token, chat_id, main_window):
        super().__init__()
        self.bot = telebot.TeleBot(token)
        self.admin_chat_id = int(chat_id) if chat_id else None
        self.main_window = main_window
        self.running = True

    def run(self):
        # Функция создания клавиатуры
        def get_keyboard():
            markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
            markup.add(
                KeyboardButton("🟢 ҚОСУ"), 
                KeyboardButton("🔴 ӨШІРУ"),
                KeyboardButton("🔑 PIN-код"), 
                KeyboardButton("📊 Статус")
            )
            return markup

        @self.bot.message_handler(commands=['start', 'help'])
        def send_welcome(message):
            if message.chat.id == self.admin_chat_id:
                text = "🛡️ *Корпоративная панель DLP*\nДобро пожаловать. Выберите действие на клавиатуре ниже:"
                self.bot.reply_to(message, text, reply_markup=get_keyboard(), parse_mode='Markdown')

        # Обработка кнопок вместо текстовых команд
        @self.bot.message_handler(func=lambda message: message.text == "🟢 ҚОСУ")
        def handle_arm(message):
            if message.chat.id == self.admin_chat_id:
                if not self.main_window.monitoring_active:
                    if self.main_window.monitor_path and os.path.exists(self.main_window.monitor_path):
                        self.arm_signal.emit()
                        self.bot.reply_to(message, "✅ Команда выполнена: Защита ВКЛЮЧЕНА.", reply_markup=get_keyboard())
                    else:
                        self.bot.reply_to(message, "❌ Ошибка: Папка для защиты не настроена на ПК!", reply_markup=get_keyboard())
                else:
                    self.bot.reply_to(message, "⚠️ Защита УЖЕ включена.", reply_markup=get_keyboard())

        @self.bot.message_handler(func=lambda message: message.text == "🔴 ӨШІРУ")
        def handle_disarm(message):
            if message.chat.id == self.admin_chat_id:
                if self.main_window.monitoring_active:
                    self.disarm_signal.emit()
                    self.bot.reply_to(message, "✅ Команда выполнена: Защита ВЫКЛЮЧЕНА.", reply_markup=get_keyboard())
                else:
                    self.bot.reply_to(message, "⚠️ Защита УЖЕ выключена.", reply_markup=get_keyboard())

        @self.bot.message_handler(func=lambda message: message.text == "🔑 PIN-код")
        def handle_pin(message):
            if message.chat.id == self.admin_chat_id:
                if self.main_window.monitoring_active:
                    current_pin = self.main_window.current_otp
                    self.bot.reply_to(message, f"🔑 Одноразовый PIN: `{current_pin}`", parse_mode='Markdown', reply_markup=get_keyboard())
                else:
                    self.bot.reply_to(message, "ℹ️ Защита выключена. PIN не требуется.", reply_markup=get_keyboard())

        @self.bot.message_handler(func=lambda message: message.text == "📊 Статус")
        def handle_status(message):
            if message.chat.id == self.admin_chat_id:
                state = "🟢 АКТИВНА" if self.main_window.monitoring_active else "🔴 ОТКЛЮЧЕНА"
                folder = self.main_window.monitor_path if self.main_window.monitor_path else "Не выбрана"
                self.bot.reply_to(message, f"📊 Статус: {state}\n📁 Директория: {folder}", reply_markup=get_keyboard())

        while self.running:
            try: self.bot.polling(none_stop=True, timeout=10)
            except: time.sleep(3)

    def stop(self):
        self.running = False
        self.bot.stop_polling()

# --- ШПИОНСКИЕ МОДУЛИ ---
class SpyModule(QObject):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings

    def take_photo(self):
        if not self.settings.get('cam_enabled', False): return None
        try:
            cap = cv2.VideoCapture(0)
            if not cap.isOpened(): return None
            for _ in range(5): cap.read()
            ret, frame = cap.read()
            cap.release()
            if ret:
                filename = f"intruder_{int(time.time())}.jpg"
                path = os.path.join(INTRUDER_FOLDER, filename)
                cv2.imwrite(path, frame)
                return path
        except: pass
        return None

    def play_siren(self):
        if not self.settings.get('siren_enabled', False): return
        def siren_loop():
            for _ in range(3):
                winsound.Beep(1000, 300)
                winsound.Beep(700, 300)
        threading.Thread(target=siren_loop, daemon=True).start()

    def make_shadow_copy(self, file_path):
        try:
            if not os.path.exists(file_path): return None
            filename = os.path.basename(file_path)
            new_filename = f"shadow_{int(time.time())}_{filename}"
            dest = os.path.join(QUARANTINE_FOLDER, new_filename)
            shutil.copy2(file_path, dest) 
            return dest
        except: return None

# --- 1. МОНИТОРИНГ ФАЙЛОВ ---
class SecurityHandler(FileSystemEventHandler):
    def __init__(self, signal, exts, spy, main_window):
        self.signal = signal; self.exts = exts; self.spy = spy; self.main_window = main_window

    def _trigger_alarm(self, filename, reason, log_type):
        if not self.main_window.monitoring_active: return
        self.signal.emit(f"{reason}: {filename}", log_type)
        if self.spy.settings.get('siren_enabled', False): self.spy.play_siren()
        if self.spy.settings.get('cam_enabled', False):
            photo = self.spy.take_photo()
            if photo: send_telegram_photo(f"🚨 {reason}!\n📂 Файл: {filename}", photo)
            else: send_telegram_alert(f"🚨 {reason}!\n📂 Файл: {filename}")
        else: send_telegram_alert(f"🚨 {reason}!\n📂 Файл: {filename}")

    def on_created(self, event):
        if not self.main_window.monitoring_active or event.is_directory: return
        filename = os.path.basename(event.src_path)
        _, ext = os.path.splitext(filename)
        if filename.startswith("~$"): return
        if ext.lower() in self.exts:
            try:
                time.sleep(0.2)
                if os.path.exists(event.src_path):
                    os.remove(event.src_path)
                    self._trigger_alarm(filename, "БҰҒАТТАЛДЫ (Вброс)", "critical")
            except: pass

    def on_deleted(self, event):
        if not self.main_window.monitoring_active or event.is_directory: return
        filename = os.path.basename(event.src_path)
        if not filename.startswith("~$") and not filename.startswith("."):
             self._trigger_alarm(filename, "ФАЙЛ ЖОЙЫЛДЫ", "warning")

class FolderWatcher(QThread):
    alert = pyqtSignal(str, str)
    def __init__(self, path, exts, spy, main_window):
        super().__init__(); self.path = path; self.exts = exts; self.spy = spy; self.main_window = main_window
        self.observer = Observer()
    def run(self):
        handler = SecurityHandler(self.alert, self.exts, self.spy, self.main_window)
        self.observer.schedule(handler, self.path, recursive=True); self.observer.start()
        try:
            while self.observer.is_alive(): self.observer.join(1)
        except: self.observer.stop()
        self.observer.stop()
    def stop(self): self.observer.stop()

# --- 2. КҮШТІ БҰҒАТТАУ ---
class FileLocker:
    def __init__(self): self.locked_files = []
    def lock_folder(self, folder_path):
        self.unlock_all(); count = 0
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                try:
                    path = os.path.join(root, file); f = open(path, 'a')
                    self.locked_files.append(f); count += 1
                except: pass
        return count
    def unlock_all(self):
        for f in self.locked_files:
            try: f.close()
            except: pass
        self.locked_files = []

# --- 3. КЛИПБОРД ---
class ClipboardGuard(QObject):
    alert = pyqtSignal(str, str)
    def __init__(self, protected_path, spy, main_window):
        super().__init__(); self.protected_path = os.path.abspath(protected_path)
        self.spy = spy; self.main_window = main_window; self.clipboard = QApplication.clipboard()
        self.clipboard.dataChanged.connect(self.check_clipboard); self.last_trigger = 0

    def check_clipboard(self):
        if not self.main_window.monitoring_active: return
        if time.time() - self.last_trigger < 2: return
        mime_data = self.clipboard.mimeData()

        if mime_data.hasText() and not mime_data.hasUrls():
            text = mime_data.text()
            iin_pattern = r'\b\d{12}\b'; card_pattern = r'\b(?:\d{4}[-\s]?){4}\b'
            keywords = ['пароль', 'секретно', 'құпия', 'password']
            if re.search(iin_pattern, text) or re.search(card_pattern, text) or any(w in text.lower() for w in keywords):
                self.clipboard.clear(); self.clipboard.setText("🚫 ҚҰПИЯ ДЕРЕКТЕР БҰҒАТТАЛДЫ!")
                self.last_trigger = time.time(); self.alert.emit("МӘТІН ҰРЛЫҒЫ", "theft")
                if self.spy.settings.get('siren_enabled', False): self.spy.play_siren()
                return

        if mime_data.hasUrls():
            for url in mime_data.urls():
                local_path = url.toLocalFile()
                if local_path and os.path.abspath(local_path).startswith(self.protected_path):
                    self.clipboard.clear(); self.clipboard.setText("🚫 ФАЙЛ БҰҒАТТАЛДЫ!")
                    self.last_trigger = time.time()
                    shadow_path = self.spy.make_shadow_copy(local_path)
                    self.alert.emit(f"ҰРЛЫҚ ЖӘНЕ КАРАНТИН: {os.path.basename(local_path)}", "theft")
                    if self.spy.settings.get('siren_enabled', False): self.spy.play_siren()
                    break

# --- 4. КОНТРОЛЬ USB ---
class USBMonitor(QThread):
    alert = pyqtSignal(str, str)
    def __init__(self, spy, main_window):
        super().__init__(); self.spy = spy; self.main_window = main_window
        self.running = True; self.known_drives = self.get_removable_drives()
    def get_removable_drives(self):
        return {p.device for p in psutil.disk_partitions(all=False) if 'removable' in p.opts}
    def run(self):
        while self.running:
            if self.main_window.monitoring_active:
                current = self.get_removable_drives(); new = current - self.known_drives
                for d in new:
                    self.alert.emit(f"БЕЙТАНЫС USB: {d}", "critical")
                    if self.spy.settings.get('siren_enabled', False): self.spy.play_siren()
                self.known_drives = current
            time.sleep(2)
    def stop(self): self.running = False

# --- СТИЛЬ (НОВЫЙ КОРПОРАТИВНЫЙ ДИЗАЙН) ---
STYLESHEET = """
QMainWindow { 
    background-color: #F5F7FA; 
}
QLabel { 
    color: #2C3E50; 
    font-family: 'Segoe UI', Arial; 
    font-size: 14px; 
    font-weight: 500; 
}
QGroupBox { 
    background-color: #FFFFFF; 
    border: 1px solid #DCDFE6; 
    border-radius: 8px; 
    margin-top: 25px; 
    font-weight: bold; 
    color: #34495E; 
    font-size: 13px; 
}
QGroupBox::title { 
    subcontrol-origin: margin; 
    subcontrol-position: top left; 
    padding: 0 5px; 
    left: 15px; 
}
QPushButton { 
    background-color: #0052CC; 
    color: white; 
    border: none; 
    border-radius: 6px; 
    padding: 10px; 
    font-weight: bold; 
}
QPushButton:hover { 
    background-color: #0747A6; 
}
QPushButton#btn_start { 
    background-color: #E74C3C; 
    font-size: 16px; 
    padding: 15px;
    border-radius: 8px;
}
QPushButton#btn_start:checked { 
    background-color: #27AE60; 
}
QListWidget { 
    background-color: #FFFFFF; 
    color: #2C3E50; 
    border: 1px solid #DCDFE6; 
    border-radius: 8px; 
    font-family: 'Consolas', monospace; 
    font-size: 13px; 
    padding: 10px; 
}
QMessageBox { 
    background-color: #FFFFFF; 
    color: #2C3E50; 
}
QLineEdit { 
    background-color: #FFFFFF; 
    color: #2C3E50; 
    border: 1px solid #BDC3C7; 
    border-radius: 4px; 
    padding: 6px; 
}
QCheckBox { 
    color: #34495E; 
    spacing: 8px; 
}
"""

# --- GUI ---
class SecureCopyGuard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SecureCopyGuard v10.0 (Enterprise DLP)")
        self.resize(1000, 720)
        self.setStyleSheet(STYLESHEET)
        
        self.settings = QSettings("DLP_Project", "SecureCopyGuard")
        
        saved_path = self.settings.value("last_folder", "")
        if saved_path and os.path.exists(saved_path):
            self.monitor_path = saved_path
        else:
            self.monitor_path = ""

        self.monitoring_active = False
        self.file_locker = FileLocker()
        self.spy_settings = {'cam_enabled': False, 'siren_enabled': False}
        self.spy = SpyModule(self.spy_settings)
        self.current_otp = None 
        
        self.init_db()
        self.setup_ui()

        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            self.admin_bot = TelegramAdminBot(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, self)
            self.admin_bot.arm_signal.connect(self.remote_arm)
            self.admin_bot.disarm_signal.connect(self.remote_disarm)
            self.admin_bot.start()

    def remote_arm(self):
        if self.monitor_path:
            self.btn_run.setChecked(True)
            self.toggle(True)

    def remote_disarm(self):
        self.btn_run.setChecked(False)
        self.monitoring_active = False 
        self.shutdown_protection()

    def init_db(self):
        self.conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.cursor.execute('PRAGMA foreign_keys = ON;')

        self.cursor.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT NOT NULL, department TEXT, position TEXT)''')
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS devices (id INTEGER PRIMARY KEY AUTOINCREMENT, hostname TEXT NOT NULL, ip_address TEXT, mac_address TEXT)''')
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS policies (id INTEGER PRIMARY KEY AUTOINCREMENT, policy_name TEXT NOT NULL, threat_level TEXT NOT NULL, description TEXT)''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                user_id INTEGER,
                device_id INTEGER,
                policy_id INTEGER,
                file_path TEXT,
                details TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (device_id) REFERENCES devices (id),
                FOREIGN KEY (policy_id) REFERENCES policies (id)
            )
        ''')

        self.cursor.execute("SELECT COUNT(*) FROM users")
        if self.cursor.fetchone()[0] == 0:
            import socket
            hostname = socket.gethostname()
            self.cursor.execute("INSERT INTO users (full_name, department, position) VALUES ('Сотрудник 1', 'Бухгалтерия', 'Главный бухгалтер')")
            self.cursor.execute("INSERT INTO devices (hostname, ip_address, mac_address) VALUES (?, '192.168.1.15', '00:1A:2B:3C:4D:5E')", (hostname,))
            policies = [
                ('Device Control', 'High', 'Блокировка несанкционированных USB-накопителей'),
                ('Clipboard Guard', 'Medium', 'Перехват конфиденциальных данных в буфере обмена'),
                ('File Lock', 'High', 'Предотвращение удаления или изменения защищенных файлов')
            ]
            self.cursor.executemany("INSERT INTO policies (policy_name, threat_level, description) VALUES (?, ?, ?)", policies)
        self.conn.commit()

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main = QHBoxLayout(central)
        main.setSpacing(20); main.setContentsMargins(25,25,25,25)

        left = QVBoxLayout()
        header = QLabel("🛡️ SecureCopyGuard Enterprise")
        header.setStyleSheet("font-size: 24px; font-weight: bold; color: #0052CC;")
        header.setAlignment(Qt.AlignCenter)
        left.addWidget(header)

        g1 = QGroupBox(" 1. ЗАЩИЩАЕМАЯ ЗОНА ")
        l1 = QVBoxLayout()
        
        if self.monitor_path:
            self.lbl_path = QLabel(f"✅ {os.path.basename(self.monitor_path)}")
            self.lbl_path.setStyleSheet("color: #27AE60; font-weight: bold;")
        else:
            self.lbl_path = QLabel("📁 Папка не выбрана")
            
        self.lbl_path.setWordWrap(True)
        btn_path = QPushButton("Выбрать директорию")
        btn_path.setCursor(QCursor(Qt.PointingHandCursor))
        btn_path.clicked.connect(self.sel_folder)
        l1.addWidget(self.lbl_path); l1.addWidget(btn_path)
        g1.setLayout(l1); left.addWidget(g1)

        g2 = QGroupBox(" 2. АКТИВНЫЕ ПОЛИТИКИ ")
        l2 = QVBoxLayout()
        self.chk_doc = QCheckBox("File Lock (Защита файлов)")
        self.chk_doc.setChecked(True)
        self.chk_delete = QCheckBox("Device Control (Мониторинг USB)")
        self.chk_delete.setChecked(True)
        self.chk_cam = QCheckBox("Webcam Trap (Фото-капкан)")
        self.chk_cam.setChecked(True)
        self.chk_siren = QCheckBox("Audio Alarm (Сирена)")
        self.chk_siren.setChecked(True)
        l2.addWidget(self.chk_doc); l2.addWidget(self.chk_delete)
        l2.addWidget(self.chk_cam); l2.addWidget(self.chk_siren)
        g2.setLayout(l2); left.addWidget(g2)

        self.btn_run = QPushButton("🔴 ВСТАТЬ НА ЗАЩИТУ")
        self.btn_run.setObjectName("btn_start")
        self.btn_run.setCheckable(True)
        self.btn_run.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_run.clicked.connect(self.toggle)
        left.addStretch()
        left.addWidget(self.btn_run)
        main.addLayout(left, 35)

        right = QVBoxLayout()
        right.addWidget(QLabel("📟 ЖУРНАЛ ИНЦИДЕНТОВ (LIVE)"))
        self.logs = QListWidget()
        self.logs.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right.addWidget(self.logs)
        btns = QHBoxLayout()
        btn_clr = QPushButton("Очистить журнал")
        btn_clr.clicked.connect(self.logs.clear)
        btn_clr.setStyleSheet("background-color: #F8F9FA; color: #34495E; border: 1px solid #DCDFE6;")
        btns.addWidget(btn_clr)
        right.addLayout(btns)
        main.addLayout(right, 65)

    def sel_folder(self):
        d = QFileDialog.getExistingDirectory(self)
        if d:
            self.monitor_path = d
            self.settings.setValue("last_folder", d)
            self.lbl_path.setText(f"✅ {os.path.basename(d)}")
            self.lbl_path.setStyleSheet("color: #27AE60; font-weight: bold;")

    def toggle(self, checked):
        if checked:
            if not self.monitor_path:
                self.btn_run.setChecked(False)
                QMessageBox.warning(self, "Ошибка", "Не выбрана директория для защиты!")
                return

            self.spy_settings['cam_enabled'] = self.chk_cam.isChecked()
            self.spy_settings['siren_enabled'] = self.chk_siren.isChecked()
            self.monitoring_active = True

            self.current_otp = str(random.randint(100000, 999999))

            if self.chk_doc.isChecked(): self.file_locker.lock_folder(self.monitor_path)

            self.watchdog = FolderWatcher(self.monitor_path, EXTS_CONFIG, self.spy, self)
            self.watchdog.alert.connect(self.log)
            self.watchdog.start()

            self.clipboard_guard = ClipboardGuard(self.monitor_path, self.spy, self)
            self.clipboard_guard.alert.connect(self.log)

            self.usb_monitor = USBMonitor(self.spy, self)
            self.usb_monitor.alert.connect(self.log)
            self.usb_monitor.start()

            self.btn_run.setText("🟢 СИСТЕМА АКТИВНА")
            self.log("СИСТЕМА УСПЕШНО ЗАПУЩЕНА. ПОЛИТИКИ ПРИМЕНЕНЫ.", "system")

            self.chk_doc.setEnabled(False); self.chk_delete.setEnabled(False)
            self.chk_cam.setEnabled(False); self.chk_siren.setEnabled(False)
        else:
            pin, ok = QInputDialog.getText(self, "Аутентификация", "Введите PIN-код (OTP/Master):", QLineEdit.Password)
            
            if ok and (pin == self.current_otp or pin == ADMIN_PIN):
                self.monitoring_active = False
                self.shutdown_protection()
            else:
                self.btn_run.setChecked(True)
                QMessageBox.critical(self, "Доступ запрещен", "Неверный PIN-код!")

    def shutdown_protection(self):
        if hasattr(self, 'watchdog'): self.watchdog.terminate()
        if hasattr(self, 'clipboard_guard'):
            try: QApplication.clipboard().dataChanged.disconnect(self.clipboard_guard.check_clipboard)
            except: pass
            del self.clipboard_guard
            
        if hasattr(self, 'usb_monitor'):
            self.usb_monitor.stop()
            self.usb_monitor.wait()

        self.file_locker.unlock_all()
        self.btn_run.setText("🔴 ВСТАТЬ НА ЗАЩИТУ")
        self.log("СИСТЕМА ОТКЛЮЧЕНА АДМИНИСТРАТОРОМ.", "system")

        self.chk_doc.setEnabled(True); self.chk_delete.setEnabled(True)
        self.chk_cam.setEnabled(True); self.chk_siren.setEnabled(True)

    def log(self, msg, type="info"):
        t = datetime.now().strftime("%H:%M:%S")

        policy_id = 3
        if type == "critical": policy_id = 1
        elif type == "theft": policy_id = 2

        try:
            self.cursor.execute(
                "INSERT INTO incidents (user_id, device_id, policy_id, details) VALUES (?, ?, ?, ?)",
                (1, 1, policy_id, f"[{type.upper()}] {msg}")
            )
            self.conn.commit()
        except Exception as e:
            pass

        # Цвета логов адаптированы под светлую тему
        color = QColor("#27AE60") # Зеленый для обычных событий
        prefix = "->"
        if type == "critical": color = QColor("#C0392B"); prefix = "☠️" # Красный
        elif type == "theft": color = QColor("#D35400"); prefix = "📸" # Оранжевый
        elif type == "warning": color = QColor("#F39C12"); prefix = "⚠️" # Желтый
        elif type == "system": color = QColor("#2980B9"); prefix = "ℹ️" # Синий
        
        it = QListWidgetItem(f"[ {t} ] {prefix} {msg}")
        it.setForeground(color)
        self.logs.addItem(it)
        self.logs.scrollToBottom()

    def closeEvent(self, e):
        if self.monitoring_active:
            e.ignore()
            QMessageBox.warning(self, "Внимание", "Система активна! Для закрытия введите PIN-код.")
        else:
            if hasattr(self, 'admin_bot'): self.admin_bot.stop()
            self.file_locker.unlock_all()
            try: self.conn.close() 
            except: pass
            e.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    w = SecureCopyGuard()
    w.show()
    sys.exit(app.exec_())