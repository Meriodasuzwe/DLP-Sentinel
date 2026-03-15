import sys
import os
import time
import requests
import threading
import winsound  
import cv2       
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
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QColor, QCursor

# Загружаем переменные из .env
load_dotenv()

# Теперь достаем их через os.getenv
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
ADMIN_PIN = os.getenv("ADMIN_PIN", "1234")
INTRUDER_FOLDER = os.getenv("INTRUDER_FOLDER", "_INTRUDERS")

if not os.path.exists(INTRUDER_FOLDER):
    os.makedirs(INTRUDER_FOLDER)

# --- TELEGRAM ---
def send_telegram_thread(message):
    if not TELEGRAM_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": f"🚨 SecureCopyGuard:\n{message}"}
    try: 
        requests.post(url, data=data, timeout=5)
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

# --- 1. МОНИТОРИНГ ---
class SecurityHandler(FileSystemEventHandler):
    def __init__(self, signal, exts, spy, main_window):
        self.signal = signal
        self.exts = exts
        self.spy = spy
        self.main_window = main_window

    def _trigger_alarm(self, filename, reason, log_type):
        if not self.main_window.monitoring_active: return # Блокталған болса орындамаймыз

        self.signal.emit(f"{reason}: {filename}", log_type)
        
        # Сирена
        if self.spy.settings.get('siren_enabled', False):
            self.spy.play_siren()
        
        # Фото + Телеграм
        if self.spy.settings.get('cam_enabled', False):
            photo = self.spy.take_photo()
            if photo:
                send_telegram_photo(f"🚨 {reason}!\n📂 Файл: {filename}\n📸 Фото нарушителя:", photo)
            else:
                send_telegram_alert(f"🚨 {reason}!\n📂 Файл: {filename}\n(Камера жоқ)")
        else:
            send_telegram_alert(f"🚨 {reason}!\n📂 Файл: {filename}")

    def on_created(self, event):
        if not self.main_window.monitoring_active: return
        if event.is_directory: return
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
        if not self.main_window.monitoring_active: return
        if event.is_directory: return
        filename = os.path.basename(event.src_path)
        if not filename.startswith("~$") and not filename.startswith("."):
             self._trigger_alarm(filename, "ФАЙЛ ЖОЙЫЛДЫ", "warning")

class FolderWatcher(QThread):
    alert = pyqtSignal(str, str)
    def __init__(self, path, exts, spy, main_window):
        super().__init__()
        self.path = path
        self.exts = exts
        self.spy = spy
        self.main_window = main_window
        self.observer = Observer()
    def run(self):
        handler = SecurityHandler(self.alert, self.exts, self.spy, self.main_window)
        self.observer.schedule(handler, self.path, recursive=True)
        self.observer.start()
        try:
            while self.observer.is_alive(): self.observer.join(1)
        except: self.observer.stop()
        self.observer.stop()
    def stop(self): self.observer.stop()

# --- 2. КҮШТІ БҰҒАТТАУ (ANTI-OPEN) ---
class FileLocker:
    def __init__(self):
        self.locked_files = []
    
    def lock_folder(self, folder_path):
        self.unlock_all()
        count = 0
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                try:
                    path = os.path.join(root, file)
                    # Файлды 'append' режимінде ашып тастаймыз.
                    # Бұл режимде Windows файлды басқа программаларға (Word, Excel) ашқызбайды.
                    f = open(path, 'a') 
                    self.locked_files.append(f)
                    count += 1
                except: pass
        return count

    def unlock_all(self):
        # Барлық файлдарды жабамыз
        for f in self.locked_files:
            try: f.close()
            except: pass
        self.locked_files = []

