import os
import shutil
import tkinter as tk
from tkinter import messagebox, filedialog
import winreg
import sys
import ctypes
import threading
import webbrowser
import pystray
from PIL import Image

APP_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
if getattr(sys, 'frozen', False):
    BUNDLE_DIR = sys._MEIPASS
else:
    BUNDLE_DIR = APP_DIR
APP_ICON = os.path.join(BUNDLE_DIR, 'QQ.ico')

FIRST_RUN_FLAG = os.path.join(APP_DIR, '.qeb_first_run')
QQ_PATH_CACHE = os.path.join(APP_DIR, '.qeb_qq_path')
SIGNAL_FILE = os.path.join(APP_DIR, '.qeb_show_signal')

tray_icon = None
gui_running = False


def find_qq_msg_wav():
    # Check cache first
    if os.path.isfile(QQ_PATH_CACHE):
        try:
            with open(QQ_PATH_CACHE, 'r', encoding='utf-8') as f:
                cached = f.read().strip()
            if cached and os.path.isfile(cached):
                return cached
        except Exception:
            pass

    import subprocess

    # Find QQ.exe path from running process
    try:
        cmd = ['wmic', 'process', 'where', "Name='QQ.exe'", 'get', 'ExecutablePath', '/FORMAT:LIST']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        qq_dirs = set()
        for line in result.stdout.splitlines():
            if line.startswith('ExecutablePath='):
                p = line.split('=', 1)[1].strip()
                if p:
                    qq_dirs.add(os.path.dirname(p))

        for qq_dir in qq_dirs:
            versions_dir = os.path.join(qq_dir, 'versions')
            if os.path.isdir(versions_dir):
                try:
                    for ver in os.listdir(versions_dir):
                        ver_path = os.path.join(versions_dir, ver)
                        if not os.path.isdir(ver_path):
                            continue
                        for rsrc in ['resources', 'Resources']:
                            candidate = os.path.join(ver_path, rsrc, 'app', 'resource', 'msg.wav')
                            if os.path.isfile(candidate):
                                save_qq_path(candidate)
                                return candidate
                except PermissionError:
                    pass

            for rsrc in ['resources', 'Resources']:
                candidate = os.path.join(qq_dir, rsrc, 'app', 'resource', 'msg.wav')
                if os.path.isfile(candidate):
                    save_qq_path(candidate)
                    return candidate
    except Exception:
        pass

    # Fallback: scan drives
    for d in range(67, 91):
        drive = chr(d) + ':\\'
        if not os.path.isdir(drive):
            continue
        for name in ['QQ', 'Tencent\\QQ', 'Program Files\\Tencent\\QQ',
                      'Program Files (x86)\\Tencent\\QQ']:
            base = os.path.join(drive, name)
            if not os.path.isdir(base):
                continue
            versions_dir = os.path.join(base, 'versions')
            if os.path.isdir(versions_dir):
                try:
                    for ver in os.listdir(versions_dir):
                        ver_path = os.path.join(versions_dir, ver)
                        if not os.path.isdir(ver_path):
                            continue
                        for rsrc in ['resources', 'Resources']:
                            candidate = os.path.join(ver_path, rsrc, 'app', 'resource', 'msg.wav')
                            if os.path.isfile(candidate):
                                save_qq_path(candidate)
                                return candidate
                except PermissionError:
                    continue

    return None


def save_qq_path(path):
    try:
        with open(QQ_PATH_CACHE, 'w', encoding='utf-8') as f:
            f.write(path)
    except Exception:
        pass


def get_wav_path(target_dir):
    path = os.path.join(BUNDLE_DIR, target_dir, 'msg.wav')
    if os.path.isfile(path):
        return path
    path = os.path.join(APP_DIR, target_dir, 'msg.wav')
    if os.path.isfile(path):
        return path
    return None


def file_hash(filepath):
    import hashlib
    h = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def detect_current_sound():
    qq_msg = find_qq_msg_wav()
    if not qq_msg:
        return None
    qq_hash = file_hash(qq_msg)
    for name, label in [('0', '安静'), ('fj', '飞机音'), ('zj', '战斗机音'), ('yb', '原本音频')]:
        wav = get_wav_path(name)
        if wav and file_hash(wav) == qq_hash:
            return label
    return '自定义'


