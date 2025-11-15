#!/usr/bin/env python3
"""
Features: Pomodoro, hosts blocking, process killer, override, settings, notifications, 
          persistence, system tray, mini floating timer, custom cycle durations, 
          break skip, session charts, completion sounds.
          
Run as Administrator to enable hosts editing & process-killing features.
Requires: PyQt5 psutil win10toast matplotlib
"""

import sys, os, time, json, shutil, hashlib, threading, ctypes, atexit, tempfile
from datetime import datetime, timedelta
from PyQt5.QtCore import QRectF

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QPushButton, QLabel, QProgressBar, QListWidget, QLineEdit, QComboBox,
    QSpinBox, QMessageBox, QFormLayout, QInputDialog, QGraphicsOpacityEffect, 
    QGraphicsDropShadowEffect, QSystemTrayIcon, QMenu, QAction, QCheckBox
)
from PyQt5.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, pyqtProperty, 
    pyqtSignal, QObject, QSettings
)
from PyQt5.QtGui import QColor, QPainter, QBrush, QPainterPath, QIcon
from PyQt5.QtMultimedia import QSound

# ----------------------------
# Optional dependencies
# ----------------------------
try:
    import psutil
except ImportError:
    psutil = None

try:
    from win10toast import ToastNotifier
except ImportError:
    ToastNotifier = None

try:
    import matplotlib
    matplotlib.use('Qt5Agg')
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    import matplotlib.pyplot as plt
    CHARTS_AVAILABLE = True
except ImportError:
    CHARTS_AVAILABLE = False

