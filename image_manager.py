import urllib.request
from io import BytesIO
from PIL import Image, ImageOps
import numpy as np
import os

class ImageManager:
    @staticmethod
    def load_image(source):
        """Загружает изображение из URL или локального пути."""
        if source.startswith(('http://', 'https://')):
            with urllib.request.urlopen(source, timeout=10) as resp:
                data = resp.read()
            return Image.open(BytesIO(data))
        elif os.path.isfile(source):
            return Image.open(source)
        else:
            raise FileNotFoundError(f"Не найден файл или URL: {source}")

    @staticmethod
    def apply_brightness_contrast(img, brightness=0, contrast=1.0):
        """Изменение яркости и контраста."""
        img = ImageOps.grayscale(img)
        arr = np.array(img, dtype=np.float32)
        arr += brightness
        arr = 128 + (arr - 128) * contrast
        np.clip(arr, 0, 255, out=arr)
        return Image.fromarray(arr.astype(np.uint8), mode='L')

    @staticmethod
    def ordered_dither(img):
        """Упорядоченный дизеринг (матрица Байера 4x4)."""
        bayer = np.array([[0,8,2,10],[12,4,14,6],[3,11,1,9],[15,7,13,5]], dtype=np.float32)
        factor = 255.0 / 16.0
        arr = np.array(img, dtype=np.float32)
        h, w = arr.shape
        res = np.zeros_like(arr)
        for y in range(h):
            for x in range(w):
                res[y,x] = 0 if arr[y,x] < bayer[y%4][x%4]*factor else 255
        return Image.fromarray(res.astype(np.uint8), mode='L')

    @staticmethod
    def floyd_dither(img):
        """Дизеринг Флойда-Стейнберга."""
        arr = np.array(img, dtype=np.float32)
        h, w = arr.shape
        for y in range(h):
            for x in range(w):
                old = arr[y,x]
                new = 0.0 if old < 128 else 255.0
                arr[y,x] = new
                err = old - new
                if x+1 < w:
                    arr[y,x+1] = np.clip(arr[y,x+1] + err * 7/16, 0, 255)
                if y+1 < h:
                    if x-1 >= 0:
                        arr[y+1,x-1] = np.clip(arr[y+1,x-1] + err * 3/16, 0, 255)
                    arr[y+1,x] = np.clip(arr[y+1,x] + err * 5/16, 0, 255)
                    if x+1 < w:
                        arr[y+1,x+1] = np.clip(arr[y+1,x+1] + err * 1/16, 0, 255)
        return Image.fromarray(arr.astype(np.uint8), mode='L')

    @staticmethod
    def simple_binarize(img):
        """Пороговая бинаризация (128)."""
        arr = np.array(img, dtype=np.uint8)
        arr = np.where(arr < 128, 0, 255).astype(np.uint8)
        return Image.fromarray(arr, mode='L')

    @classmethod
    def process_image(cls, source, width=384, brightness=0, contrast=1.0, dither='ordered'):
        """Полный пайплайн обработки изображения для принтера."""
        img = cls.load_image(source)
        # Масштабирование до ширины 384
        w_percent = width / float(img.size[0])
        h_size = int(float(img.size[1]) * w_percent)
        img = img.resize((width, h_size), Image.Resampling.LANCZOS)
        gray = cls.apply_brightness_contrast(img, brightness, contrast)
        if dither == 'ordered':
            dithered = cls.ordered_dither(gray)
        elif dither == 'floyd':
            dithered = cls.floyd_dither(gray)
        else:
            dithered = cls.simple_binarize(gray)
        return dithered.convert('1')

    @staticmethod
    def to_printer_bytes(img: Image.Image):
        """Преобразует 1-битное изображение 384xH в байты для принтера."""
        w, h = img.size
        if w != 384:
            raise ValueError("Ширина должна быть 384 пикселя")
        pixels = img.load()
        byte_width = w // 8
        result = bytearray()
        for y in range(h):
            row = bytearray(byte_width)
            for x in range(w):
                if pixels[x, y] == 0:  # чёрный
                    byte_idx = x // 8
                    bit = x % 8
                    row[byte_idx] |= (1 << bit)
            result.extend(row)
        return bytes(result)