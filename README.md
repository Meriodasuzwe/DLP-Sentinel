# 🛡️ SecureCopyGuard: Enterprise-Grade DLP Agent

**SecureCopyGuard** is a sophisticated Data Loss Prevention (DLP) solution designed to protect sensitive information from unauthorized access and exfiltration. Built with a focus on **Enterprise Security**, it combines real-time file system monitoring, peripheral control, and remote management through an AI-integrated Telegram MDM (Mobile Device Management) interface.

---

## 🚀 Key Features

* **Real-time File Protection:** Prevents unauthorized modification or deletion of sensitive documents using low-level file locking.
* **Shadow Copy & Forensic Quarantine:** Automatically creates encrypted-like shadow copies of exfiltrated data for digital forensic investigations.
* **Peripheral & USB Control:** Instant detection and logging of unauthorized removable media connections.
* **Clipboard Guard:** Content-aware filtering for sensitive patterns like IDs, credit card numbers, and custom keywords.
* **Telegram MDM Integration:** Full remote control via a button-based Telegram interface (Arm/Disarm, Status, OTP request).
* **2FA Authentication:** Implements One-Time Passwords (OTP) generated in real-time to prevent unauthorized local disarmament.
* **Webcam Trap:** Captures high-definition photos of intruders upon security breach detection.
* **Persistent Logging:** Full audit trail stored in a structured SQLite database.

---

## 🛠️ Tech Stack

* **Language:** Python 3.13
* **GUI:** PyQt5 (Enterprise Light Theme)
* **Monitoring:** Watchdog (File System), Psutil (Hardware)
* **Security:** OpenCV (Vision), Telebot (Telegram API), Cryptography principles
* **Database:** SQLite3

---

## 📦 Installation & Setup

1. **Clone the repository:**
```bash
git clone https://github.com/yourusername/SecureCopyGuard.git
cd SecureCopyGuard

```


2. **Install dependencies:**
```bash
pip install -r requirements.txt

```


3. **Configure Environment Variables:**
Create a `.env` file in the root directory based on `.env.example`:
```env
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
ADMIN_PIN=1234

```


4. **Run the Application:**
```bash
python monitor.py

```



---

## 🛡️ Forensic Evidence Collection

The system is designed to provide actionable evidence for security audits:

* **`_INTRUDERS/`**: Contains visual evidence (photos) of policy violators.
* **`_QUARANTINE/`**: Contains shadow copies of files that were attempted to be copied or moved.
* **`dlp_logs.db`**: A complete SQL-queryable history of all security incidents.

---

## 🖥️ UI Design

The interface follows a **Strict Corporate Style**, optimized for Security Operations Centers (SOC):

* **Clean Light Theme**: Focused on readability and data visualization.
* **Real-time Live Logs**: Instant feedback on system state and policy hits.

---

## ⚠️ Disclaimer

*This software is developed for educational purposes as part of a University Diploma Project. Unauthorized use of this tool for malicious activities is strictly prohibited and remains the sole responsibility of the user.*

---

## 👨‍💻 Author

**Rakhat (Information Security Student)**

* Focus: Backend Development & Cyber Security
* Status: 4th Year Student