def resource_path(relative_path):
    import sys, os
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# ----------------------------
# Custom Dialog Helper (Fix for PyInstaller button issue)
# ----------------------------
def show_question_dialog(parent, title, message, buttons=None):
    """
    Custom question dialog that works in PyInstaller.
    Returns: 0=No/Cancel, 1=Yes/OK, 2=Third option
    """
    from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
    from PyQt5.QtCore import Qt
    
    if buttons is None:
        buttons = ["Yes", "No"]
    
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setModal(True)
    dialog.setMinimumWidth(400)
    dialog.setFixedHeight(180)
    dialog.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
    
    layout = QVBoxLayout(dialog)
    layout.setSpacing(15)
    layout.setContentsMargins(25, 25, 25, 25)
    
    # Message
    label = QLabel(message)
    label.setStyleSheet("font-size: 14px; color: #ffffff;")
    label.setAlignment(Qt.AlignCenter)
    label.setWordWrap(True)
    layout.addWidget(label)
    
    layout.addSpacing(10)
    
    # Buttons
    btn_layout = QHBoxLayout()
    btn_layout.setSpacing(10)
    
    button_widgets = []
    colors = ["#007bff", "#28a745", "#dc3545", "#6c757d"]
    
    for idx, btn_text in enumerate(buttons):
        btn = QPushButton(btn_text)
        btn.setMinimumHeight(40)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {colors[idx % len(colors)]};
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 13px;
                font-weight: bold;
                padding: 8px 20px;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
        """)
        btn.clicked.connect(lambda checked, i=idx: dialog.done(i))
        btn_layout.addWidget(btn)
        button_widgets.append(btn)
    
    layout.addLayout(btn_layout)
    
    dialog.setStyleSheet("""
        QDialog {
            background-color: #2b2b2b;
            border: 2px solid #444;
            border-radius: 10px;
        }
    """)
    
    return dialog.exec_()

def show_info_dialog(parent, title, message):
    """Simple info dialog."""
    from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton
    from PyQt5.QtCore import Qt
    
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setModal(True)
    dialog.setMinimumWidth(350)
    dialog.setFixedHeight(150)
    dialog.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
    
    layout = QVBoxLayout(dialog)
    layout.setSpacing(15)
    layout.setContentsMargins(25, 25, 25, 25)
    
    label = QLabel(message)
    label.setStyleSheet("font-size: 13px; color: #ffffff;")
    label.setAlignment(Qt.AlignCenter)
    label.setWordWrap(True)
    layout.addWidget(label)
    
    btn = QPushButton("OK")
    btn.setMinimumHeight(35)
    btn.setStyleSheet("""
        QPushButton {
            background: #007bff;
            color: white;
            border: none;
            border-radius: 5px;
            font-size: 13px;
            font-weight: bold;
            padding: 8px 30px;
        }
        QPushButton:hover {
            background: #0056b3;
        }
    """)
    btn.clicked.connect(dialog.accept)
    layout.addWidget(btn, alignment=Qt.AlignCenter)
    
    dialog.setStyleSheet("""
        QDialog {
            background-color: #2b2b2b;
            border: 2px solid #444;
            border-radius: 10px;
        }
    """)
    
    dialog.exec_()

def show_warning_dialog(parent, title, message):
    """Simple warning dialog."""
    show_info_dialog(parent, title, f"⚠️ {message}")

# ----------------------------
# Config
# ----------------------------
DEFAULT_CONFIG = {
    "daily_required_minutes": 300,
    "pomodoro_work_min": 50,
    "pomodoro_break_min": 10,
    "long_break_min": 30,
    "long_break_after_cycles": 3,
    "blocked_apps": ["vlc.exe", "mpv.exe", "steam.exe"],
    "blocked_sites": [
        "x.com", "www.x.com",
        "twitter.com", "www.twitter.com",
        "mangafire.to", "www.mangafire.to",
        "reddit.com", "www.reddit.com"
    ],
    "hosts_path": r"C:\Windows\System32\drivers\etc\hosts",
    "hosts_backup": r"C:\Windows\System32\drivers\etc\hosts.study_lock_backup",
    "hosts_block_marker": "# STUDY_LOCK_BLOCK_START",
    "hosts_block_end_marker": "# STUDY_LOCK_BLOCK_END",
    "hosts_ip": "127.0.0.1",
    "override_minutes": 15,
    "override_password_hash": "f4faff209c72dc8e85869d39231f0d03a1987d197807c05afcf7c4e54bd9867d",
    "sound_enabled": True,
    "mini_timer_enabled": False
}

_OVERRIDE_SALT = "study_lock_salt_v1"

# ----------------------------
# Data file paths
# ----------------------------
def get_app_data_dir():
    """
    Get directory for storing application data.
    Uses the same directory as the EXE/script.
    """
    if getattr(sys, 'frozen', False):
        # Running as EXE - use EXE directory
        app_dir = os.path.dirname(sys.executable)
    else:
        # Running as script - use script directory
        app_dir = os.path.dirname(os.path.abspath(__file__))
    
    return app_dir

# Call it immediately
APP_DIR = get_app_data_dir()

STATE_FILE = os.path.join(APP_DIR, "study_lock_state.json")
PAUSE_FILE = os.path.join(APP_DIR, "study_lock_pause.json")
CFG_FILE = os.path.join(APP_DIR, "study_lock_config.json")
LOG_FILE = os.path.join(APP_DIR, "study_lock_log.txt")
SESSIONS_FILE = os.path.join(APP_DIR, "study_lock_sessions.json")


state_lock = threading.Lock()

# Notifications
toaster = ToastNotifier() if ToastNotifier else None

def notify(title, msg, duration=5):
    """Show desktop notification with fallback."""
    try:
        if toaster:
            toaster.show_toast(title, msg, duration=duration, threaded=True)
        else:
            safe_log("NOTIFY", f"{title}: {msg}")
    except Exception as e:
        safe_log("NOTIFY_ERROR", str(e))

# ----------------------------
# Sound helper
# ----------------------------
def play_completion_sound():
    """Play notification sound on session completion."""
    try:
        # Try to find bell.wav in current directory
        sound_file = resource_path("bell.wav")
        if os.path.exists(sound_file):
            QSound.play(sound_file)
        else:
            # Use system beep as fallback
            QApplication.beep()
    except Exception as e:
        safe_log("SOUND_ERROR", str(e))

# ----------------------------
# Session history helper
# ----------------------------
def save_session_history(session_type, duration_min, completed=True):
    """Save completed session to history."""
    try:
        history = []
        if os.path.exists(SESSIONS_FILE):
            with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        
        session = {
            "timestamp": datetime.now().isoformat(),
            "type": session_type,  # "work", "break", "long_break"
            "duration": duration_min,
            "completed": completed,
            "date": datetime.now().strftime("%Y-%m-%d")
        }
        
        history.append(session)
        
        # Keep last 1000 sessions
        if len(history) > 1000:
            history = history[-1000:]
        
        with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
            
    except Exception as e:
        safe_log("SESSION_HISTORY_ERROR", str(e))

def load_session_history():
    """Load session history."""
    try:
        if os.path.exists(SESSIONS_FILE):
            with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        safe_log("SESSION_LOAD_ERROR", str(e))
    return []

# ----------------------------
# Admin helper
# ----------------------------
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False

def safe_log(kind, note=""):
    """Thread-safe logging."""
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} - {kind} - {note}\n")
    except Exception:
        pass

# ----------------------------
# Thread-safe signal emitter
# ----------------------------
class ThreadSignals(QObject):
    """Signals for thread-safe GUI updates."""
    override_update = pyqtSignal(str, bool)

# ----------------------------
# Load/save config & state
# ----------------------------
def load_config():
    cfg = DEFAULT_CONFIG.copy()
    if os.path.exists(CFG_FILE):
        try:
            with open(CFG_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                cfg.update(loaded)
        except Exception as e:
            safe_log("CONFIG_LOAD_ERROR", str(e))
    return cfg

def save_config(cfg):
    try:
        with open(CFG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        safe_log("CONFIG_SAVE_ERROR", str(e))

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        safe_log("STATE_LOAD_ERROR", str(e))
        return {}

def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        safe_log("STATE_SAVE_ERROR", str(e))

def initialize_state():
    s = load_state()
    today = datetime.now().strftime("%Y-%m-%d")
    if s.get("date") != today:
        prev = s.get("date")
        if prev:
            week = s.get("weekly_minutes", {})
            week[prev] = s.get("minutes_today", 0)
            s["weekly_minutes"] = week
        s["date"] = today
        s["minutes_today"] = 0
    if "weekly_minutes" not in s:
        s["weekly_minutes"] = {}
    return s

# ----------------------------
# Pause helpers
# ----------------------------
def save_pause(elapsed, total, in_break):
    try:
        with open(PAUSE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "saved_at": time.time(),
                "elapsed": elapsed,
                "total": total,
                "in_break": in_break
            }, f)
    except Exception as e:
        safe_log("PAUSE_SAVE_ERROR", str(e))

def load_pause():
    if not os.path.exists(PAUSE_FILE):
        return None
    try:
        with open(PAUSE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        safe_log("PAUSE_LOAD_ERROR", str(e))
        return None

def clear_pause():
    try:
        if os.path.exists(PAUSE_FILE):
            os.remove(PAUSE_FILE)
    except Exception as e:
        safe_log("PAUSE_CLEAR_ERROR", str(e))

# ----------------------------
# Hosts file control
# ----------------------------
def backup_hosts(cfg):
    """Backup hosts file if not already backed up."""
    try:
        if not os.path.exists(cfg["hosts_backup"]):
            shutil.copy2(cfg["hosts_path"], cfg["hosts_backup"])
            safe_log("HOSTS_BACKUP", "Created backup")
            return True
        return True
    except Exception as e:
        safe_log("HOSTS_BACKUP_ERROR", str(e))
        return False

def restore_hosts(cfg):
    """Restore hosts from backup."""
    try:
        if os.path.exists(cfg["hosts_backup"]):
            shutil.copy2(cfg["hosts_backup"], cfg["hosts_path"])
            safe_log("HOSTS_RESTORE", "Restored from backup")
            return True
        safe_log("HOSTS_RESTORE_ERROR", "No backup found")
        return False
    except Exception as e:
        safe_log("HOSTS_RESTORE_ERROR", str(e))
        return False

def apply_hosts_block(cfg):
    """Apply hosts file blocking."""
    if not is_admin():
        safe_log("HOSTS_BLOCK_ERROR", "Not admin - cannot modify hosts")
        return False
    
    hosts_path = r"C:\Windows\System32\drivers\etc\hosts"
    
    if not os.path.exists(hosts_path):
        safe_log("HOSTS_BLOCK_ERROR", f"Hosts file not found: {hosts_path}")
        return False
    
    if not os.access(hosts_path, os.W_OK):
        try:
            os.chmod(hosts_path, 0o666)
        except Exception as e:
            safe_log("HOSTS_BLOCK_ERROR", f"Cannot change permissions: {e}")
            return False
    
    try:
        with open(hosts_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        
        blocked_sites = cfg.get("blocked_sites", [])
        if not blocked_sites:
            return True
        
        # Remove old Study Lock blocks
        new_lines = []
        for line in lines:
            if "Study Lock" in line:
                continue
            
            is_blocked = False
            for site in blocked_sites:
                if site in line and line.strip().startswith("127.0.0.1"):
                    is_blocked = True
                    break
            
            if not is_blocked:
                new_lines.append(line)
        
        # Add new blocks
        new_lines.append("\n# Study Lock blocks (added by Study Lock app)\n")
        
        block_count = 0
        for site in blocked_sites:
            new_lines.append(f"127.0.0.1 {site}\n")
            new_lines.append(f"127.0.0.1 www.{site}\n")
            block_count += 2
        
        # Write to hosts file
        with open(hosts_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        
        safe_log("HOSTS_BLOCK_SUCCESS", f"Applied {block_count} blocks")
        
        # Flush DNS cache
        try:
            import subprocess
            subprocess.run(["ipconfig", "/flushdns"], 
                          capture_output=True, 
                          text=True, 
                          check=True)
            safe_log("DNS_FLUSH", "Success")
        except Exception as e:
            safe_log("DNS_FLUSH_ERROR", str(e))
        
        return True
        
    except PermissionError as e:
        safe_log("HOSTS_BLOCK_ERROR", f"Permission denied: {e}")
        return False
        
    except Exception as e:
        safe_log("HOSTS_BLOCK_ERROR", f"Unexpected error: {e}")
        return False

def remove_hosts_block(cfg):
    """Remove hosts file blocking with enhanced error handling."""
    if not is_admin():
        safe_log("HOSTS_UNBLOCK_ERROR", "Not admin - cannot modify hosts")
        return False
    
    hosts_path = r"C:\Windows\System32\drivers\etc\hosts"
    
    try:
        if not os.path.exists(hosts_path):
            safe_log("HOSTS_UNBLOCK_ERROR", f"Hosts file not found: {hosts_path}")
            return False
        
        # Read current hosts file
        with open(hosts_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        
        # Remove Study Lock blocks
        new_lines = []
        removed_count = 0
        skip_next = False
        
        for line in lines:
            if "Study Lock" in line:
                skip_next = True
                continue
            
            # Skip block lines
            if skip_next and any(site in line for site in cfg["blocked_sites"]):
                removed_count += 1
                continue
            else:
                skip_next = False
            
            new_lines.append(line)
        
        # Write back
        try:
            with open(hosts_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            
            safe_log("HOSTS_UNBLOCK_SUCCESS", f"Removed {removed_count} blocks from hosts file")
            
            # Flush DNS cache
            try:
                import subprocess
                subprocess.run(["ipconfig", "/flushdns"], capture_output=True, check=True)
                safe_log("DNS_FLUSH", "DNS cache flushed")
            except:
                pass
            
            return True
            
        except Exception as e:
            safe_log("HOSTS_UNBLOCK_ERROR", f"Failed to write hosts file: {e}")
            return False
    
    except Exception as e:
        safe_log("HOSTS_UNBLOCK_ERROR", f"Unexpected error: {e}")
        return False

# ----------------------------
# Killer thread
# ----------------------------
class KillerThread(threading.Thread):
    def __init__(self, cfg, state):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.state = state
        self.stop_event = threading.Event()
        self.stop_flag = False

    def stop(self):
        self.stop_flag = True

def run(self):
    """Main thread loop - applies blocking and monitors processes."""
    self.blocks_removed = False
    
    while not self.stop_event.is_set():
        try:
            # Check if we need to apply/remove blocks based on progress
            with state_lock:
                mins = self.state.get("minutes_today", 0)
                required = self.cfg.get("daily_required_minutes", 300)
                
                if mins >= required:
                    # Goal reached - remove blocks
                    if not self.blocks_removed:
                        try:
                            remove_hosts_block(self.cfg)
                            self.blocks_removed = True
                            safe_log("GOAL_REACHED", "Blocks removed")
                        except Exception as e:
                            safe_log("GOAL_REACHED_ERROR", str(e))
                elif self.blocks_removed:
                    # Goal not reached but blocks were removed - reapply
                    try:
                        apply_hosts_block(self.cfg)
                        self.blocks_removed = False
                        safe_log("BLOCKS_REAPPLIED", "Website blocks reapplied")
                    except Exception as e:
                        safe_log("BLOCKS_REAPPLY_ERROR", str(e))
            
            # Kill blocked applications
            if psutil:
                blocked_apps = self.cfg.get("blocked_apps", [])
                for proc in psutil.process_iter(['name']):
                    try:
                        pname = proc.info.get('name', '')
                        if pname and pname.lower() in [x.lower() for x in blocked_apps]:
                            proc.kill()
                            safe_log("KILLED_APP", pname)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                    except Exception as e:
                        safe_log("KILL_ERROR", str(e))
            
            # Wait 2 seconds before next check
            self.stop_event.wait(2)
            
        except Exception as e:
            safe_log("KILLER_THREAD_ERROR", f"Loop error: {e}")
            self.stop_event.wait(5)
    
    safe_log("KILLER_THREAD", "Stopped")

# ----------------------------
# Glass Panel widget
# ----------------------------
class GlassPanel(QWidget):
    def __init__(self, parent=None, radius=12, color=QColor(60, 60, 60, 230)):
        super().__init__(parent)
        self.radius = radius
        self.bg = color
        self.setAttribute(Qt.WA_TranslucentBackground)

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        r = self.rect().adjusted(6, 6, -6, -6)
        rectf = QRectF(float(r.x()), float(r.y()), float(r.width()), float(r.height()))

        path = QPainterPath()
        path.addRoundedRect(rectf, float(self.radius), float(self.radius))

        painter.fillPath(path, QBrush(self.bg))
        painter.setPen(QColor(255, 255, 255, 10))
        painter.drawPath(path)

# ----------------------------
# Animated Button
# ----------------------------
class AnimatedButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        
        self._shadow_strength = 0
        
        self.shadow = QGraphicsDropShadowEffect()
        self.shadow.setBlurRadius(15)
        self.shadow.setColor(QColor(109, 211, 241, 0))
        self.shadow.setOffset(0, 0)
        self.setGraphicsEffect(self.shadow)
        
        self.anim = QPropertyAnimation(self, b"shadowStrength")
        self.anim.setDuration(200)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
    
    def enterEvent(self, event):
        self.anim.stop()
        self.anim.setStartValue(self._shadow_strength)
        self.anim.setEndValue(200)
        self.anim.start()
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        self.anim.stop()
        self.anim.setStartValue(self._shadow_strength)
        self.anim.setEndValue(0)
        self.anim.start()
        super().leaveEvent(event)
    
    @pyqtProperty(int)
    def shadowStrength(self):
        return self._shadow_strength
    
    @shadowStrength.setter
    def shadowStrength(self, value):
        self._shadow_strength = value
        self.shadow.setColor(QColor(109, 211, 241, value))

# ----------------------------
# Mini Floating Timer Window
# ----------------------------
class MiniTimerWindow(QWidget):
    """Small floating timer window (like Windows clock)."""
    
    def __init__(self, parent=None):
        super().__init__()
        
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint | 
            Qt.FramelessWindowHint | 
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.setFixedSize(120, 60)
        
        # Position at top-right corner
        screen = QApplication.desktop().screenGeometry()
        self.move(screen.width() - 140, 20)
        
        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Timer label
        self.timer_label = QLabel("00:00")
        self.timer_label.setAlignment(Qt.AlignCenter)
        self.timer_label.setStyleSheet("""
            QLabel {
                color: #6DD3F1;
                font-size: 24px;
                font-weight: bold;
                background: rgba(15, 17, 18, 230);
                border-radius: 8px;
                padding: 5px;
            }
        """)
        
        layout.addWidget(self.timer_label)
        
        # Dragging
        self.dragging = False
        self.drag_position = QPoint()
    
    def update_time(self, text):
        """Update displayed time."""
        self.timer_label.setText(text)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.dragging:
            self.move(event.globalPos() - self.drag_position)
            event.accept()
    
    def mouseReleaseEvent(self, event):
        self.dragging = False

# ----------------------------
# System Tray Icon
# ----------------------------
class TrayIcon(QSystemTrayIcon):
    """System tray icon with menu."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        try:
            if os.path.exists("study_lock.ico"):
                self.setIcon(QIcon("study_lock.ico"))
            else:
                app = QApplication.instance()
                self.setIcon(app.style().standardIcon(app.style().SP_ComputerIcon))
        except Exception:
            app = QApplication.instance()
            self.setIcon(app.style().standardIcon(app.style().SP_ComputerIcon))
        
        self.setToolTip("Study Lock")
        
        self.menu = QMenu()
        
        self.show_action = QAction("📱 Show Window", self)
        self.show_action.triggered.connect(self.on_show_hide)
        self.menu.addAction(self.show_action)
        
        self.menu.addSeparator()
        
        self.status_action = QAction("⏸️ Status: Idle", self)
        self.status_action.setEnabled(False)
        self.menu.addAction(self.status_action)
        
        self.menu.addSeparator()
        
        self.start_action = QAction("▶️ Start Pomodoro", self)
        self.menu.addAction(self.start_action)
        
        self.pause_action = QAction("⏸️ Pause", self)
        self.pause_action.setEnabled(False)
        self.menu.addAction(self.pause_action)
        
        self.menu.addSeparator()
        
        quit_action = QAction("🚪 Quit", self)
        quit_action.triggered.connect(self.on_quit)
        self.menu.addAction(quit_action)
        
        self.setContextMenu(self.menu)
        self.activated.connect(self.on_activated)
        
        self.parent_window = parent
    
    def on_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.on_show_hide()
    
    def on_show_hide(self):
        if self.parent_window:
            if self.parent_window.isVisible():
                self.parent_window.hide()
                self.show_action.setText("📱 Show Window")
                self.showMessage(
                    "Study Lock",
                    "Minimized to tray. Double-click to restore.",
                    QSystemTrayIcon.Information,
                    2000
                )
            else:
                self.parent_window.show()
                self.parent_window.activateWindow()
                self.parent_window.raise_()
                self.show_action.setText("📦 Hide to Tray")
    
    def on_quit(self):
        if self.parent_window:
            self.parent_window.force_quit = True
            self.parent_window.close()
    
    def update_status(self, status_text):
        self.status_action.setText(f"Status: {status_text}")
    
    def update_tooltip(self, tooltip):
        self.setToolTip(tooltip)