def replace_sound(target_dir, show_msg=True):
    msg_path = find_qq_msg_wav()
    if not msg_path:
        if show_msg:
            messagebox.showerror("错误", "未找到QQ，请先打开QQ")
        return False

    target_wav = get_wav_path(target_dir)
    if not target_wav:
        if show_msg:
            messagebox.showerror("错误", f"目标音频文件不存在: {target_dir}/msg.wav")
        return False

    try:
        attrs = os.stat(msg_path).st_mode
        os.chmod(msg_path, 0o666)
        shutil.copy2(target_wav, msg_path)
        os.chmod(msg_path, attrs)
        if show_msg:
            messagebox.showinfo("Success", "Success")
        return True
    except Exception as e:
        if show_msg:
            messagebox.showerror("错误", f"替换失败: {str(e)}")
        return False


def is_autorun_enabled():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run', 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, '企鹅别叫')
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def set_autorun(enabled):
    try:
        key_path = r'Software\Microsoft\Windows\CurrentVersion\Run'
        exe_path = os.path.abspath(sys.argv[0]) if getattr(sys, 'frozen', False) else os.path.abspath(__file__)
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        if enabled:
            winreg.SetValueEx(key, '企鹅别叫', 0, winreg.REG_SZ, exe_path)
        else:
            winreg.DeleteValue(key, '企鹅别叫')
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def get_icon():
    if os.path.isfile(APP_ICON):
        return Image.open(APP_ICON)
    return None


def show_initial_popup():
    root = tk.Tk()
    root.withdraw()
    if os.path.isfile(APP_ICON):
        root.iconbitmap(APP_ICON)

    popup = tk.Toplevel(root)
    popup.title("企鹅别叫--by lcgd2023")
    popup.geometry("300x150")
    popup.resizable(False, False)
    if os.path.isfile(APP_ICON):
        popup.iconbitmap(APP_ICON)

    popup.update_idletasks()
    x = (popup.winfo_screenwidth() - 300) // 2
    y = (popup.winfo_screenheight() - 150) // 2
    popup.geometry(f'300x150+{x}+{y}')

    tk.Label(popup, text="欢迎使用 企鹅别叫--by lcgd2023", font=("Microsoft YaHei", 12)).pack(pady=20)

    btn_frame = tk.Frame(popup)
    btn_frame.pack()

    def enter():
        popup.destroy()
        root.destroy()
        show_main_gui()

    tk.Button(btn_frame, text="继续", width=10, command=enter,
              bg="#4CAF50", fg="white", font=("Microsoft YaHei", 10)).pack(side=tk.LEFT, padx=10)
    tk.Button(btn_frame, text="开始", width=10, command=enter,
              bg="#F44336", fg="white", font=("Microsoft YaHei", 10)).pack(side=tk.RIGHT, padx=10)

    root.mainloop()


