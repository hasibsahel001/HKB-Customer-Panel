from abc import ABC, abstractmethod


class DeviceConnector(ABC):
    """قرارداد مشترک. در آینده APConnector هم همین را پیاده می‌کند."""

    @abstractmethod
    def connect(self): ...

    @abstractmethod
    def close(self): ...