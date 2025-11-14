# 📚 Study Lock — Modern Productivity & Distraction Blocker

Study Lock is a polished productivity tool built with **PyQt5**, designed to keep you focused with a modern glass UI, a robust Pomodoro system, smart blocking, statistics, and a distraction‑free workflow.

This README documents the features, UI, build instructions, and usage.

## ✨ Features

### ✔ Pomodoro Timer System
- Customizable work & break durations  
- Auto long breaks after defined cycles  
- Pause / Resume / Stop / Skip break  
- Smooth animations & modern UI  

### ✔ Website & App Blocking (Windows)
- Blocks websites using hosts file  
- Kills selected applications (Steam, VLC, etc.)  
- Blocking stops automatically when daily goal is completed

### ✔ Emergency Override
- Password-protected  
- Temporarily unblocks all restrictions  
- Automatically reverts after override duration  

### ✔ Mini Floating Timer
- Always-on-top  
- Movable widget  
- Shows remaining time in real‑time  

### ✔ Statistics & Charts
- Work vs Break chart for the last 7 days  
- All sessions saved in persistent history  

### ✔ Tray Integration
- Start / Pause / Show Window / Quit  
- Live tooltip updater  
- Notifications during sessions  

### ✔ Persistent Data
- Saves daily minutes  
- Saves paused session state  
- Saves weekly history  
- Saves configurations automatically  

---

## 🚀 Running the Application

### 1. Install Required Libraries

```
pip install PyQt5 psutil win10toast matplotlib
```

### 2. Run the app

```
python study_lock.py
```

> ⚠ **For blocking features**, run as **Administrator**.

---

## 🧱 Project Structure

```
Study-Lock/
│
├── study_lock.py
├── build.bat
├── study_lock.ico
├── bell.wav
├── README.md
│
├── study_lock_config.json
├── study_lock_state.json
├── study_lock_sessions.json
└── images/
      mini_timer.png
      stats.png
      dashboard.png
      pomodoro.png
      settings.png
      override.png
```

---

## ⚙ Build Instructions (Windows EXE)

You already have a fully working build script.

### `build.bat`

```
@echo off
pyinstaller --noconfirm --onefile --windowed ^
--icon=study_lock.ico ^
--add-data "bell.wav;." ^
study_lock.py
```

### Build:

```
build.bat
```

The EXE will be located in:

```
dist/study_lock.exe
```

---

## 🛠 Dependencies

| Library | Purpose |
|--------|---------|
| PyQt5 | UI framework |
| psutil | Process killer |
| win10toast | Notifications |
| matplotlib | Charts |

---

## 📄 License

MIT License.

---

## 🙌 Credits

Created by **FlamerFx**  
Crafted with PyQt5  
