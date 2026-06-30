import tkinter as tk
from tkinter import ttk, messagebox, filedialog, Toplevel, Canvas
from PIL import Image, ImageTk
import asyncio
import threading
import os
import sys
import re
from lefuxin_driver import LefuxinDriver
from renderer import Renderer
from image_manager import ImageManager
import bleak

VERSION = "1.0.4"

class InsertImageDialog(Toplevel):
    def __init__(self, parent, default_size=100):
        super().__init__(parent)
        self.title("Вставить изображение")
        self.geometry("450x250")
        self.result = None
        self.resizable(False, False)

        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        tab_file = ttk.Frame(notebook)
        notebook.add(tab_file, text="Файл")
        ttk.Label(tab_file, text="Выберите файл изображения:").pack(pady=10)
        ttk.Button(tab_file, text="Обзор...", command=self.choose_file).pack(pady=5)

        tab_url = ttk.Frame(notebook)
        notebook.add(tab_url, text="Ссылка")
        ttk.Label(tab_url, text="Введите URL:").pack(pady=10)
        self.url_entry = ttk.Entry(tab_url, width=50)
        self.url_entry.pack(pady=5)
        ttk.Button(tab_url, text="Вставить", command=self.insert_url).pack(pady=5)

        size_frame = ttk.Frame(self)
        size_frame.pack(pady=5)
        ttk.Label(size_frame, text="Размер (%):").pack(side=tk.LEFT)
        self.size_var = tk.IntVar(value=default_size)
        ttk.Scale(size_frame, from_=20, to=200, orient=tk.HORIZONTAL, 
                  variable=self.size_var, length=150).pack(side=tk.LEFT, padx=5)
        self.size_label = ttk.Label(size_frame, text="100%", width=5)
        self.size_label.pack(side=tk.LEFT)
        self.size_var.trace('w', lambda *args: self.size_label.config(text=f"{self.size_var.get()}%"))

        ttk.Button(self, text="Отмена", command=self.destroy).pack(pady=5)

        self.grab_set()
        self.wait_window()

    def choose_file(self):
        filetypes = [("Изображения", "*.png *.jpg *.jpeg *.bmp *.gif"), ("Все файлы", "*.*")]
        path = filedialog.askopenfilename(title="Выберите картинку", filetypes=filetypes)
        if path:
            self.result = (path, self.size_var.get())
            self.destroy()

    def insert_url(self):
        url = self.url_entry.get().strip()
        if url:
            self.result = (url, self.size_var.get())
            self.destroy()

class PrinterApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"MXW01 Bluetooth Printer v{VERSION}")
        self.root.geometry("900x700")
        
        # Устанавливаем иконку окна и панели задач
        try:
            if getattr(sys, 'frozen', False):
                icon_path = os.path.join(sys._MEIPASS, 'app.ico')
            else:
                icon_path = 'app.ico'
            
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except:
            pass
        
        # Устанавливаем AppUserModelID для панели задач (Windows)
        try:
            import ctypes
            app_id = f'MXW01.Printer.{VERSION}'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except:
            pass
        
        self.driver = None
        self.font_path = None
        self.font_name = None
        self.renderer = Renderer(font_size=20)
        self.style = ttk.Style()
        self.preview_canvas = None
        self.set_theme("light")

        menubar = tk.Menu(root)
        root.config(menu=menubar)
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Настройки", menu=settings_menu)
        settings_menu.add_command(label="Светлая тема", command=lambda: self.set_theme("light"))
        settings_menu.add_command(label="Тёмная тема", command=lambda: self.set_theme("dark"))
        settings_menu.add_separator()
        settings_menu.add_command(label="О программе", command=self.show_about)

        toolbar = ttk.Frame(root)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        ttk.Button(toolbar, text="Сканировать", command=self.scan_devices).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Подключиться", command=self.connect_device).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Вставить картинку", command=self.insert_image).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Вставить QR", command=self.insert_qr).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Печать", command=self.print_content).pack(side=tk.LEFT, padx=2)

        size_frame = ttk.Frame(toolbar)
        size_frame.pack(side=tk.RIGHT, padx=10)

        ttk.Label(size_frame, text="Текст:").pack(side=tk.LEFT)
        self.font_size_var = tk.IntVar(value=20)
        ttk.Scale(size_frame, from_=10, to=40, orient=tk.HORIZONTAL, 
                  variable=self.font_size_var, length=80, 
                  command=self.on_font_size_change).pack(side=tk.LEFT, padx=5)
        self.font_size_label = ttk.Label(size_frame, text="20", width=2)
        self.font_size_label.pack(side=tk.LEFT)

        ttk.Separator(size_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=5, fill=tk.Y)

        ttk.Label(size_frame, text="QR:").pack(side=tk.LEFT)
        self.qr_size_var = tk.IntVar(value=3)
        ttk.Scale(size_frame, from_=1, to=10, orient=tk.HORIZONTAL, 
                  variable=self.qr_size_var, length=80, 
                  command=self.on_qr_size_change).pack(side=tk.LEFT, padx=5)
        self.qr_size_label = ttk.Label(size_frame, text="3", width=2)
        self.qr_size_label.pack(side=tk.LEFT)

        ttk.Separator(size_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=5, fill=tk.Y)

        ttk.Label(size_frame, text="IMG:").pack(side=tk.LEFT)
        self.img_size_var = tk.IntVar(value=100)
        ttk.Scale(size_frame, from_=20, to=200, orient=tk.HORIZONTAL, 
                  variable=self.img_size_var, length=80, 
                  command=self.on_img_size_change).pack(side=tk.LEFT, padx=5)
        self.img_size_label = ttk.Label(size_frame, text="100%", width=4)
        self.img_size_label.pack(side=tk.LEFT)

        main_panel = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        main_panel.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        left_frame = ttk.Frame(main_panel)
        main_panel.add(left_frame, weight=1)

        bt_frame = ttk.LabelFrame(left_frame, text="Bluetooth устройства")
        bt_frame.pack(fill=tk.X, pady=(0,5))
        self.device_listbox = tk.Listbox(bt_frame, height=4)
        self.device_listbox.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        editor_frame = ttk.LabelFrame(left_frame, text="Редактор (Markdown + [IMG:...] [QR:...])")
        editor_frame.pack(fill=tk.BOTH, expand=True)
        self.text_editor = tk.Text(editor_frame, wrap=tk.WORD, font=("Consolas", 10))
        self.text_editor.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        preview_frame = ttk.LabelFrame(main_panel, text="Предпросмотр")
        main_panel.add(preview_frame, weight=2)

        self.preview_canvas = Canvas(preview_frame, bg='lightgray', highlightthickness=0)
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)

        preview_toolbar = ttk.Frame(preview_frame)
        preview_toolbar.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Button(preview_toolbar, text="-", width=3, command=self.zoom_out).pack(side=tk.LEFT)
        ttk.Button(preview_toolbar, text="+", width=3, command=self.zoom_in).pack(side=tk.LEFT)
        ttk.Button(preview_toolbar, text="Обновить", command=self.update_preview).pack(side=tk.RIGHT, padx=5)

        self.preview_image = None
        self.preview_tk = None
        self.scale_factor = 1.0

        self.status_var = tk.StringVar(value="Готов")
        status_bar = ttk.Label(root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.text_editor.bind("<KeyRelease>", lambda e: self.auto_preview())
        self.auto_preview_timer = None

    def show_about(self):
        messagebox.showinfo("О программе", 
            f"MXW01 Bluetooth Printer v{VERSION}\n\n"
            "Печать на термопринтере MXW01 через Bluetooth.\n"
            "Поддержка Markdown, изображений и QR-кодов.\n\n"
            "© 2026 | GitHub: https://github.com/fjk-dev/MXW01-Printer")

    def on_font_size_change(self, value):
        size = int(float(value))
        self.font_size_var.set(size)
        self.font_size_label.config(text=str(size))
        self.renderer.font_size = size
        self.renderer._init_fonts()

    def on_qr_size_change(self, value):
        size = int(float(value))
        self.qr_size_var.set(size)
        self.qr_size_label.config(text=str(size))

    def on_img_size_change(self, value):
        size = int(float(value))
        self.img_size_var.set(size)
        self.img_size_label.config(text=f"{size}%")

    def set_theme(self, theme):
        if theme == "dark":
            self.style.theme_use("clam")
            bg = "#2e2e2e"
            fg = "white"
            self.style.configure(".", background=bg, foreground=fg)
            self.style.map("TButton", background=[("active", "#444")])
            if self.preview_canvas:
                self.preview_canvas.config(bg='#1e1e1e')
        else:
            self.style.theme_use("vista")
            bg = "SystemButtonFace"
            fg = "black"
            self.style.configure(".", background=bg, foreground=fg)
            if self.preview_canvas:
                self.preview_canvas.config(bg='lightgray')

    def async_task(self, coro, callback=None, error_callback=None):
        def runner():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(coro)
                if callback:
                    self.root.after(0, callback, result)
            except Exception as e:
                if error_callback:
                    self.root.after(0, error_callback, str(e))
                else:
                    self.root.after(0, lambda: messagebox.showerror("Ошибка", str(e)))
            finally:
                loop.close()
        threading.Thread(target=runner, daemon=True).start()

    def scan_devices(self):
        self.status_var.set("Сканирование...")
        async def scan():
            devices = await bleak.BleakScanner.discover()
            printers = [(d.name, d.address) for d in devices if d.name and 'mxw01' in d.name.lower()]
            return printers
        def update(printers):
            self.device_listbox.delete(0, tk.END)
            for name, addr in printers:
                self.device_listbox.insert(tk.END, f"{name}  ({addr})")
            self.status_var.set(f"Найдено: {len(printers)}")
        self.async_task(scan(), update)

    def connect_device(self):
        sel = self.device_listbox.curselection()
        if not sel:
            messagebox.showwarning("Не выбрано", "Выберите устройство")
            return
        entry = self.device_listbox.get(sel[0])
        addr = entry.split('(')[-1].rstrip(')')
        self.status_var.set(f"Подключение к {addr}...")
        async def connect():
            driver = LefuxinDriver()
            await driver.connect(addr)
            return driver
        def on_connected(driver):
            self.driver = driver
            self.status_var.set(f"Подключено к {addr}")
        self.async_task(connect(), on_connected)

    def insert_image(self):
        dialog = InsertImageDialog(self.root, self.img_size_var.get())
        if dialog.result:
            source, size = dialog.result
            self.text_editor.insert(tk.INSERT, f"[IMG:{source}|{size}]")
            self.update_preview()

    def insert_qr(self):
        dialog = InsertQRDialog(self.root, self.qr_size_var.get())
        if dialog.result:
            self.text_editor.insert(tk.INSERT, dialog.result)
            self.update_preview()

    def auto_preview(self):
        if self.auto_preview_timer:
            self.root.after_cancel(self.auto_preview_timer)
        self.auto_preview_timer = self.root.after(500, self.update_preview)

    def update_preview(self):
        text = self.text_editor.get("1.0", tk.END)
        if not text.strip():
            self.preview_canvas.delete("all")
            return
        try:
            img = self.renderer.render_to_image(text, self.qr_size_var.get(), self.img_size_var.get())
            self.preview_image = img
            self.scale_factor = 1.0
            self._draw_preview()
            self.status_var.set(f"Предпросмотр: {img.width}x{img.height}")
        except Exception as e:
            self.status_var.set(f"Ошибка рендеринга: {e}")

       def _draw_preview(self):
        if not self.preview_image:
            return
        w = int(self.preview_image.width * self.scale_factor)
        h = int(self.preview_image.height * self.scale_factor)
        resized = self.preview_image.resize((w, h), Image.Resampling.NEAREST)
        # Инвертируем для предпросмотра (на светлом фоне должны быть чёрные буквы)
        inverted = resized.point(lambda x: 1 - x)
        self.preview_tk = ImageTk.BitmapImage(inverted, foreground="black", background="white")
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(w//2, h//2, image=self.preview_tk)
        self.preview_canvas.config(scrollregion=(0, 0, w, h))

    def zoom_in(self):
        self.scale_factor *= 1.2
        self._draw_preview()

    def zoom_out(self):
        self.scale_factor *= 0.8
        self._draw_preview()

    def print_content(self):
        if not self.driver:
            messagebox.showwarning("Нет подключения", "Подключитесь к принтеру")
            return
        text = self.text_editor.get("1.0", tk.END)
        if not text.strip():
            messagebox.showwarning("Пусто", "Нечего печатать")
            return
        self.status_var.set("Генерация изображения...")
        try:
            img = self.renderer.render_to_image(text, self.qr_size_var.get(), self.img_size_var.get())
        except Exception as e:
            messagebox.showerror("Ошибка рендеринга", str(e))
            return
        printer_bytes = ImageManager.to_printer_bytes(img)
        height = img.height
        self.status_var.set(f"Отправка на печать ({height} строк)...")
        async def print_job():
            await self.driver.print_image(printer_bytes, height)
        def done(_=None):
            self.status_var.set("Печать завершена")
        self.async_task(print_job(), done)

class InsertQRDialog(Toplevel):
    def __init__(self, parent, default_size=3):
        super().__init__(parent)
        self.title("Вставить QR-код")
        self.geometry("400x180")
        self.result = None
        self.resizable(False, False)

        ttk.Label(self, text="Текст или ссылка для QR-кода:").pack(pady=10)
        self.text_entry = ttk.Entry(self, width=50)
        self.text_entry.pack(pady=5)

        size_frame = ttk.Frame(self)
        size_frame.pack(pady=5)
        ttk.Label(size_frame, text="Размер:").pack(side=tk.LEFT)
        self.size_var = tk.IntVar(value=default_size)
        ttk.Scale(size_frame, from_=1, to=10, orient=tk.HORIZONTAL, 
                  variable=self.size_var, length=150).pack(side=tk.LEFT, padx=5)
        self.size_label = ttk.Label(size_frame, text=str(default_size), width=3)
        self.size_label.pack(side=tk.LEFT)
        self.size_var.trace('w', lambda *args: self.size_label.config(text=str(self.size_var.get())))

        ttk.Button(self, text="Вставить", command=self.insert).pack(pady=10)

        self.grab_set()
        self.text_entry.focus_set()
        self.wait_window()

    def insert(self):
        text = self.text_entry.get().strip()
        if text:
            size = self.size_var.get()
            self.result = f"[QR:{text}|{size}]"
            self.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = PrinterApp(root)
    root.mainloop()
