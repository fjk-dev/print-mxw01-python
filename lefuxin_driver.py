import asyncio
from bleak import BleakClient, BleakScanner

class LefuxinDriver:
    # Сервисы, которые перебираются при подключении
    SERVICE_UUIDS = [
        '0000ae30-0000-1000-8000-00805f9b34fb',
        '0000ae00-0000-1000-8000-00805f9b34fb',
        '0000ff00-0000-1000-8000-00805f9b34fb',
    ]
    CTRL_CHAR_UUID = '0000ae01-0000-1000-8000-00805f9b34fb'
    DATA_CHAR_UUID = '0000ae03-0000-1000-8000-00805f9b34fb'

    def __init__(self):
        self.client = None
        self.ctrl_char = None
        self.data_char = None

    async def connect(self, address):
        """Подключиться к устройству по MAC-адресу."""
        self.client = BleakClient(address)
        await self.client.connect()
        await asyncio.sleep(0.6)  # как в JS setTimeout 600ms

        # Ищем сервис, содержащий обе характеристики
        for svc_uuid in self.SERVICE_UUIDS:
            try:
                service = self.client.services.get_service(svc_uuid)
                if not service:
                    continue
                ctrl = service.get_characteristic(self.CTRL_CHAR_UUID)
                data = service.get_characteristic(self.DATA_CHAR_UUID)
                if ctrl and data:
                    self.ctrl_char = ctrl
                    self.data_char = data
                    print(f"Порты найдены в сервисе: {svc_uuid}")
                    return True
            except Exception:
                continue
        raise Exception("Не найдены каналы управления AE01/AE03")

    @staticmethod
    def _crc(data: bytes) -> int:
        """Вычисление CRC как в JS (0x07 полином)."""
        c = 0
        for b in data:
            c ^= b
            for _ in range(8):
                if c & 0x80:
                    c = ((c << 1) ^ 0x07) & 0xFF
                else:
                    c = (c << 1) & 0xFF
        return c

    async def _send_command(self, cmd_id: int, payload: bytes):
        """Отправка команды в канал управления."""
        pkt = bytes([
            0x22, 0x21, cmd_id, 0x00,
            len(payload) & 0xFF, (len(payload) >> 8) & 0xFF,
            *payload,
            self._crc(payload),
            0xFF
        ])
        await self.client.write_gatt_char(self.ctrl_char, pkt, response=False)
        await asyncio.sleep(0.05)  # 50мс задержка

    async def print_image(self, image_bytes: bytes, height: int):
        """Печать изображения шириной 384, высота height."""
        if not self.ctrl_char or not self.data_char:
            raise Exception("Принтер не подключён")

        # Инициализация
        await self._send_command(0xB1, b'\x00')
        # Параметры печати: высота, 48, 0
        await self._send_command(0xA9, bytes([height & 0xFF, (height >> 8) & 0xFF, 48, 0]))

        # Отправка данных изображения порциями по 20 байт
        for i in range(0, len(image_bytes), 20):
            chunk = image_bytes[i:i+20]
            await self.client.write_gatt_char(self.data_char, chunk, response=False)
            if i % 400 == 0:
                await asyncio.sleep(0.02)  # 20мс задержка

        # Завершение печати
        await self._send_command(0xAD, b'\x00')

    async def disconnect(self):
        if self.client and self.client.is_connected:
            await self.client.disconnect()