# --- 3. КЛИПБОРД ---
class ClipboardGuard(QObject):
    alert = pyqtSignal(str, str)
    
    def __init__(self, protected_path, spy, main_window):
        super().__init__()
        self.protected_path = os.path.abspath(protected_path)
        self.spy = spy
        self.main_window = main_window 
        self.clipboard = QApplication.clipboard()
        self.clipboard.dataChanged.connect(self.check_clipboard)
        self.last_trigger = 0

    def check_clipboard(self):
        # ЕГЕР ҚОРҒАНЫС ӨШІРУЛІ БОЛСА - ЕШТЕҢЕ ІСТЕМЕЙМІЗ
        if not self.main_window.monitoring_active: return

        if time.time() - self.last_trigger < 2: return
        
        mime_data = self.clipboard.mimeData()
        
        # --- 1. ТЕКСТТІК КОНТЕНТТІ ТЕКСЕРУ (DLP Content Analysis) ---
        if mime_data.hasText() and not mime_data.hasUrls():
            text = mime_data.text()
            # Паттерндер: 12 сан (ИИН/БИН), 16 сан (Карта), кілт сөздер
            iin_pattern = r'\b\d{12}\b' 
            card_pattern = r'\b(?:\d{4}[-\s]?){4}\b' 
            keywords = ['пароль', 'секретно', 'құпия', 'password']
            
            is_sensitive = False
            if re.search(iin_pattern, text): is_sensitive = True
            elif re.search(card_pattern, text): is_sensitive = True
            elif any(w in text.lower() for w in keywords): is_sensitive = True
            
            if is_sensitive:
                self.clipboard.clear()
                self.clipboard.setText("🚫 БҰҒАТТАЛДЫ: Құпия деректер (ИИН/Карта/Сыр) көшіруге тыйым салынған!")
                self.last_trigger = time.time()
                self.alert.emit("МӘТІН ҰРЛЫҒЫ: Құпия деректер", "theft")
                
                if self.spy.settings.get('siren_enabled', False):
                    self.spy.play_siren()
                if self.spy.settings.get('cam_enabled', False):
                    photo = self.spy.take_photo()
                    if photo: send_telegram_photo("🕵️‍♂️ МӘТІН ҰРЛЫҒЫ!\nҚұпия мәтін көшірілді.", photo)
                    else: send_telegram_alert("🕵️‍♂️ МӘТІН ҰРЛЫҒЫ!\nҚұпия мәтін көшірілді.")
                else:
                    send_telegram_alert("🕵️‍♂️ МӘТІН ҰРЛЫҒЫ!\nҚұпия мәтін көшірілді.")
                return

        # --- 2. ФАЙЛДАРДЫ ТЕКСЕРУ ---
        if mime_data.hasUrls():
            urls = mime_data.urls()
            for url in urls:
                local_path = url.toLocalFile()
                if local_path:
                    abs_path = os.path.abspath(local_path)
                    if abs_path.startswith(self.protected_path):
                        filename = os.path.basename(abs_path)
                        
                        # 1. Буферді тазалау
                        self.clipboard.clear()
                        self.clipboard.setText(f"🚫 БҰҒАТТАЛДЫ: {filename}")
                        self.last_trigger = time.time()
                        self.alert.emit(f"ҰРЛЫҚ ТОҚТАТЫЛДЫ: {filename}", "theft")
                        
                        # 2. ДАБЫЛ ЖӘНЕ ФОТО (Тікелей шақырамыз)
                        if self.spy.settings.get('siren_enabled', False):
                            self.spy.play_siren()

                        if self.spy.settings.get('cam_enabled', False):
                            photo = self.spy.take_photo()
                            if photo:
                                send_telegram_photo(f"🕵️‍♂️ ҰРЛЫҚ ӘРЕКЕТІ!\nФайл: {filename}", photo)
                            else:
                                send_telegram_alert(f"🕵️‍♂️ ҰРЛЫҚ ӘРЕКЕТІ!\nФайл: {filename}")
                        else:
                             send_telegram_alert(f"🕵️‍♂️ ҰРЛЫҚ ӘРЕКЕТІ!\nФайл: {filename}")
                        
                        break

# --- СТИЛЬ ---
STYLESHEET = """
QMainWindow { background-color: #1a1b26; }
QLabel { color: #a9b1d6; font-family: 'Segoe UI'; font-size: 14px; font-weight: 500; }
QGroupBox { background-color: #24283b; border: 1px solid #414868; border-radius: 10px; margin-top: 25px; font-weight: bold; color: #7aa2f7; font-size: 13px; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 10px; left: 15px; }
QPushButton { background-color: #3d59a1; color: white; border: none; border-radius: 8px; padding: 12px; font-weight: bold; }
QPushButton:hover { background-color: #7aa2f7; margin-top: -2px; }
QPushButton#btn_start { background-color: #f7768e; border: 2px solid #f7768e; font-size: 15px; }
QPushButton#btn_start:checked { background-color: #9ece6a; border-color: #9ece6a; color: #1a1b26; }
QListWidget { background-color: #0f0f14; color: #00ff00; border: 1px solid #414868; border-radius: 10px; font-family: 'Consolas'; font-size: 12px; padding: 10px; }
QMessageBox { background-color: #24283b; color: white; }
QLineEdit { background-color: #1a1b26; color: white; border: 1px solid #7aa2f7; border-radius: 5px; padding: 5px; }
QCheckBox { color: #c0caf5; spacing: 8px; }
"""