def show_main_gui():
    global gui_running

    root = tk.Tk()
    root.title("企鹅别叫--by lcgd2023")
    root.geometry("450x380")
    root.resizable(False, False)
    if os.path.isfile(APP_ICON):
        root.iconbitmap(APP_ICON)

    root.update_idletasks()
    x = (root.winfo_screenwidth() - 450) // 2
    y = (root.winfo_screenheight() - 350) // 2
    root.geometry(f'450x350+{x}+{y}')

    tk.Label(root, text="企鹅别叫--by lcgd2023", font=("Microsoft YaHei", 14, "bold")).pack(pady=10)

    qq_msg = find_qq_msg_wav()
    if qq_msg:
        tk.Label(root, text=f"已找到: {qq_msg}", font=("Microsoft YaHei", 9), fg="green", wraplength=420, justify="left").pack()
        current = detect_current_sound()
        if current:
            tk.Label(root, text=f"当前提示音: {current}", font=("Microsoft YaHei", 9, "bold"), fg="#333").pack()
    else:
        tk.Label(root, text="未找到QQ，请先打开QQ", font=("Microsoft YaHei", 9), fg="red").pack()

    func_frame = tk.LabelFrame(root, text="音效选项", font=("Microsoft YaHei", 10))
    func_frame.pack(fill=tk.X, padx=20, pady=8)

    tk.Button(func_frame, text="安静", width=8, command=lambda: replace_sound('0'),
              bg="#8BC34A", fg="white", font=("Microsoft YaHei", 10)).pack(side=tk.LEFT, padx=5, pady=8)
    tk.Button(func_frame, text="飞机音", width=8, command=lambda: replace_sound('fj'),
              bg="#607D8B", fg="white", font=("Microsoft YaHei", 10)).pack(side=tk.LEFT, padx=5, pady=8)
    tk.Button(func_frame, text="战斗机音", width=8, command=lambda: replace_sound('zj'),
              bg="#FF9800", fg="white", font=("Microsoft YaHei", 10)).pack(side=tk.LEFT, padx=5, pady=8)
    tk.Button(func_frame, text="返回原本音频", width=10, command=lambda: replace_sound('yb'),
              bg="#9C27B0", fg="white", font=("Microsoft YaHei", 10)).pack(side=tk.LEFT, padx=5, pady=8)

    def choose_custom():
        file_path = filedialog.askopenfilename(
            title="选择wav音频文件",
            filetypes=[("WAV音频", "*.wav"), ("所有文件", "*.*")]
        )
        if not file_path:
            return
        if not file_path.lower().endswith('.wav'):
            messagebox.showerror("错误", "请选择wav格式的音频文件")
            return
        msg_path = find_qq_msg_wav()
        if not msg_path:
            messagebox.showerror("错误", "未找到QQ，请先打开QQ")
            return
        try:
            attrs = os.stat(msg_path).st_mode
            os.chmod(msg_path, 0o666)
            shutil.copy2(file_path, msg_path)
            os.chmod(msg_path, attrs)
            messagebox.showinfo("Success", "Success")
        except Exception as e:
            messagebox.showerror("错误", f"替换失败: {str(e)}")

    tk.Button(func_frame, text="自定义", width=8, command=choose_custom,
              bg="#E91E63", fg="white", font=("Microsoft YaHei", 10)).pack(side=tk.LEFT, padx=5, pady=8)

    auto_frame = tk.LabelFrame(root, text="自启动设置", font=("Microsoft YaHei", 10))
    auto_frame.pack(fill=tk.X, padx=20, pady=8)

    auto_var = tk.BooleanVar(value=is_autorun_enabled())

    def on_auto_toggle():
        set_autorun(auto_var.get())

    tk.Checkbutton(auto_frame, text="开机自动运行", variable=auto_var,
                   command=on_auto_toggle, font=("Microsoft YaHei", 10)).pack(pady=5)

    link = tk.Label(root, text="项目地址", fg="blue", cursor="hand2", font=("Microsoft YaHei", 9, "underline"))
    link.pack(pady=5)
    link.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/lcgd2023/QQquiet"))

    def on_close():
        global gui_running
        gui_running = False
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    gui_running = True
    root.mainloop()


def start_tray():
    global tray_icon, gui_running

    def on_show(icon, item):
        if not gui_running:
            threading.Thread(target=show_main_gui, daemon=True).start()

    def on_exit(icon, item):
        icon.stop()

    def check_signal():
        while True:
            try:
                if os.path.exists(SIGNAL_FILE):
                    os.remove(SIGNAL_FILE)
                    if not gui_running:
                        threading.Thread(target=show_main_gui, daemon=True).start()
            except Exception:
                pass
            time.sleep(0.5)

    tray_icon = pystray.Icon("企鹅别叫", get_icon(), "企鹅别叫--by lcgd2023", menu=pystray.Menu(
        pystray.MenuItem("打开设置", on_show, default=True),
        pystray.MenuItem("退出", on_exit)
    ))

    threading.Thread(target=check_signal, daemon=True).start()
    tray_icon.run()


if __name__ == "__main__":
    import time
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "企鹅别叫lcgd2023")
    if ctypes.windll.kernel32.GetLastError() == 183:
        try:
            open(SIGNAL_FILE, 'w').close()
        except Exception:
            pass
        sys.exit()

    is_first_run = not os.path.exists(FIRST_RUN_FLAG)

    if is_first_run:
        open(FIRST_RUN_FLAG, 'w').close()
        set_autorun(True)
        show_initial_popup()
    elif is_autorun_enabled():
        start_tray()
    else:
        show_initial_popup()