# ----------------------------
# Chart Widget (if matplotlib available)
# ----------------------------
if CHARTS_AVAILABLE:
    class SessionChartWidget(QWidget):
        """Widget displaying session history charts."""
        
        def __init__(self, parent=None):
            super().__init__(parent)
            
            layout = QVBoxLayout(self)
            
            self.figure = Figure(figsize=(8, 6), facecolor='#0f1112')
            self.canvas = FigureCanvasQTAgg(self.figure)
            layout.addWidget(self.canvas)
            
            self.refresh_chart()
        
        def refresh_chart(self):
            """Refresh chart with latest data."""
            self.figure.clear()
            
            history = load_session_history()
            
            if not history:
                ax = self.figure.add_subplot(111, facecolor='#1a1c1e')
                ax.text(0.5, 0.5, 'No session data yet', 
                       ha='center', va='center', color='#ffffff', fontsize=14)
                ax.set_xticks([])
                ax.set_yticks([])
                self.canvas.draw()
                return
            
            # Group by date
            from collections import defaultdict
            daily_data = defaultdict(lambda: {'work': 0, 'break': 0, 'total_sessions': 0})
            
            for session in history:
                date = session['date']
                if session['completed']:
                    if session['type'] == 'work':
                        daily_data[date]['work'] += session['duration']
                    else:
                        daily_data[date]['break'] += session['duration']
                    daily_data[date]['total_sessions'] += 1
            
            # Sort by date and get last 7 days
            sorted_dates = sorted(daily_data.keys())[-7:]
            
            if not sorted_dates:
                ax = self.figure.add_subplot(111, facecolor='#1a1c1e')
                ax.text(0.5, 0.5, 'No completed sessions yet', 
                       ha='center', va='center', color='#ffffff', fontsize=14)
                ax.set_xticks([])
                ax.set_yticks([])
                self.canvas.draw()
                return
            
            dates_short = [d[-5:] for d in sorted_dates]  # MM-DD format
            work_mins = [daily_data[d]['work'] for d in sorted_dates]
            break_mins = [daily_data[d]['break'] for d in sorted_dates]
            
            # Create stacked bar chart
            ax = self.figure.add_subplot(111, facecolor='#1a1c1e')
            
            x = range(len(dates_short))
            width = 0.6
            
            bars1 = ax.bar(x, work_mins, width, label='Work', color='#6DD3F1', alpha=0.9)
            bars2 = ax.bar(x, break_mins, width, bottom=work_mins, 
                          label='Break', color='#FFD700', alpha=0.7)
            
            ax.set_xlabel('Date', color='#ffffff', fontsize=12)
            ax.set_ylabel('Minutes', color='#ffffff', fontsize=12)
            ax.set_title('Session History (Last 7 Days)', color='#ffffff', fontsize=14, pad=20)
            ax.set_xticks(x)
            ax.set_xticklabels(dates_short, rotation=45, ha='right', color='#ffffff')
            ax.tick_params(colors='#ffffff')
            ax.legend(facecolor='#1a1c1e', edgecolor='#ffffff', labelcolor='#ffffff')
            
            # Grid
            ax.grid(True, alpha=0.2, color='#ffffff')
            ax.spines['bottom'].set_color('#ffffff')
            ax.spines['left'].set_color('#ffffff')
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            
            self.figure.tight_layout()
            self.canvas.draw()

