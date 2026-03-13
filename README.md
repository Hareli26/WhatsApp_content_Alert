# 📱 WhatsApp Online Monitor

A Windows desktop app that monitors multiple WhatsApp contacts simultaneously and sends you a **Windows notification + Telegram message** the moment any of them come online.

No console window. Runs silently in the background.

---

## ✨ Features

- 🟢 **Real-time online detection** — polls WhatsApp Web every 3 seconds per contact
- 👥 **Multiple contacts** — monitor several people at the same time, each in a dedicated browser tab
- 🔄 **Stop & restart freely** — browser stays open between Stop/Start cycles, no re-login needed
- 🔔 **Windows balloon notification** — pops up instantly when a contact comes online
- ✈️ **Telegram bot notification** — sends a message to your Telegram
- 📱 **Google Contacts autocomplete** — import your contacts from Google for quick name lookup
- 🕓 **Recent contacts history** — one-click chips for contacts you've monitored before
- 🔇 **No CLI window** — launches as a clean GUI app, no black console
- 💾 **Persistent browser session** — WhatsApp Web stays logged in between app restarts

---

## 🖥️ Requirements

| Requirement | Details |
|---|---|
| **OS** | Windows 10 or 11 |
| **Python** | 3.8 or newer — [python.org](https://www.python.org/downloads/) |
| **WhatsApp** | Active WhatsApp account (mobile app required for first QR scan) |

---

## 🚀 Installation

### Step 1 — Install Python
Download and install Python from [python.org](https://www.python.org/downloads/).
**Make sure to check "Add Python to PATH"** during installation.

### Step 2 — Run Setup
Double-click **`setup.bat`**. It will:
1. Install the `playwright` Python package
2. Download the Chromium browser used for WhatsApp Web

### Step 3 — Launch the App
Double-click **`run.bat`** to start the app.

---

## 📖 How to Use

### Monitoring contacts

1. **Type a contact name** in the "Add contact" field and click **+ Add** (or press Enter)
2. **Add as many contacts** as you want — each will get its own browser tab
3. Click **▶ Start All** to begin monitoring
4. The app opens WhatsApp Web in the background, finds each contact's chat, and watches for the "online" status
5. The first time you run it, scan the **QR code** in the Chromium window to log in — after that it stays logged in automatically
6. When a contact comes online: you get a **Windows notification** and a **Telegram message** (if configured)
7. Click **■ Stop All** to stop monitoring — the browser stays open, so clicking Start All again is instant

### Tips for contact names

- The name must match (or be part of) how the contact appears **in WhatsApp**, not in your phone's address book
- If search fails, try a shorter version of the name (e.g. `"John"` instead of `"John Smith"`)
- Hebrew names work — make sure to type them exactly as they appear in WhatsApp

### Status indicators

| Color | Meaning |
|---|---|
| ⚫ Grey | Idle / Stopped |
| 🟡 Yellow | Starting... |
| 🔵 Cyan | Monitoring (waiting for online) |
| 🟢 Green | Online right now! |
| 🔴 Red | Error / Not found |

---

## 👤 Google Contacts Autocomplete

You can import your Google Contacts so names autocomplete as you type:

1. Go to **[contacts.google.com](https://contacts.google.com)**
2. Click **Export** → choose **vCard (.vcf)**
3. In the app, click **⚙ Settings** → **📂 Import vCard (.vcf)**
4. Select the downloaded file

Once imported, start typing in the "Add contact" field and matching names will appear as suggestions.

---

## ✈️ Telegram Notifications Setup

To receive Telegram messages when a contact comes online:

### 1. Create a Bot
1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the instructions
3. Copy the **Bot Token** you receive (looks like `123456:ABC-DEF...`)

### 2. Get Your Chat ID
1. Send **any message** to your new bot in Telegram
2. In the app, go to **⚙ Settings**
3. Paste your Bot Token, then click **Auto-detect my ID**
4. Your numeric Chat ID is filled in automatically

### 3. Save & Test
Click **Save**, then use the **✈ Test** button on the main screen to confirm everything works.

---

## 📁 File Structure

```
whatsapp_monitor/
├── app.py           # Main application
├── run.bat          # Launch the app (no console window)
├── setup.bat        # One-time installation script
├── requirements.txt # Python dependencies
├── config.json      # Auto-created: saves your Telegram settings & contact history
└── wa_session/      # Auto-created: stores WhatsApp Web login session
```

> **`config.json`** and **`wa_session/`** are created automatically on first run. Do not share them — they contain your session data.

---

## ❓ Troubleshooting

### "Contact not found"
- Make sure the name **matches** (fully or partially) how it appears in WhatsApp
- The contact must have an **existing chat** with you in WhatsApp
- Try a shorter partial name (e.g. `"John"` instead of `"John Smith"`)
- The app tries 3 different search strategies automatically, including the WhatsApp search box

### Only some contacts are found
- Each contact gets its own browser tab — the app searches them one by one
- If a contact is "Not found" but others work, check the exact spelling in WhatsApp
- Click **Stop All** then **Start All** to retry all contacts

### WhatsApp Web QR code keeps appearing
- Delete the **`wa_session/`** folder and re-scan the QR code

### Telegram "Chat not found" error
- Your **Chat ID must be a number** (e.g. `123456789`), not your username or bot name
- Use the **Auto-detect my ID** button after sending a message to your bot

### App doesn't open (no window appears)
- Make sure Python is installed and in PATH
- Try running `python app.py` from a terminal to see any error messages
- Run `setup.bat` again to ensure all dependencies are installed

### Stop All → Start All doesn't work
- This is fixed in the current version — the browser thread stays alive between cycles
- If you see "Browser launch error", close the app and restart it once

---

## 🔒 Privacy

- The app runs **entirely on your machine** — no data is sent anywhere except to Telegram (if you configure it)
- WhatsApp Web is opened in a local Chromium browser using your own session
- Your credentials and session data are stored only in the local `config.json` and `wa_session/` folder

---

## 📦 Dependencies

| Package | Purpose |
|---|---|
| `playwright` | Controls the Chromium browser for WhatsApp Web |

All other features use Python's built-in standard library (tkinter, urllib, threading, queue, etc.).
