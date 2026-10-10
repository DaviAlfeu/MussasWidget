import sys
import ctypes
from ctypes import wintypes

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QPoint, QTimer
from PyQt6.QtGui import QColor

from config import config_app
from utils import alpha_desfoque


class JanelaVidro(QWidget):
    """Janela de fundo com acrílico do Windows, posicionada logo abaixo de outra janela."""

    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._topo = None
        self._blur_ok = False
        self._cor = None

    def _aplicar_blur(self, cor, intensidade):
        class ACCENT(ctypes.Structure):
            _fields_ = [("AccentState", ctypes.c_int), ("AccentFlags", ctypes.c_int),
                        ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_int)]

        class WCA(ctypes.Structure):
            _fields_ = [("Attribute", ctypes.c_int), ("Data", ctypes.c_void_p), ("SizeOfData", ctypes.c_size_t)]

        c = QColor(cor)
        gradiente = (intensidade << 24) | (c.blue() << 16) | (c.green() << 8) | c.red()
        accent = ACCENT(4, 0, gradiente, 0)
        data = WCA(19, ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p), ctypes.sizeof(accent))
        ctypes.windll.user32.SetWindowCompositionAttribute(wintypes.HWND(int(self.winId())), ctypes.byref(data))

    def _aplicar_regiao(self):
        if sys.getwindowsversion().build >= 22000:
            pref = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(wintypes.HWND(int(self.winId())), 33, ctypes.byref(pref), 4)
            return
        dpr = self.devicePixelRatioF()
        gdi32 = ctypes.windll.gdi32
        gdi32.CreateRoundRectRgn.restype = wintypes.HRGN
        gdi32.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
        r = int(24 * dpr)
        regiao = gdi32.CreateRoundRectRgn(0, 0, int(self.width() * dpr) + 1, int(self.height() * dpr) + 1, r, r)
        ctypes.windll.user32.SetWindowRgn(wintypes.HWND(int(self.winId())), regiao, True)

    def sincronizar(self, alvo, topo, cor):
        intensidade = int(alpha_desfoque(config_app.desfoque, 0, 40))
        try:
            origem = alvo.mapToGlobal(QPoint(0, 0))
            if self._topo != topo:
                self._topo = topo
                self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, topo)
                self._blur_ok = False
            self.setGeometry(origem.x(), origem.y(), alvo.width(), alvo.height())
            if not self.isVisible():
                self.show()
            if not self._blur_ok or self._cor != (cor, intensidade):
                self._cor = (cor, intensidade)
                self._aplicar_blur(cor, intensidade)
                self._blur_ok = True
            self._aplicar_regiao()
            QTimer.singleShot(120, self._aplicar_regiao)
            ctypes.windll.user32.SetWindowPos(wintypes.HWND(int(self.winId())), wintypes.HWND(int(alvo.window().winId())),
                                              0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
        except Exception:
            pass


def atualizar_vidro(host, alvo):
    """Mantém o vidro de `host` sincronizado com o container `alvo` (cria, move, redimensiona ou esconde)."""
    if sys.platform != "win32":
        return
    vidro = getattr(host, "_vidro", None)
    if not config_app.vidro_desfocado or not host.isVisible():
        if vidro is not None:
            vidro.hide()
        return
    if vidro is None:
        vidro = host._vidro = JanelaVidro()
    topo = bool(host.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
    vidro.sincronizar(alvo, topo, config_app.cor_base)


def esconder_vidro(host):
    vidro = getattr(host, "_vidro", None)
    if vidro is not None:
        vidro.hide()