# ----------------------------
# MAIN WINDOW
# ----------------------------
class StudyLockWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowSystemMenuHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.setWindowTitle("Study Lock")
        self.resize(1100, 700)
        
        self.dragging = False
        self.drag_position = QPoint()
        self.force_quit = False
        self.has_tray = False

        self.cfg = load_config()
        self.state = initialize_state()
        self.admin = is_admin()

        self.override_active = False
        self.override_end_time = None
        
        self.thread_signals = ThreadSignals()
        self.thread_signals.override_update.connect(self._update_override_label)

        # ==================== BLOCKING SYSTEM INITIALIZATION ====================
        self.killer = None

        if self.admin:
            try:
                backup_hosts(self.cfg)
                self.killer = KillerThread(self.cfg, self.state)
                self.killer.start()
                safe_log("BLOCKING", "Killer thread started")
            except Exception as e:
                safe_log("KILLER_THREAD_ERROR", str(e))
        else:
            safe_log("WARNING", "Not running as admin - blocking features disabled")

        # ==================== END BLOCKING SYSTEM INITIALIZATION ====================

        atexit.register(self.cleanup)

        # Mini timer (will be created after UI is built)
        self.mini_timer = None

        # ==================== BUILD UI FIRST ====================
        # This creates all widgets including self.timer_label
        self.build_ui()
        self.apply_qss()
        # ==================== END UI BUILD ====================

        # NOW we can use widgets created by build_ui()
        
        # Create animation for timer_label (NOW timer_label exists!)
        self.anim = QPropertyAnimation(self.timer_label, b"geometry")
        self.anim.setDuration(350)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)

        # System tray (after UI is built)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = TrayIcon(self)
            self.tray_icon.show()
            self.has_tray = True
            
            self.tray_icon.start_action.triggered.connect(self.start_work)
            self.tray_icon.pause_action.triggered.connect(self.pause)
            
            self.tray_icon.showMessage(
                "Study Lock Started",
                "Running in system tray. Double-click icon to show/hide.",
                QSystemTrayIcon.Information,
                3000
            )
            safe_log("TRAY", "System tray initialized")
        else:
            self.tray_icon = None
            safe_log("TRAY_WARNING", "System tray not available")

        # Create mini timer window (after main UI exists)
        if self.cfg.get("mini_timer_enabled", False):
            self.mini_timer = MiniTimerWindow(self)

        # Timers
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(100)
        
        self.dashboard_timer = QTimer()
        self.dashboard_timer.timeout.connect(self.update_dashboard_status)
        self.dashboard_timer.start(1000)

        # Session state
        self.start_time = None
        self.total_seconds = 0
        self.remaining = 0
        self.running = False
        self.paused = False
        self.pause_time = None
        self.cycles = 0
        self.in_break = False
        
        # Blink timer
        self.blink_timer = QTimer()
        self.blink_timer.timeout.connect(self.blink_timer_label)
        self.blink_state = False

        # Restore paused session and update UI
        self.restore_paused_session()
        self.update_button_states()
        self.update_dashboard_status()

    def _update_override_label(self, text, visible):
        self.override_label.setText(text)
        self.override_label.setVisible(visible)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.dragging:
            self.move(event.globalPos() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.dragging = False

    def minimize_to_tray(self):
        if self.has_tray:
            # Animate window before hiding
            self.animation = QPropertyAnimation(self, b"windowOpacity")
            self.animation.setDuration(200)
            self.animation.setStartValue(1.0)
            self.animation.setEndValue(0.0)
            self.animation.setEasingCurve(QEasingCurve.OutCubic)
            self.animation.finished.connect(self._finish_minimize)
            self.animation.start()
        else:
            self.showMinimized()
    
    def _finish_minimize(self):
        self.hide()
        self.setWindowOpacity(1.0)
        if self.tray_icon:
            self.tray_icon.show_action.setText("📱 Show Window")
            self.tray_icon.showMessage(
                "Study Lock",
                "Minimized to tray. Double-click to restore.",
                QSystemTrayIcon.Information,
                2000
            )

    def toggle_mini_timer(self, enabled):
        """Toggle mini floating timer."""
        self.cfg["mini_timer_enabled"] = enabled
        save_config(self.cfg)
        
        if enabled:
            if not self.mini_timer:
                self.mini_timer = MiniTimerWindow(self)
            self.mini_timer.show()
        else:
            if self.mini_timer:
                self.mini_timer.hide()

    def build_ui(self):
        container = QWidget()
        container.setObjectName("mainContainer")
        
        root = QWidget(container)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title bar
        title_bar = QWidget()
        title_bar.setObjectName("titleBar")
        title_bar.setFixedHeight(40)
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(10, 0, 10, 0)
        
        title_label = QLabel("🎯 Study Lock")
        title_label.setObjectName("titleBarLabel")
        tb_layout.addWidget(title_label)
        tb_layout.addStretch()
        
        btn_minimize = QPushButton("−")
        btn_minimize.setObjectName("titleBarBtn")
        btn_minimize.setFixedSize(30, 30)
        btn_minimize.clicked.connect(self.minimize_to_tray)
        
        btn_close = QPushButton("×")
        btn_close.setObjectName("titleBarBtn")
        btn_close.setFixedSize(30, 30)
        btn_close.clicked.connect(self.close)
        
        tb_layout.addWidget(btn_minimize)
        tb_layout.addWidget(btn_close)

        # Sidebar
        sidebar = QWidget()
        sb = QVBoxLayout(sidebar)
        sidebar.setFixedWidth(220)
        sidebar.setObjectName("sidebar")

        title = QLabel("📚 Study Lock")
        title.setObjectName("appTitle")
        title.setAlignment(Qt.AlignCenter)
        sb.addWidget(title)
        
        sb.addSpacing(10)

        self.btn_dash = AnimatedButton("📊 Dashboard")
        self.btn_pom = AnimatedButton("🍅 Pomodoro")
        self.btn_stats = AnimatedButton("📈 Stats")
        self.btn_settings = AnimatedButton("⚙️ Settings")

        for b in (self.btn_dash, self.btn_pom, self.btn_stats, self.btn_settings):
            b.setFixedHeight(44)
            b.setMinimumWidth(180)
            sb.addWidget(b)

        sb.addStretch()

        self.btn_override = AnimatedButton("🔓 Emergency Override")
        self.override_label = QLabel("")
        self.override_label.setObjectName("overrideLabel")
        self.override_label.setAlignment(Qt.AlignCenter)
        self.override_label.setVisible(False)
        
        self.btn_quit = AnimatedButton("🚪 Quit")
        sb.addWidget(self.override_label)
        sb.addWidget(self.btn_override)
        sb.addWidget(self.btn_quit)

        self.stack = QStackedWidget()

        # ---------- Dashboard ----------
        dash = QWidget()
        dlay = QVBoxLayout(dash)

        card = GlassPanel()
        cl = QVBoxLayout(card)

        t = QLabel("📊 Dashboard")
        t.setObjectName("pageTitle")
        cl.addWidget(t)
        cl.addSpacing(20)

        self.dashboard_status = QLabel("")
        self.dashboard_status.setWordWrap(True)
        self.dashboard_status.setTextFormat(Qt.RichText)
        cl.addWidget(self.dashboard_status)
        
        cl.addSpacing(15)

        self.dashboard_progress = QProgressBar()
        self.dashboard_progress.setMaximum(self.cfg["daily_required_minutes"])
        self.dashboard_progress.setFormat("%v / %m min (%p%)")
        cl.addWidget(self.dashboard_progress)
        
        cl.addSpacing(20)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(10)
        self.dash_start = AnimatedButton("▶️ Start Pomodoro")
        self.dash_status = AnimatedButton("🔄 Refresh Status")
        self.dash_restore = AnimatedButton("💾 Restore Hosts")
        
        self.dash_start.setMinimumHeight(40)
        self.dash_status.setMinimumHeight(40)
        self.dash_restore.setMinimumHeight(40)
        
        btn_col.addWidget(self.dash_start)
        btn_col.addWidget(self.dash_status)
        btn_col.addWidget(self.dash_restore)

        cl.addLayout(btn_col)
        cl.addStretch()
        dlay.addWidget(card)

        # ---------- Pomodoro ----------
        pom = QWidget()
        play = QVBoxLayout(pom)
        pcard = GlassPanel()
        pbox = QVBoxLayout(pcard)

        self.session_label = QLabel("💼 Work Session")
        self.session_label.setObjectName("sessionLabel")
        self.session_label.setAlignment(Qt.AlignCenter)
        pbox.addWidget(self.session_label)

        self.timer_label = QLabel("00:00")
        self.timer_label.setObjectName("timerBig")
        self.timer_label.setAlignment(Qt.AlignCenter)
        pbox.addWidget(self.timer_label)

        # Custom duration selectors
        duration_layout = QHBoxLayout()
        duration_layout.addWidget(QLabel("⏱️ Work:"))
        self.work_duration_combo = QComboBox()
        self.work_duration_combo.addItems(["5", "10", "15", "25", "30", "45", "50", "60", "90"])
        self.work_duration_combo.setCurrentText(str(self.cfg.get("pomodoro_work_min", 50)))
        duration_layout.addWidget(self.work_duration_combo)
        
        duration_layout.addSpacing(20)
        duration_layout.addWidget(QLabel("☕ Break:"))
        self.break_duration_combo = QComboBox()
        self.break_duration_combo.addItems(["5", "10", "15", "30", "45", "60", "90"])
        self.break_duration_combo.setCurrentText(str(self.cfg.get("pomodoro_break_min", 10)))
        duration_layout.addWidget(self.break_duration_combo)
        
        pbox.addLayout(duration_layout)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.btn_start = AnimatedButton("▶️ Start")
        self.btn_pause = AnimatedButton("⏸️ Pause")
        self.btn_resume = AnimatedButton("▶️ Resume")
        self.btn_stop = AnimatedButton("⏹️ Stop")
        self.btn_skip_break = AnimatedButton("⏭️ Skip Break")

        for x in (self.btn_start, self.btn_pause, self.btn_resume, self.btn_stop, self.btn_skip_break):
            row.addWidget(x)

        pbox.addLayout(row)
        
        pbox.addSpacing(15)
        
        self.pom_progress = QProgressBar()
        self.pom_progress.setMaximum(self.cfg["daily_required_minutes"])
        self.pom_progress.setFormat("%v / %m min (%p%)")
        pbox.addWidget(self.pom_progress)
        
        pbox.addSpacing(10)
        
        self.cycles_label = QLabel("🔄 Cycles: 0")
        self.cycles_label.setAlignment(Qt.AlignCenter)
        self.cycles_label.setObjectName("cyclesLabel")
        pbox.addWidget(self.cycles_label)
        
        play.addWidget(pcard)

        # ---------- Stats ----------
        stats = QWidget()
        sl = QVBoxLayout(stats)
        sc = GlassPanel()
        scl = QVBoxLayout(sc)
        s_title = QLabel("📈 Statistics")
        s_title.setObjectName("pageTitle")
        scl.addWidget(s_title)
        scl.addSpacing(20)
        
        # Add chart if available
        if CHARTS_AVAILABLE:
            self.chart_widget = SessionChartWidget()
            scl.addWidget(self.chart_widget)
            
            refresh_chart_btn = AnimatedButton("🔄 Refresh Chart")
            refresh_chart_btn.clicked.connect(self.chart_widget.refresh_chart)
            scl.addWidget(refresh_chart_btn)
        
        scl.addSpacing(10)
        
        self.stats_text = QLabel("")
        self.stats_text.setWordWrap(True)
        self.stats_text.setTextFormat(Qt.RichText)
        scl.addWidget(self.stats_text)
        scl.addStretch()
        sl.addWidget(sc)

        # ---------- Settings ----------
        sett = QWidget()
        stl = QVBoxLayout(sett)
        sc2 = GlassPanel()
        form = QFormLayout(sc2)
        
        settings_title = QLabel("⚙️ Settings")
        settings_title.setObjectName("pageTitle")
        form.addRow(settings_title)

        self.spin_daily = QSpinBox()
        self.spin_daily.setRange(1, 1440)
        self.spin_daily.setValue(self.cfg["daily_required_minutes"])

        self.spin_long_break = QSpinBox()
        self.spin_long_break.setRange(1, 240)
        self.spin_long_break.setValue(self.cfg.get("long_break_min", 30))

        self.spin_long = QSpinBox()
        self.spin_long.setRange(1, 10)
        self.spin_long.setValue(self.cfg["long_break_after_cycles"])

        form.addRow("⏱️ Daily minutes:", self.spin_daily)
        form.addRow("🌴 Long break minutes:", self.spin_long_break)
        form.addRow("🔄 Long break cycles:", self.spin_long)

        # Sound toggle
        self.sound_checkbox = QCheckBox("🔔 Enable completion sound")
        self.sound_checkbox.setChecked(self.cfg.get("sound_enabled", True))
        form.addRow(self.sound_checkbox)

        # Mini timer toggle
        self.mini_timer_checkbox = QCheckBox("⏰ Show mini floating timer")
        self.mini_timer_checkbox.setChecked(self.cfg.get("mini_timer_enabled", False))
        self.mini_timer_checkbox.stateChanged.connect(lambda state: self.toggle_mini_timer(state == Qt.Checked))
        form.addRow(self.mini_timer_checkbox)

        self.list_apps = QListWidget()
        for x in self.cfg["blocked_apps"]:
            self.list_apps.addItem(x)

        self.list_sites = QListWidget()
        for x in self.cfg["blocked_sites"]:
            self.list_sites.addItem(x)

        form.addRow("🚫 Blocked apps:", self.list_apps)
        form.addRow("🌐 Blocked sites:", self.list_sites)

        self.app_input = QLineEdit()
        self.app_input.setPlaceholderText("e.g., chrome.exe")
        self.site_input = QLineEdit()
        self.site_input.setPlaceholderText("e.g., facebook.com")

        baddapp = AnimatedButton("➕ Add App")
        baddsite = AnimatedButton("➕ Add Site")
        brmapp = AnimatedButton("➖ Remove App")
        brmsite = AnimatedButton("➖ Remove Site")
        bsave = AnimatedButton("💾 Save Settings")

        form.addRow(self.app_input, baddapp)
        form.addRow(brmapp)
        form.addRow(self.site_input, baddsite)
        form.addRow(brmsite)
        form.addRow(bsave)

        stl.addWidget(sc2)

        self.stack.addWidget(dash)
        self.stack.addWidget(pom)
        self.stack.addWidget(stats)
        self.stack.addWidget(sett)

        # Connections
        self.btn_dash.clicked.connect(lambda: self.switch_page(dash))
        self.btn_pom.clicked.connect(lambda: self.switch_page(pom))
        self.btn_stats.clicked.connect(lambda: self.switch_page(stats))
        self.btn_settings.clicked.connect(lambda: self.switch_page(sett))
        self.btn_override.clicked.connect(self.ui_override)
        self.btn_quit.clicked.connect(self.close)

        self.btn_start.clicked.connect(self.start_work)
        self.btn_pause.clicked.connect(self.pause)
        self.btn_resume.clicked.connect(self.resume)
        self.btn_stop.clicked.connect(self.stop)
        self.btn_skip_break.clicked.connect(self.skip_break)

        self.dash_start.clicked.connect(lambda: self.switch_page(pom))
        self.dash_status.clicked.connect(self.update_dashboard_status)
        self.dash_restore.clicked.connect(self.ui_restore_hosts)

        baddapp.clicked.connect(lambda: self.add_app(self.app_input.text().strip()))
        baddsite.clicked.connect(lambda: self.add_site(self.site_input.text().strip()))
        brmapp.clicked.connect(self.remove_selected_app)
        brmsite.clicked.connect(self.remove_selected_site)
        bsave.clicked.connect(self.save_settings)

        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(title_bar)
        main_layout.addWidget(root)
        
        layout.addWidget(sidebar)
        layout.addWidget(self.stack)
        
        self.setCentralWidget(container)

    def switch_page(self, page):
        if self.stack.currentWidget() != page:
            self.stack.setCurrentWidget(page)

    def update_button_states(self):
        if self.running:
            if self.paused:
                self.btn_start.setEnabled(False)
                self.btn_pause.setEnabled(False)
                self.btn_resume.setEnabled(True)
                self.btn_stop.setEnabled(True)
                self.btn_skip_break.setEnabled(False)
                if self.has_tray:
                    self.tray_icon.start_action.setEnabled(False)
                    self.tray_icon.pause_action.setEnabled(False)
            else:
                self.btn_start.setEnabled(False)
                self.btn_pause.setEnabled(True)
                self.btn_resume.setEnabled(False)
                self.btn_stop.setEnabled(True)
                self.btn_skip_break.setEnabled(self.in_break)
                if self.has_tray:
                    self.tray_icon.start_action.setEnabled(False)
                    self.tray_icon.pause_action.setEnabled(True)
        else:
            self.btn_start.setEnabled(True)
            self.btn_pause.setEnabled(False)
            self.btn_resume.setEnabled(False)
            self.btn_stop.setEnabled(False)
            self.btn_skip_break.setEnabled(False)
            if self.has_tray:
                self.tray_icon.start_action.setEnabled(True)
                self.tray_icon.pause_action.setEnabled(False)

    def skip_break(self):
        """Skip current break and count the completed work cycle."""
        if not self.running or not self.in_break:
            return
        
        # Save the break session (partial)
        elapsed_min = (self.total_seconds - self.remaining) // 60
        if elapsed_min > 0:
            save_session_history("break", elapsed_min, completed=False)
        
        # Stop the break
        self.running = False
        self.blink_timer.stop()
        self.timer_label.setStyleSheet("")
        self.timer_label.setText("00:00")
        self.session_label.setText("💼 Work Session")
        self.in_break = False
        
        clear_pause()
        self.update_button_states()
        
        notify("Break Skipped", "Ready for next work session!", 3)
        safe_log("BREAK_SKIP", f"Skipped after {elapsed_min} min")

    def add_app(self, txt):
        if txt and not self.list_apps.findItems(txt, Qt.MatchExactly):
            self.list_apps.addItem(txt)
            self.app_input.clear()

    def add_site(self, txt):
        if txt and not self.list_sites.findItems(txt, Qt.MatchExactly):
            self.list_sites.addItem(txt)
            self.site_input.clear()

    def remove_selected_app(self):
        for item in self.list_apps.selectedItems():
            self.list_apps.takeItem(self.list_apps.row(item))

    def remove_selected_site(self):
        for item in self.list_sites.selectedItems():
            self.list_sites.takeItem(self.list_sites.row(item))

    def save_settings(self):
        reply = show_question_dialog(
            self, 
            "Save Settings",
            "Save settings and restart blocking?",
            ["Yes", "No"]
        )

        if reply != 0:  # 0 = Yes
            return

        self.cfg["daily_required_minutes"] = self.spin_daily.value()
        self.cfg["long_break_min"] = self.spin_long_break.value()
        self.cfg["long_break_after_cycles"] = self.spin_long.value()
        self.cfg["sound_enabled"] = self.sound_checkbox.isChecked()
        self.cfg["blocked_apps"] = [self.list_apps.item(i).text() for i in range(self.list_apps.count())]
        self.cfg["blocked_sites"] = [self.list_sites.item(i).text() for i in range(self.list_sites.count())]
        
        save_config(self.cfg)
        
        self.dashboard_progress.setMaximum(self.cfg["daily_required_minutes"])
        self.pom_progress.setMaximum(self.cfg["daily_required_minutes"])
        
        with state_lock:
            if self.state.get("minutes_today", 0) < self.cfg["daily_required_minutes"]:
                if self.admin:
                    apply_hosts_block(self.cfg)
        
        show_info_dialog(self, "Saved", "Settings saved successfully.")

    def update_dashboard_status(self):
        with state_lock:
            mins = self.state.get("minutes_today", 0)
        
        required = self.cfg["daily_required_minutes"]
        remaining = max(0, required - mins)
        percentage = int((mins / required) * 100) if required > 0 else 0
        
        status = '<div style="font-size: 16px; line-height: 2.0;">'
        status += f'<p><b>📊 Today:</b> {mins}/{required} minutes ({percentage}%)</p>'
        status += f'<p><b>⏱️ Remaining:</b> {remaining} minutes</p>'
        status += '<br>'
        
        if mins >= required:
            status += '<p style="color: #6DD3F1; font-size: 18px; font-weight: bold;">✅ Daily goal completed!</p>'
        else:
            status += f'<p style="color: #FFD700; font-size: 17px;">⏳ {remaining} minutes until goal</p>'
        
        if not self.admin:
            status += '<br><p style="color: #FF6B6B; font-weight: bold;">⚠️ Not running as admin - blocking disabled</p>'
        
        if self.override_active and self.override_end_time:
            remaining_override = max(0, int((self.override_end_time - datetime.now()).total_seconds() / 60))
            status += f'<br><p style="color: #FF6B6B; font-size: 16px; font-weight: bold;">🔓 Override Active ({remaining_override} min left)</p>'
        
        status += '</div>'
        self.dashboard_status.setText(status)

    def start_work(self):
        if self.running:
            return
        
        # Get custom duration from combo box
        work_min = int(self.work_duration_combo.currentText())
        self.start_pomodoro(work_min, False)

    def start_pomodoro(self, minutes, is_break):
        self.total_seconds = minutes * 60
        self.remaining = self.total_seconds
        self.start_time = time.time()
        self.running = True
        self.paused = False
        self.pause_time = None
        self.in_break = is_break

        icon = "☕" if is_break else "💼"
        self.session_label.setText(f"{icon} {'Break' if is_break else 'Work'} Session")
        self.timer_label.setText(f"{minutes:02d}:00")

        geom = self.timer_label.geometry()
        self.anim.stop()
        self.anim.setStartValue(geom)
        self.anim.setEndValue(geom.adjusted(-6, -6, 6, 6))
        self.anim.start()

        clear_pause()
        self.update_button_states()
        
        session_type = "Long Break" if (is_break and minutes > int(self.break_duration_combo.currentText())) else ("Break" if is_break else "Work")
        notify("Pomodoro", f"{session_type} session started ({minutes} min)", 4)
        safe_log("POMODORO_START", f"{session_type} - {minutes} min")

    def pause(self):
        if self.running and not self.paused:
            self.paused = True
            self.pause_time = time.time()
            elapsed = self.pause_time - self.start_time
            save_pause(elapsed, self.total_seconds, self.in_break)
            self.update_button_states()
            notify("Paused", "Session paused")
            safe_log("POMODORO_PAUSE", f"Elapsed: {elapsed:.0f}s")

    def resume(self):
        if self.running and self.paused:
            pause_duration = time.time() - self.pause_time
            self.start_time += pause_duration
            self.paused = False
            self.pause_time = None
            clear_pause()
            self.update_button_states()
            notify("Resumed", "Session resumed")
            safe_log("POMODORO_RESUME", "")

    def stop(self):
        if not self.running:
            return
        
        reply = show_question_dialog(
            self,
            "Stop Session",
            "Stop the current session? Progress will not be saved.",
            ["Yes", "No"]
        )

        if reply != 0:  # 0 = Yes
            return
            
        self.running = False
        self.paused = False
        self.remaining = 0
        self.start_time = None
        self.pause_time = None
        self.in_break = False
        self.timer_label.setText("00:00")
        self.session_label.setText("💼 Work Session")
        self.blink_timer.stop()
        clear_pause()
        self.update_button_states()
        notify("Stopped", "Session stopped")
        safe_log("POMODORO_STOP", "")

    def restore_paused_session(self):
        pause_data = load_pause()
        if not pause_data:
            return
        
        reply = show_question_dialog(
            self,
            "Restore Session",
            "A paused session was found. Resume it?",
            ["Yes", "No"]
        )

        if reply != 0:  # 0 = Yes
            clear_pause()
            return

        elapsed = pause_data.get("elapsed", 0)
        total = pause_data.get("total", 0)
        in_break = pause_data.get("in_break", False)
        
        self.total_seconds = total
        self.remaining = total - elapsed
        self.start_time = time.time() - elapsed
        self.running = True
        self.paused = True
        self.pause_time = time.time()
        self.in_break = in_break
        
        icon = "☕" if in_break else "💼"
        self.session_label.setText(f"{icon} {'Break' if in_break else 'Work'} Session")
        self.update_button_states()
        safe_log("POMODORO_RESTORE", f"Elapsed: {elapsed}s, Total: {total}s")

    def complete_work(self):
        added = self.total_seconds // 60
        
        # Save session history
        save_session_history("work", added, completed=True)
        
        with state_lock:
            self.state["minutes_today"] = self.state.get("minutes_today", 0) + added
            save_state(self.state)
            current_mins = self.state["minutes_today"]

        safe_log("WORK_COMPLETE", f"Added {added} min, Total: {current_mins} min")
        
        # Play completion sound
        if self.cfg.get("sound_enabled", True):
            play_completion_sound()
        
        self.cycles += 1
        self.cycles_label.setText(f"🔄 Cycles: {self.cycles}")
        
        # Refresh chart if available
        if CHARTS_AVAILABLE and hasattr(self, 'chart_widget'):
            self.chart_widget.refresh_chart()
        
        if current_mins >= self.cfg["daily_required_minutes"]:
            if self.admin:
                remove_hosts_block(self.cfg)
            notify("Goal Complete!", "Daily target reached! 🎉", 10)
            
            if self.has_tray:
                self.tray_icon.showMessage(
                    "🎉 Goal Complete!",
                    f"Daily goal of {self.cfg['daily_required_minutes']} min reached!",
                    QSystemTrayIcon.Information,
                    5000
                )
            
            show_info_dialog(
                self,
                "🔓 Override Active",
                f"Blocking temporarily disabled for {minutes} minutes.\n\nBlocking will automatically resume after this period unless you've completed your daily goal."
            )
            self.running = False
            self.timer_label.setText("00:00")
            self.session_label.setText("💼 Work Session")
            self.blink_timer.stop()
            self.update_button_states()
            return
        
        if self.cycles % self.cfg["long_break_after_cycles"] == 0:
            long_break_min = self.cfg.get("long_break_min", 30)
            reply = show_question_dialog(
                self,
                "🌴 Long Break Time!",
                f"You've completed {self.cycles} cycles!\n\nStart a {long_break_min}-minute long break?",
                ["Yes", "No"]
            )

            if reply == 0:  # 0 = Yes
                self.start_pomodoro(long_break_min, True)
            else:
                self.running = False
                self.timer_label.setText("00:00")
                self.session_label.setText("💼 Work Session")
                self.blink_timer.stop()
                self.update_button_states()
        else:
            # Get custom break duration from combo box
            break_min = int(self.break_duration_combo.currentText())
            notify("Work Complete", f"Break starts now ({break_min} min)", 5)
            self.start_pomodoro(break_min, True)

    def complete_break(self):
        """Handle break completion."""
        # Save break session history
        completed_min = self.total_seconds // 60
        save_session_history("break", completed_min, completed=True)
        
        # Play completion sound
        if self.cfg.get("sound_enabled", True):
            play_completion_sound()
        
        notify("Break Over", "Ready for the next work session!", 5)
        safe_log("BREAK_COMPLETE", "")
        
        self.running = False
        self.timer_label.setText("00:00")
        self.session_label.setText("💼 Work Session")
        self.blink_timer.stop()
        self.update_button_states()
        
        # Refresh chart
        if CHARTS_AVAILABLE and hasattr(self, 'chart_widget'):
            self.chart_widget.refresh_chart()

    def blink_timer_label(self):
        """Blink timer label in last 5 seconds."""
        self.blink_state = not self.blink_state
        if self.blink_state:
            self.timer_label.setStyleSheet("color: #6DD3F1;")
        else:
            self.timer_label.setStyleSheet("color: #FF6B6B;")

    def verify_pw(self, pw):
        """Verify override password (case-insensitive by design)."""
        try:
            hash_val = hashlib.sha256((pw.lower() + _OVERRIDE_SALT).encode()).hexdigest()
            stored_hash = self.cfg.get("override_password_hash", "")
            return hash_val == stored_hash
        except Exception as e:
            safe_log("PW_VERIFY_ERROR", str(e))
            return False

    def ui_override(self):
        """Handle emergency override."""
        if not self.admin:
            show_warning_dialog(
                self,
                "Admin Required",
                "You must run Study Lock as Administrator to use override features."
            )
            return

        pw, ok = QInputDialog.getText(
            self, "🔓 Emergency Override",
            "Enter override password (case-insensitive):",
            QLineEdit.Password
        )
        if not ok:
            return

        if not self.verify_pw(pw):
            show_warning_dialog(self, "Wrong Password", "Incorrect override password.")
            safe_log("OVERRIDE_FAILED", "Wrong password")
            return

        remove_hosts_block(self.cfg)
        minutes = self.cfg["override_minutes"]
        
        self.override_active = True
        self.override_end_time = datetime.now() + timedelta(minutes=minutes)
        
        self.thread_signals.override_update.emit("Initializing...", True)
        
        notify("Override Active", f"Temporary unblocking for {minutes} minutes", 5)
        safe_log("OVERRIDE_START", f"{minutes} minutes")
        
        show_info_dialog(
            self,
            "🎉 Congratulations!",
            f"You've reached your daily goal of {self.cfg['daily_required_minutes']} minutes!\n\nBlocking has been disabled for today."
        )
        
        threading.Thread(target=self._override_thread, daemon=True).start()

    def _override_thread(self):
        """Background thread for override countdown."""
        while datetime.now() < self.override_end_time:
            remaining = int((self.override_end_time - datetime.now()).total_seconds() / 60)
            self.thread_signals.override_update.emit(f"🔓 Override: {remaining} min", True)
            time.sleep(1)

        self.override_active = False
        self.thread_signals.override_update.emit("", False)
        
        with state_lock:
            if self.state.get("minutes_today", 0) < self.cfg["daily_required_minutes"]:
                if self.admin:
                    apply_hosts_block(self.cfg)
                    notify("Override Expired", "Blocking re-enabled", 5)
                    safe_log("OVERRIDE_END", "Blocking restored")

    def ui_restore_hosts(self):
        """Restore hosts file from backup."""
        if not self.admin:
            show_warning_dialog(
                self,
                "Admin Required",
                "You must run Study Lock as Administrator to restore hosts."
            )
            return

        reply = show_question_dialog(
            self,
            "💾 Restore Hosts",
            "Restore hosts file from backup?\n\nThis will overwrite the current hosts file.",
            ["Yes", "No"]
        )

        if reply != 0:  # 0 = Yes
            return

        ok = restore_hosts(self.cfg)
        if ok:
            show_info_dialog(self, "✅ Success", "Hosts file restored from backup.")
        else:
            show_warning_dialog(self, "❌ Failed", "Could not restore hosts file. Check logs.")

    def tick(self):
        """Main timer tick - updates every 100ms."""
        with state_lock:
            mins = self.state.get("minutes_today", 0)
        
        # Update progress bars
        self.dashboard_progress.setValue(min(mins, self.cfg["daily_required_minutes"]))
        self.pom_progress.setValue(min(mins, self.cfg["daily_required_minutes"]))

        # Update tray tooltip and status
        if self.has_tray:
            if self.running and not self.paused:
                m, s = divmod(self.remaining, 60)
                session = "Break" if self.in_break else "Work"
                self.tray_icon.update_tooltip(f"Study Lock - {session}: {m:02d}:{s:02d}")
                self.tray_icon.update_status(f"⏱️ {session} - {m:02d}:{s:02d}")
            else:
                self.tray_icon.update_tooltip(f"Study Lock - {mins}/{self.cfg['daily_required_minutes']} min")
                self.tray_icon.update_status("⏸️ Idle")

        # Enhanced stats with icons
        lines = [f'<div style="font-size: 17px; line-height: 2.2;">']
        lines.append(f'<p style="font-size: 19px; font-weight: bold;">📅 Today: {mins} / {self.cfg["daily_required_minutes"]} minutes</p>')
        
        weekly = self.state.get("weekly_minutes", {})
        if weekly:
            lines.append('<br><p style="font-weight: bold; font-size: 17px;">📊 Previous Days:</p>')
            for d, v in sorted(weekly.items(), reverse=True)[:7]:
                lines.append(f'<p style="margin-left: 20px;">📌 {d}: {v} min</p>')
        else:
            lines.append('<br><p style="color: #888;">No previous data yet</p>')
        
        lines.append('</div>')
        self.stats_text.setText("".join(lines))

        # Update timer if running
        if self.running and not self.paused:
            elapsed = time.time() - self.start_time
            self.remaining = max(0, self.total_seconds - int(elapsed))
            
            m, s = divmod(self.remaining, 60)
            time_text = f"{m:02d}:{s:02d}"
            self.timer_label.setText(time_text)
            
            # Update mini timer if enabled
            if self.mini_timer and self.mini_timer.isVisible():
                self.mini_timer.update_time(time_text)
            
            # Blink in last 5 seconds
            if self.remaining <= 5 and self.remaining > 0 and not self.blink_timer.isActive():
                self.blink_timer.start(500)
            
            # Session complete
            if self.remaining <= 0:
                self.running = False
                self.blink_timer.stop()
                self.timer_label.setStyleSheet("")
                
                if self.in_break:
                    self.complete_break()
                else:
                    self.complete_work()

    def apply_qss(self):
        """Apply QSS stylesheet."""
        accent = "#6DD3F1"

        qss = f"""
        #mainContainer {{
            background: #0f1112;
            border-radius: 15px;
        }}
        
        #titleBar {{
            background: rgba(255, 255, 255, 0.05);
            border-top-left-radius: 15px;
            border-top-right-radius: 15px;
        }}
        
        #titleBarLabel {{
            color: #ffffff;
            font-size: 14px;
            font-weight: 600;
        }}
        
        #titleBarBtn {{
            background: transparent;
            color: #ffffff;
            border: none;
            font-size: 20px;
            font-weight: bold;
            border-radius: 5px;
        }}
        
        #titleBarBtn:hover {{
            background: rgba(255, 255, 255, 0.1);
        }}

        QMainWindow {{
            background: transparent;
        }}

        #sidebar {{
            background: transparent;
        }}

        #appTitle {{
            font-size: 20px;
            font-weight: 700;
            color: #ffffff;
            padding: 18px;
        }}

        QPushButton {{
            background: rgba(255,255,255,0.05);
            color: #eaf6ff;
            border-radius: 10px;
            padding: 10px 12px;
            border: 1px solid rgba(255,255,255,0.08);
            font-size: 13px;
            font-weight: 500;
        }}
        QPushButton:hover {{
            background: rgba(255,255,255,0.10);
        }}
        QPushButton:pressed {{
            background: rgba(255,255,255,0.06);
        }}
        QPushButton:disabled {{
            background: rgba(255,255,255,0.02);
            color: rgba(234,246,255,0.3);
        }}

        QProgressBar {{
            background: rgba(255,255,255,0.05);
            border-radius: 8px;
            height: 20px;
            text-align: center;
            color: #dff7ff;
            font-weight: 600;
            font-size: 12px;
        }}
        QProgressBar::chunk {{
            background: qlineargradient(
                x1:0,y1:0, x2:1,y2:0,
                stop:0 {accent}, stop:1 #2ea4d8
            );
            border-radius: 8px;
        }}

        QLabel#pageTitle {{
            font-size: 22px;
            font-weight: 600;
            color: #ffffff;
        }}

        QLabel#sessionLabel {{
            font-size: 19px;
            font-weight: 600;
            color: {accent};
            margin-bottom: 5px;
        }}

        QLabel#timerBig {{
            font-size: 72px;
            font-weight: 800;
            color: #ffffff;
            margin: 20px;
        }}
        
        QLabel#cyclesLabel {{
            font-size: 16px;
            font-weight: 600;
            color: #aad4e8;
        }}
        
        QLabel#overrideLabel {{
            font-size: 13px;
            font-weight: 600;
            color: #FF6B6B;
            padding: 5px;
            background: rgba(255, 107, 107, 0.1);
            border-radius: 5px;
        }}

        GlassPanel QLabel {{
            color: #f8f9fb;
            font-size: 15px;
            font-weight: 500;
        }}

        QLineEdit, QSpinBox, QListWidget {{
            background: rgba(255,255,255,0.06);
            border-radius: 6px;
            border: 1px solid rgba(255,255,255,0.10);
            color: #ffffff;
            padding: 6px;
        }}
        
        QLineEdit:focus, QSpinBox:focus {{
            border: 1px solid {accent};
        }}
        
        QFormLayout QLabel {{
            color: #e0e6ea;
            font-weight: 500;
        }}
        
        QComboBox {{
            background: rgba(255,255,255,0.06);
            border-radius: 6px;
            border: 1px solid rgba(255,255,255,0.10);
            color: #ffffff;
            padding: 6px;
            min-width: 60px;
        }}
        
        QComboBox:focus {{
            border: 1px solid {accent};
        }}
        
        QComboBox::drop-down {{
            border: none;
        }}
        
        QComboBox::down-arrow {{
            image: none;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 5px solid #ffffff;
            margin-right: 5px;
        }}
        
        QComboBox QAbstractItemView {{
            background: #1a1c1e;
            color: #ffffff;
            selection-background-color: {accent};
            border: 1px solid {accent};
        }}
        
        QCheckBox {{
            color: #e0e6ea;
            spacing: 8px;
        }}
        
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border-radius: 4px;
            border: 2px solid rgba(255,255,255,0.3);
            background: rgba(255,255,255,0.05);
        }}
        
        QCheckBox::indicator:checked {{
            background: {accent};
            border-color: {accent};
        }}
        
        QCheckBox::indicator:checked::after {{
            content: "✓";
            color: #ffffff;
        }}
        """

        self.setStyleSheet(qss)

    def cleanup(self):
        """Cleanup on exit."""
        try:
            # Stop timers
            self.timer.stop()
            self.dashboard_timer.stop()
            self.blink_timer.stop()
            
            # Save state
            with state_lock:
                save_state(self.state)

            # Stop killer thread
            if self.killer:
                self.killer.stop()
                self.killer.join(timeout=2)

            # Remove blocks if goal completed
            with state_lock:
                if self.state.get("minutes_today", 0) >= self.cfg["daily_required_minutes"]:
                    if self.admin:
                        remove_hosts_block(self.cfg)

            safe_log("SHUTDOWN", "Clean exit")
        except Exception as e:
            safe_log("CLEANUP_ERROR", str(e))

    def closeEvent(self, event):
        """Handle window close with proper tray behavior."""
        # Import here to ensure it's available in frozen exe
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel
        from PyQt5.QtCore import Qt
        
        # Force quit from tray
        if self.force_quit:
            if self.running and not self.paused:
                self.pause()
            self.cleanup()
            if self.has_tray and self.tray_icon:
                self.tray_icon.hide()
            if self.mini_timer:
                self.mini_timer.close()
            event.accept()
            QApplication.quit()
            return
        
        # Handle running session first
        if self.running:
            dialog = QDialog(self)
            dialog.setWindowTitle("Session Running")
            dialog.setModal(True)
            dialog.setFixedSize(450, 180)
            dialog.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
            
            layout = QVBoxLayout(dialog)
            layout.setSpacing(15)
            layout.setContentsMargins(25, 25, 25, 25)
            
            label = QLabel("⚠️ A study session is currently running!")
            label.setStyleSheet("font-size: 15px; font-weight: bold; color: #ffffff;")
            label.setAlignment(Qt.AlignCenter)
            layout.addWidget(label)
            
            info_label = QLabel("What would you like to do with your progress?")
            info_label.setStyleSheet("font-size: 12px; color: #cccccc;")
            info_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(info_label)
            
            layout.addSpacing(10)
            
            btn_layout = QHBoxLayout()
            btn_layout.setSpacing(10)
            
            btn_save = QPushButton("💾 Save & Pause")
            btn_save.setMinimumHeight(40)
            btn_save.setStyleSheet("""
                QPushButton {
                    background: #28a745;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    font-size: 13px;
                    font-weight: bold;
                    padding: 8px 15px;
                }
                QPushButton:hover {
                    background: #218838;
                }
            """)
            btn_save.clicked.connect(lambda: dialog.done(1))
            
            btn_discard = QPushButton("🗑️ Discard")
            btn_discard.setMinimumHeight(40)
            btn_discard.setStyleSheet("""
                QPushButton {
                    background: #dc3545;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    font-size: 13px;
                    font-weight: bold;
                    padding: 8px 15px;
                }
                QPushButton:hover {
                    background: #c82333;
                }
            """)
            btn_discard.clicked.connect(lambda: dialog.done(2))
            
            btn_cancel = QPushButton("❌ Cancel")
            btn_cancel.setMinimumHeight(40)
            btn_cancel.setStyleSheet("""
                QPushButton {
                    background: #6c757d;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    font-size: 13px;
                    font-weight: bold;
                    padding: 8px 15px;
                }
                QPushButton:hover {
                    background: #5a6268;
                }
            """)
            btn_cancel.clicked.connect(lambda: dialog.done(0))
            
            btn_layout.addWidget(btn_save)
            btn_layout.addWidget(btn_discard)
            btn_layout.addWidget(btn_cancel)
            
            layout.addLayout(btn_layout)
            
            dialog.setStyleSheet("""
                QDialog {
                    background-color: #2b2b2b;
                    border: 2px solid #444;
                    border-radius: 10px;
                }
            """)
            
            result = dialog.exec_()
            
            if result == 0:
                event.ignore()
                return
            elif result == 1:
                if not self.paused:
                    self.pause()
        
        # Handle minimize to tray or quit
        if self.has_tray:
            dialog = QDialog(self)
            dialog.setWindowTitle("Close Application")
            dialog.setModal(True)
            dialog.setFixedSize(450, 180)
            dialog.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
            
            layout = QVBoxLayout(dialog)
            layout.setSpacing(15)
            layout.setContentsMargins(25, 25, 25, 25)
            
            label = QLabel("How would you like to close?")
            label.setStyleSheet("font-size: 15px; font-weight: bold; color: #ffffff;")
            label.setAlignment(Qt.AlignCenter)
            layout.addWidget(label)
            
            info_label = QLabel("Minimize keeps the app running in the background.")
            info_label.setStyleSheet("font-size: 11px; color: #cccccc;")
            info_label.setAlignment(Qt.AlignCenter)
            info_label.setWordWrap(True)
            layout.addWidget(info_label)
            
            layout.addSpacing(10)
            
            btn_layout = QHBoxLayout()
            btn_layout.setSpacing(10)
            
            btn_minimize = QPushButton("📥 Minimize to Tray")
            btn_minimize.setMinimumHeight(40)
            btn_minimize.setStyleSheet("""
                QPushButton {
                    background: #007bff;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    font-size: 13px;
                    font-weight: bold;
                    padding: 8px 15px;
                }
                QPushButton:hover {
                    background: #0056b3;
                }
            """)
            btn_minimize.clicked.connect(lambda: dialog.done(1))
            
            btn_quit = QPushButton("🚪 Quit Completely")
            btn_quit.setMinimumHeight(40)
            btn_quit.setStyleSheet("""
                QPushButton {
                    background: #dc3545;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    font-size: 13px;
                    font-weight: bold;
                    padding: 8px 15px;
                }
                QPushButton:hover {
                    background: #c82333;
                }
            """)
            btn_quit.clicked.connect(lambda: dialog.done(2))
            
            btn_cancel = QPushButton("❌ Cancel")
            btn_cancel.setMinimumHeight(40)
            btn_cancel.setStyleSheet("""
                QPushButton {
                    background: #6c757d;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    font-size: 13px;
                    font-weight: bold;
                    padding: 8px 15px;
                }
                QPushButton:hover {
                    background: #5a6268;
                }
            """)
            btn_cancel.clicked.connect(lambda: dialog.done(0))
            
            btn_layout.addWidget(btn_minimize)
            btn_layout.addWidget(btn_quit)
            btn_layout.addWidget(btn_cancel)
            
            layout.addLayout(btn_layout)
            
            dialog.setStyleSheet("""
                QDialog {
                    background-color: #2b2b2b;
                    border: 2px solid #444;
                    border-radius: 10px;
                }
            """)
            
            result = dialog.exec_()
            
            if result == 1:
                event.ignore()
                self.minimize_to_tray()
            elif result == 2:
                self.cleanup()
                if self.tray_icon:
                    self.tray_icon.hide()
                if self.mini_timer:
                    self.mini_timer.close()
                event.accept()
                QApplication.quit()
            else:
                event.ignore()
        else:
            self.cleanup()
            if self.mini_timer:
                self.mini_timer.close()
            event.accept()
def main():
    """Main entry point."""
    try:
        cfg = load_config()
        state = load_state()
        today = datetime.now().strftime("%Y-%m-%d")
        
        if state.get("date") == today:
            mins = state.get("minutes_today", 0)
            if mins < cfg["daily_required_minutes"] and is_admin():
                apply_hosts_block(cfg)
                safe_log("STARTUP", f"Applied blocking - {mins}/{cfg['daily_required_minutes']} min")
    except Exception as e:
        safe_log("STARTUP_ERROR", str(e))

    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps)
    
    # CRITICAL: Allow app to run with window closed (for tray functionality)
    if QSystemTrayIcon.isSystemTrayAvailable():
        app.setQuitOnLastWindowClosed(False)
        safe_log("APP", "Tray mode enabled - app will run when window closed")
    else:
        safe_log("APP", "No system tray - app will quit when window closed")
    
    w = StudyLockWindow()
    w.show()
    
    return app.exec_()
if __name__ == "__main__":
    sys.exit(main())