# --- GUI ---
class SecureCopyGuard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SecureCopyGuard v9.1 (Final)")
        self.resize(1000, 720)
        self.setStyleSheet(STYLESHEET)
        self.monitor_path = ""
        self.monitoring_active = False # БАСТЫ ТУМБЛЕР
        self.file_locker = FileLocker()
        self.spy_settings = {'cam_enabled': False, 'siren_enabled': False}
        self.spy = SpyModule(self.spy_settings) 
        self.init_db()
        self.setup_ui()

    def init_db(self):
        # Подключаемся к базе
        self.conn = sqlite3.connect("dlp_logs.db", check_same_thread=False)
        self.cursor = self.conn.cursor()

        # Включаем поддержку внешних ключей в SQLite
        self.cursor.execute('PRAGMA foreign_keys = ON;')

        # 1. Таблица Сотрудников (users)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                department TEXT,
                position TEXT
            )
        ''')

        # 2. Таблица Рабочих станций (devices)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hostname TEXT NOT NULL,
                ip_address TEXT,
                mac_address TEXT
            )
        ''')

        # 3. Таблица Политик безопасности (policies)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS policies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                policy_name TEXT NOT NULL,
                threat_level TEXT NOT NULL,
                description TEXT
            )
        ''')

        # 4. Главная таблица Инцидентов (incidents) - связи один-ко-многим
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

        # --- ЗАПОЛНЕНИЕ БАЗОВЫМИ ДАННЫМИ (Mock Data для диплома) ---
        # Чтобы на защите таблицы не были пустыми, сразу закидываем туда "дефолтные" значения
        self.cursor.execute("SELECT COUNT(*) FROM users")
        if self.cursor.fetchone()[0] == 0:
            # Создаем фейкового сотрудника и комп
            import socket
            hostname = socket.gethostname()
            
            self.cursor.execute("INSERT INTO users (full_name, department, position) VALUES ('Сотрудник 1', 'Бухгалтерия', 'Главный бухгалтер')")
            self.cursor.execute("INSERT INTO devices (hostname, ip_address, mac_address) VALUES (?, '192.168.1.15', '00:1A:2B:3C:4D:5E')", (hostname,))
            
            # Создаем 3 правила безопасности
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
        main.setSpacing(20); main.setContentsMargins(20,20,20,20)

        left = QVBoxLayout()
        header = QLabel("🛡️ SecureCopyGuard")
        header.setStyleSheet("font-size: 26px; font-weight: bold; color: #7aa2f7;")
        header.setAlignment(Qt.AlignCenter)
        left.addWidget(header)

        g1 = QGroupBox(" 1. ҚОРҒАЛАТЫН АЙМАҚ ")
        l1 = QVBoxLayout()
        self.lbl_path = QLabel("📁 Папка таңдалмаған")
        self.lbl_path.setWordWrap(True)
        btn_path = QPushButton("Папканы таңдау")
        btn_path.setCursor(QCursor(Qt.PointingHandCursor))
        btn_path.clicked.connect(self.sel_folder)
        l1.addWidget(self.lbl_path); l1.addWidget(btn_path)
        g1.setLayout(l1); left.addWidget(g1)

        g2 = QGroupBox(" 2. БЕЛСЕНДІ ҚАРСЫ ТҰРУ ")
        l2 = QVBoxLayout()
        self.chk_doc = QCheckBox("Файлдарды қорғау (Word, PDF, JPG)")
        self.chk_doc.setChecked(True)
        self.chk_delete = QCheckBox("Өшіруден қорғау (File Lock)")
        self.chk_delete.setChecked(True)
        self.chk_delete.setStyleSheet("color: #ff9e64; font-weight: bold;")
        self.chk_cam = QCheckBox("📸 Фото-қақпан (Webcam Trap)")
        self.chk_cam.setChecked(True)
        self.chk_cam.setStyleSheet("color: #bb9af7; font-weight: bold;")
        self.chk_siren = QCheckBox("🔊 Дабыл Сиренасы (Audio Alarm)")
        self.chk_siren.setChecked(True)
        self.chk_siren.setStyleSheet("color: #f7768e; font-weight: bold;")
        l2.addWidget(self.chk_doc); l2.addWidget(self.chk_delete)
        l2.addWidget(self.chk_cam); l2.addWidget(self.chk_siren)
        g2.setLayout(l2); left.addWidget(g2)

        self.btn_run = QPushButton("🔴 ҚОРҒАНЫСТЫ ҚОСУ")
        self.btn_run.setObjectName("btn_start")
        self.btn_run.setCheckable(True)
        self.btn_run.setFixedHeight(60)
        self.btn_run.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_run.clicked.connect(self.toggle)
        left.addStretch()
        left.addWidget(self.btn_run)
        main.addLayout(left, 35)

        right = QVBoxLayout()
        right.addWidget(QLabel("📟 LIVE LOGS"))
        self.logs = QListWidget()
        self.logs.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right.addWidget(self.logs)
        btns = QHBoxLayout()
        btn_clr = QPushButton("Тазалау")
        btn_clr.clicked.connect(self.logs.clear)
        btn_clr.setStyleSheet("background-color: #24283b; border: 1px solid #414868;")
        btns.addWidget(btn_clr)
        right.addLayout(btns)
        main.addLayout(right, 65)

    def sel_folder(self):
        d = QFileDialog.getExistingDirectory(self)
        if d: 
            self.monitor_path = d
            self.lbl_path.setText(f"✅ {os.path.basename(d)}")
            self.lbl_path.setStyleSheet("color: #9ece6a; font-weight: bold;")

    def get_exts(self):
        return ['.docx', '.doc', '.xlsx', '.pdf', '.jpg', '.png', '.jpeg', '.txt', '.exe', '.bat', '.py']

    def toggle(self, checked):
        if checked:
            if not self.monitor_path:
                self.btn_run.setChecked(False)
                QMessageBox.warning(self, "Қате", "Папканы таңдаңыз!")
                return
            
            self.spy_settings['cam_enabled'] = self.chk_cam.isChecked()
            self.spy_settings['siren_enabled'] = self.chk_siren.isChecked()
            self.monitoring_active = True 

            if self.chk_delete.isChecked(): self.file_locker.lock_folder(self.monitor_path)
            
            self.watchdog = FolderWatcher(self.monitor_path, self.get_exts(), self.spy, self)
            self.watchdog.alert.connect(self.log)
            self.watchdog.start()
            
            self.clipboard_guard = ClipboardGuard(self.monitor_path, self.spy, self)
            self.clipboard_guard.alert.connect(self.log)
            
            self.btn_run.setText("🟢 ҚОРҒАНЫС БЕЛСЕНДІ")
            self.log("SYSTEM ARMED. TRAPS SET.", "system")
            
            self.chk_doc.setEnabled(False); self.chk_delete.setEnabled(False)
            self.chk_cam.setEnabled(False); self.chk_siren.setEnabled(False)
        else:
            pin, ok = QInputDialog.getText(self, "Admin", "PIN-код:", QLineEdit.Password)
            if ok and pin == ADMIN_PIN:
                self.monitoring_active = False 

                if hasattr(self, 'watchdog'): self.watchdog.terminate()
                if hasattr(self, 'clipboard_guard'):
                    try: QApplication.clipboard().dataChanged.disconnect(self.clipboard_guard.check_clipboard)
                    except: pass
                    del self.clipboard_guard
                
                self.file_locker.unlock_all()
                self.btn_run.setText("🔴 ҚОРҒАНЫСТЫ ҚОСУ")
                self.log("SYSTEM DISARMED.", "system")
                
                self.chk_doc.setEnabled(True); self.chk_delete.setEnabled(True)
                self.chk_cam.setEnabled(True); self.chk_siren.setEnabled(True)
            else:
                self.btn_run.setChecked(True)
                QMessageBox.critical(self, "Error", "PIN қате!")

    def log(self, msg, type="info"):
        t = datetime.now().strftime("%H:%M:%S")
        
        # Сохраняем логи в базу данных (SQLite)
        try:
            self.cursor.execute("INSERT INTO incidents (timestamp, event_type, description) VALUES (?, ?, ?)", (t, type, msg))
            self.conn.commit()
        except: pass

        color = QColor("#9ece6a")
        prefix = "->"
        if type == "critical": color = QColor("#f7768e"); prefix = "☠️"
        elif type == "theft": color = QColor("#ff9e64"); prefix = "📸"
        elif type == "warning": color = QColor("#e0af68"); prefix = "⚠️"
        elif type == "system": color = QColor("#7aa2f7"); prefix = "ℹ️"
        it = QListWidgetItem(f"[ {t} ] {prefix} {msg}")
        it.setForeground(color)
        self.logs.addItem(it)
        self.logs.scrollToBottom()

    def closeEvent(self, e):
        if self.monitoring_active:
            e.ignore()
            QMessageBox.warning(self, "Warning", "Жүйе қосулы! PIN-код арқылы өшіріңіз.")
        else:
            self.file_locker.unlock_all()
            e.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    w = SecureCopyGuard()
    w.show()
    sys.exit(app.exec_())