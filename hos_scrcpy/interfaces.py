"""Abstract interfaces for HOScrcpy controllers.

Defines the contracts that all controller implementations must follow.
Enables dependency injection, testing with mocks, and consistent API surface.
"""

from abc import ABC, abstractmethod


class TouchProvider(ABC):
    """Interface for touch injection — uinput shell, Java stdin, async queue, etc."""

    @abstractmethod
    def down(self, x: int, y: int, contact: int = 0):
        """Touch down at (x, y)."""
        ...

    @abstractmethod
    def up(self, x: int, y: int, contact: int = 0):
        """Touch up at (x, y)."""
        ...

    @abstractmethod
    def move(self, x: int, y: int):
        """Move touch point to (x, y)."""
        ...

    @abstractmethod
    def click(self, x: int, y: int, duration: float = 0.05):
        """Tap at (x, y)."""
        ...

    @abstractmethod
    def swipe(self, x1: int, y1: int, x2: int, y2: int,
              duration: float = 0.3, steps: int = 10):
        """Swipe from (x1, y1) to (x2, y2)."""
        ...

    def stop(self):
        """Release resources. Optional cleanup."""
        pass


class MouseProvider(ABC):
    """Interface for mouse event injection."""

    @abstractmethod
    def down(self, button: str, x: int, y: int):
        ...

    @abstractmethod
    def up(self, button: str, x: int, y: int):
        ...

    @abstractmethod
    def move(self, x: int, y: int):
        ...

    @abstractmethod
    def click(self, button: str, x: int, y: int):
        ...

    @abstractmethod
    def wheel_up(self, x: int, y: int):
        ...

    @abstractmethod
    def wheel_down(self, x: int, y: int):
        ...

    def stop(self):
        pass


class KeyboardProvider(ABC):
    """Interface for key injection."""

    @abstractmethod
    def press(self, keycode: int):
        """Press and release a key."""
        ...

    @abstractmethod
    def input_text(self, text: str):
        """Input text (supports CJK)."""
        ...

    @abstractmethod
    def home(self):
        ...

    @abstractmethod
    def back(self):
        ...

    @abstractmethod
    def power(self):
        ...

    def stop(self):
        pass


class StreamProvider(ABC):
    """Interface for screen streaming backends."""

    @abstractmethod
    def start(self, on_frame) -> TouchProvider | None:
        """Start streaming frames to on_frame(jpeg_bytes).

        Returns a TouchProvider for touch injection, or None.
        """
        ...

    @abstractmethod
    def stop(self):
        """Stop streaming and release resources."""
        ...

    @property
    @abstractmethod
    def is_streaming(self) -> bool:
        ...


class DeviceProvider(ABC):
    """Interface for device operations."""

    @abstractmethod
    def screenshot(self) -> bytes | None:
        """Capture device screen as JPEG bytes."""
        ...

    @abstractmethod
    def execute_shell(self, cmd: str, timeout: int = 10) -> str:
        """Execute a shell command on the device."""
        ...

    @abstractmethod
    def is_online(self) -> bool:
        """Check if device is reachable."""
        ...

    @property
    @abstractmethod
    def sn(self) -> str:
        ...

    @property
    @abstractmethod
    def ip(self) -> str:
        ...
