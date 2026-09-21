import sys
import os
import signal
import urllib.request
import csv
import codecs
import json
import winreg
import webbrowser
import random
import tempfile
import subprocess
import time
from datetime import date, datetime

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QFrame, QPushButton, 
    QHBoxLayout, QVBoxLayout, QGridLayout, QDialog, QCheckBox, 
    QSystemTrayIcon, QMenu, QGraphicsScene, QGraphicsBlurEffect,
    QStackedWidget, QScrollArea, QComboBox, QSlider, QMessageBox
)
from PyQt6.QtCore import (
    QThread, Qt, QTimer, QUrl, QPoint, pyqtSignal,
    QPropertyAnimation, QParallelAnimationGroup, QEasingCurve, QAbstractAnimation, QEvent, QSharedMemory
)
from PyQt6.QtGui import (
    QFontDatabase, QCursor, QPixmap, QIcon, QAction, 
    QPainter, QPainterPath, QColor, QImage, QPen
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

APP_VERSION = "1.0.2"
URL_UPDATE_CHECK = "https://raw.githubusercontent.com/DaviAlfeu/MussasWidget/main/version.json"
URL_DOWNLOAD_EXE = "https://github.com/DaviAlfeu/MussasWidget/raw/main/WidgetAniversarios.exe"
URL_CSV_ANIVERSARIOS = "https://docs.google.com/spreadsheets/d/1W1cX9dCAFnLPjDImSB6rjSSC0GhvOX0rp_HiaHeHAGI/export?format=csv&gid=0"
URL_CSV_JOGO = "https://docs.google.com/spreadsheets/d/1W1cX9dCAFnLPjDImSB6rjSSC0GhvOX0rp_HiaHeHAGI/export?format=csv&gid=36262169"

CONFIG_FONTES = {
    "nome": {"fonte": "Lemon Milk", "tamanho": 16, "peso": "bold"},
    "data": {"fonte": "Roboto", "tamanho": 12, "peso": "light"},
    "faltam": {"fonte": "Roboto", "tamanho": 12, "peso": "light"},
    "dias": {"fonte": "Lemon Milk", "tamanho": 16, "peso": "bold"},
    "parabens_titulo": {"fonte": "Lemon Milk", "tamanho": 14, "peso": "bold"},
    "parabens_nome": {"fonte": "Lemon Milk", "tamanho": 15, "peso": "bold"},
    "lista": {"fonte": "Lemon Milk", "tamanho": 11, "peso": "bold"},
    "cal_meses": {"fonte": "Roboto", "tamanho": 11, "peso": "light"},
    "cal_titulo": {"fonte": "Lemon Milk", "tamanho": 13, "peso": "bold"},
    "cal_lista": {"fonte": "Lemon Milk", "tamanho": 11, "peso": "bold"}
}

APPDATA_DIR = os.path.join(os.getenv('APPDATA', os.path.expanduser('~')), "MussasWidget")
os.makedirs(APPDATA_DIR, exist_ok=True)

PASTA_WALLPAPERS = os.path.join(APPDATA_DIR, "Wallpapers")
os.makedirs(PASTA_WALLPAPERS, exist_ok=True)

STATE_FILE = os.path.join(APPDATA_DIR, "parabens_played.txt")
CONFIG_FILE = os.path.join(APPDATA_DIR, "config.json")

# --- FUNÇÃO E CLASSE DE THREAD PARA EVITAR TRAVAMENTOS ---
def parse_data_jogo_bg(valor):
    if not valor: return None
    valor = valor.strip()
    formatos = (
        "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
        "%d/%m/%y %H:%M:%S", "%d/%m/%y %H:%M", "%d/%m/%y"
    )
    for formato in formatos:
        try: return datetime.strptime(valor, formato)
        except ValueError: pass
    try: return datetime.fromisoformat(valor.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception: return None

class WorkerDownload(QThread):
    resultado = pyqtSignal(list, list, object, object, bytes, bytes)

    def run(self):
        dados_planilha = []
        dados_jogo = [{"imagem": "", "link": ""}, {"imagem": "", "link": ""}]
        data_inicio = None
        data_fim = None
        img_bytes1 = b""
        img_bytes2 = b""

        # 1. Baixar Aniversários em 2º plano
        try:
            req_aniv = urllib.request.urlopen(URL_CSV_ANIVERSARIOS, timeout=10)
            csv_aniv = csv.reader(codecs.iterdecode(req_aniv, 'utf-8'))
            next(csv_aniv, None)
            for r in csv_aniv:
                if len(r) >= 2 and r[0].strip():
                    dados_planilha.append((r[0].strip(), r[1].strip(), r[2].strip() if len(r) >= 3 else ""))
        except: pass

        # 2. Baixar Dados do Jogo em 2º plano
        try:
            req_jogo = urllib.request.urlopen(URL_CSV_JOGO, timeout=10)
            csv_jogo = list(csv.reader(codecs.iterdecode(req_jogo, 'utf-8')))
            if len(csv_jogo) > 1:
                linha2 = csv_jogo[1]
                if len(linha2) >= 1: dados_jogo[0]["imagem"] = linha2[0].strip()
                if len(linha2) >= 2: dados_jogo[0]["link"] = linha2[1].strip()
                if len(linha2) >= 4:
                    data_inicio = parse_data_jogo_bg(linha2[2].strip())
                    data_fim = parse_data_jogo_bg(linha2[3].strip())
            if len(csv_jogo) > 2:
                linha3 = csv_jogo[2]
                if len(linha3) >= 1: dados_jogo[1]["imagem"] = linha3[0].strip()
                if len(linha3) >= 2: dados_jogo[1]["link"] = linha3[1].strip()
        except: pass

        # 3. Baixar as imagens remotamente sem travar a interface
        try:
            if dados_jogo[0]["imagem"]:
                req = urllib.request.Request(dados_jogo[0]["imagem"], headers={'User-Agent': 'Mozilla/5.0'})
                img_bytes1 = urllib.request.urlopen(req, timeout=10).read()
        except: pass
        try:
            if dados_jogo[1]["imagem"]:
                req = urllib.request.Request(dados_jogo[1]["imagem"], headers={'User-Agent': 'Mozilla/5.0'})
                img_bytes2 = urllib.request.urlopen(req, timeout=10).read()
        except: pass

        # Envia os resultados prontos de volta para a interface principal
        self.resultado.emit(dados_planilha, dados_jogo, data_inicio, data_fim, img_bytes1, img_bytes2)

NIVEIS_DESFOQUE = [0, 20, 40, 60, 80, 100]
NIVEIS_ESPESSURA = [0.0, 0.5, 1.0, 1.5, 2.0]

def indice_desfoque(valor):
    try: valor = float(valor)
    except (TypeError, ValueError): valor = 0
    return min(range(len(NIVEIS_DESFOQUE)), key=lambda i: abs(NIVEIS_DESFOQUE[i] - valor))

def raio_desfoque(valor):
    try: valor = float(valor)
    except (TypeError, ValueError): valor = 0
    valor = max(0.0, min(100.0, valor))
    return int(round(valor * 50 / 100))

def indice_espessura(valor):
    try: valor = float(valor)
    except (TypeError, ValueError): valor = 0
    return min(range(len(NIVEIS_ESPESSURA)), key=lambda i: abs(NIVEIS_ESPESSURA[i] - valor))

def get_app_path():
    if getattr(sys, 'frozen', False):
        return os.path.abspath(sys.executable)
    return os.path.abspath(__file__)

def get_app_dir():
    return os.path.dirname(get_app_path())

def resource_path(filename):
    if getattr(sys, 'frozen', False):
        base = getattr(sys, '_MEIPASS', get_app_dir())
    else:
        base = get_app_dir()
    return os.path.join(base, filename)

def external_resource_path(filename):
    external = os.path.join(get_app_dir(), filename)
    if os.path.exists(external):
        return external
    return resource_path(filename)

def carregar_fontes():
    pastas = [
        os.path.join(get_app_dir(), "Fonts"),
        os.path.join(get_app_dir(), "WidgetAniversario", "Fonts"),
        resource_path("Fonts"),
        resource_path(os.path.join("WidgetAniversario", "Fonts")),
        "Fonts"
    ]
    for pasta in pastas:
        if os.path.exists(pasta):
            for arquivo in os.listdir(pasta):
                if arquivo.lower().endswith(('.ttf', '.otf')):
                    QFontDatabase.addApplicationFont(os.path.abspath(os.path.join(pasta, arquivo)))

def versao_tuple(valor):
    try:
        return tuple(int(p) for p in str(valor).strip().lstrip("vV").split(".")[:4])
    except Exception:
        return (0,)

def caminho_executavel_atual():
    return os.path.abspath(sys.executable) if getattr(sys, "frozen", False) else os.path.abspath(__file__)

def executar_atualizacao_bat(novo_exe):
    exe_atual = caminho_executavel_atual()
    nome_atual = os.path.basename(exe_atual)
    caminho_old = exe_atual + ".old"
    
    bat_path = os.path.join(tempfile.gettempdir(), f"mussas_update_{os.getpid()}.bat")
    
    conteudo = f"""@echo off
:: Espera 2 segundos para o processo atual morrer completamente
ping 127.0.0.1 -n 3 > NUL

:: Garante que o processo seja finalizado à força
taskkill /F /PID {os.getpid()} > NUL 2>&1
ping 127.0.0.1 -n 2 > NUL

:: Remove a versão de backup antiga, se existir
del /q "{caminho_old}" > NUL 2>&1

:: Renomeia o executável atual para .old (O Windows permite isso mesmo rodando)
move /Y "{exe_atual}" "{caminho_old}" > NUL 2>&1

:: Move o novo executável baixado para o nome original
move /Y "{novo_exe}" "{exe_atual}" > NUL 2>&1

:: Desbloqueia o arquivo para evitar o aviso do Windows Defender (SmartScreen)
powershell -windowstyle hidden -Command "Unblock-File -LiteralPath '{exe_atual}'" > NUL 2>&1

:: Inicia o app atualizado
start "" "{exe_atual}"

:: Deleta a si mesmo
del "%~f0" > NUL 2>&1
"""
    with open(bat_path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(conteudo)
        
    # Executa o bat sem criar a janela preta
    CREATE_NO_WINDOW = 0x08000000
    subprocess.Popen([bat_path], creationflags=CREATE_NO_WINDOW)

class Configuracoes:
    def __init__(self):
        self.iniciar_com_windows = False
        self.segundo_plano = False
        self.sempre_no_topo = False
        self.modo_claro = False
        self.wallpaper = "Nenhum"
        self.desfoque = 20
        self.espessura_borda = 1.0
        self.pos_x = None
        self.pos_y = None
        self.carregar()

    def carregar(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    d = json.load(f)
                    self.iniciar_com_windows = d.get("iniciar_com_windows", False)
                    self.segundo_plano = d.get("segundo_plano", False)
                    self.sempre_no_topo = d.get("sempre_no_topo", False)
                    self.modo_claro = d.get("modo_claro", False)
                    self.wallpaper = d.get("wallpaper", "Nenhum")
                    self.desfoque = NIVEIS_DESFOQUE[indice_desfoque(d.get("desfoque", 20))]
                    self.espessura_borda = NIVEIS_ESPESSURA[indice_espessura(d.get("espessura_borda", 1.0))]
                    self.pos_x = d.get("pos_x", None)
                    self.pos_y = d.get("pos_y", None)
            except: pass

    def salvar(self):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.__dict__, f)
        except: pass

    def aplicar_registro_windows(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_ALL_ACCESS)
            if self.iniciar_com_windows: winreg.SetValueEx(key, "WidgetAniversarios", 0, winreg.REG_SZ, f'"{get_app_path()}"')
            else: winreg.DeleteValue(key, "WidgetAniversarios")
            winreg.CloseKey(key)
        except: pass

config_app = Configuracoes()

def normalizar_cor_hex(valor):
    valor = (valor or "").strip().replace(" ", "")
    if valor.startswith("#"):
        valor = valor[1:]
    if len(valor) not in (3, 4, 6, 8):
        return "#ffffff"
    try:
        int(valor, 16)
    except ValueError:
        return "#ffffff"
    return "#" + valor

def aplicar_css_fonte_base(key):
    f = CONFIG_FONTES.get(key, {"fonte": "Segoe UI", "tamanho": 11, "peso": "normal"})
    peso = "bold" if f["peso"] == "bold" else "normal"
    return f"font-family: '{f['fonte']}', 'Segoe UI'; font-size: {f['tamanho']}px; font-weight: {peso}; background: transparent; border: none;"

class OutlineLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.borda_cor = None
        self.espessura = 0.0
        self.cor_texto = "#ffffff"

    def atualizar_estilo(self, css_base, cor_texto, borda_cor, espessura):
        self.setStyleSheet(css_base + f" color: {cor_texto};")
        self.cor_texto = cor_texto
        self.borda_cor = borda_cor
        try: self.espessura = float(espessura)
        except (TypeError, ValueError): self.espessura = 0.0
        self.update()

    def paintEvent(self, event):
        if not self.borda_cor or self.espessura <= 0:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = self.font(); painter.setFont(font)
        rect = self.rect(); text = self.text(); align = self.alignment()
        metrics = painter.fontMetrics(); text_width = metrics.horizontalAdvance(text)
        if align & Qt.AlignmentFlag.AlignHCenter: x = rect.x() + (rect.width() - text_width) / 2.0
        elif align & Qt.AlignmentFlag.AlignRight: x = rect.right() - text_width
        else: x = rect.x()
        y = rect.y() + (rect.height() + metrics.ascent() - metrics.descent()) / 2.0
        path = QPainterPath(); path.addText(x, y, font, text)
        pen = QPen(QColor(self.borda_cor)); pen.setWidthF(self.espessura); pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.strokePath(path, pen)
        painter.setPen(QColor(self.cor_texto))
        flags = int(align.value) if hasattr(align, 'value') else int(align)
        if self.wordWrap(): flags |= Qt.TextFlag.TextWordWrap.value
        painter.drawText(rect, flags, text)
        painter.end()

class BlurredBackgroundFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.bg_pixmap = None
        self.overlay_color = QColor(25, 25, 25, 175)
        self.border_color = QColor(255, 255, 255, 50)
        self.border_radius = 18

    def update_background(self, image_path, blur_radius, overlay_color, border_color, border_radius=18, modo_claro=False):
        self.border_color = QColor(*border_color) if isinstance(border_color, tuple) else QColor(border_color)
        self.border_radius = border_radius
        w, h = max(self.width(), 100), max(self.height(), 100)
        
        tem_wp = image_path and os.path.exists(image_path) and image_path != "Nenhum"

        if tem_wp:
            self.overlay_color = QColor(*overlay_color) if isinstance(overlay_color, tuple) else QColor(overlay_color)
            pix = QPixmap(image_path)
            if not pix.isNull():
                pix = pix.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                if blur_radius > 0:
                    scene = QGraphicsScene()
                    item = scene.addPixmap(pix)
                    blur = QGraphicsBlurEffect()
                    blur.setBlurRadius(blur_radius)
                    item.setGraphicsEffect(blur)
                    
                    img = QImage(pix.size(), QImage.Format.Format_ARGB32_Premultiplied)
                    img.fill(Qt.GlobalColor.transparent)
                    p = QPainter(img)
                    scene.render(p)
                    p.end()
                    self.bg_pixmap = QPixmap.fromImage(img)
                else:
                    self.bg_pixmap = pix
        else:
            self.bg_pixmap = None
            base_color = QColor(245, 245, 245) if modo_claro else QColor(25, 25, 25)
            alpha = 30 + int((blur_radius / 50.0) * 225)
            base_color.setAlpha(alpha)
            self.overlay_color = base_color

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), self.border_radius, self.border_radius)
        painter.setClipPath(path)
        
        if self.bg_pixmap:
            x, y = (self.width() - self.bg_pixmap.width()) // 2, (self.height() - self.bg_pixmap.height()) // 2
            painter.drawPixmap(x, y, self.bg_pixmap)
            
        painter.fillPath(path, self.overlay_color)
        pen = QPen(self.border_color)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawPath(path)

class JanelaConfiguracoes(QDialog):
    def __init__(self, parent_widget):
        super().__init__(parent_widget)
        self.parent_widget = parent_widget
        self.setWindowTitle("Configurações")
        self.setFixedSize(300, 480)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        
        layout = QVBoxLayout(self)
        
        self.check_tema = QCheckBox("Modo Claro")
        self.check_tema.setChecked(config_app.modo_claro)
        
        self.check_windows = QCheckBox("Iniciar junto com o Windows")
        self.check_windows.setChecked(config_app.iniciar_com_windows)
        
        self.check_plano = QCheckBox("Ao fechar, manter em 2º plano")
        self.check_plano.setChecked(config_app.segundo_plano)
        
        self.check_topo = QCheckBox("Sempre no topo")
        self.check_topo.setChecked(config_app.sempre_no_topo)

        # Layout horizontal para o rótulo e o botão de abrir a pasta no AppData
        layout_wp_top = QHBoxLayout()
        lbl_wp = QLabel("Papel de Parede:")
        self.btn_abrir_wp = QPushButton("📂 Abrir Pasta")
        self.btn_abrir_wp.setStyleSheet("padding: 3px 6px;")
        self.btn_abrir_wp.clicked.connect(lambda: os.startfile(PASTA_WALLPAPERS))
        
        layout_wp_top.addWidget(lbl_wp)
        layout_wp_top.addStretch()
        layout_wp_top.addWidget(self.btn_abrir_wp)

        self.combo_wp = QComboBox()
        self.combo_wp.addItem("Nenhum")
        
        for f in os.listdir(PASTA_WALLPAPERS):
            if f.lower().endswith(('.png', '.jpg', '.jpeg')):
                self.combo_wp.addItem(f)
                
        if config_app.wallpaper in [self.combo_wp.itemText(i) for i in range(self.combo_wp.count())]:
            self.combo_wp.setCurrentText(config_app.wallpaper)
            
        self.lbl_blur = QLabel()
        self.slider_blur = QSlider(Qt.Orientation.Horizontal)
        self.slider_blur.setRange(0, 5)
        self.slider_blur.setValue(indice_desfoque(config_app.desfoque))

        self.lbl_espessura = QLabel()
        self.slider_esp = QSlider(Qt.Orientation.Horizontal)
        self.slider_esp.setRange(0, 4)
        self.slider_esp.setValue(indice_espessura(config_app.espessura_borda))
        
        self.preview_frame = BlurredBackgroundFrame(self)
        self.preview_frame.setFixedSize(100, 100) 
        
        self.lbl_versao = QLabel(f"Versão atual: {APP_VERSION}")
        self.lbl_versao.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_update = QPushButton("Verificar Atualizações")
        self.btn_update.clicked.connect(lambda: self.parent_widget.verificar_atualizacoes(manual=True))
        
        layout.addWidget(self.check_tema)
        layout.addWidget(self.check_windows)
        layout.addWidget(self.check_plano)
        layout.addWidget(self.check_topo)
        layout.addSpacing(10)
        layout.addLayout(layout_wp_top)
        layout.addWidget(self.combo_wp)
        layout.addWidget(self.lbl_blur)
        layout.addWidget(self.slider_blur)
        layout.addWidget(self.lbl_espessura)
        layout.addWidget(self.slider_esp)
        layout.addSpacing(5)
        layout.addWidget(self.preview_frame, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
        layout.addWidget(self.lbl_versao)
        layout.addWidget(self.btn_update)
        
        self.check_tema.toggled.connect(self.atualizar_preview)
        self.combo_wp.currentTextChanged.connect(self.atualizar_preview)
        self.slider_blur.valueChanged.connect(self.atualizar_preview)
        self.slider_esp.valueChanged.connect(self.atualizar_preview)
        
        self.atualizar_preview()

    def atualizar_preview(self):
        claro = self.check_tema.isChecked()
        wp_nome = self.combo_wp.currentText()
        wp_path = os.path.join(self.pasta_wallpapers, wp_nome) if wp_nome != "Nenhum" else "Nenhum"
        tem_wp = wp_nome != "Nenhum" and os.path.exists(wp_path)
        blur_percent = NIVEIS_DESFOQUE[self.slider_blur.value()]
        espessura = NIVEIS_ESPESSURA[self.slider_esp.value()]
        self.lbl_blur.setText(f"Nível de Desfoque: {blur_percent}%")
        self.lbl_espessura.setText(f"Espessura da Borda: {espessura:g}px")
        self.slider_esp.setEnabled(tem_wp)
        if tem_wp:
            overlay = (255, 255, 255, 25) if claro else (0, 0, 0, 25)
            border = (0, 0, 0, 100) if claro else (255, 255, 255, 100)
        else:
            overlay = (245, 245, 245, 180) if claro else (25, 25, 25, 175)
            border = (255, 255, 255, 200) if claro else (255, 255, 255, 50)
        self.preview_frame.update_background(wp_path, raio_desfoque(blur_percent), overlay, border, 12, modo_claro=claro)

    def closeEvent(self, event):
        config_app.modo_claro = self.check_tema.isChecked()
        config_app.iniciar_com_windows = self.check_windows.isChecked()
        config_app.segundo_plano = self.check_plano.isChecked()
        config_app.sempre_no_topo = self.check_topo.isChecked()
        config_app.wallpaper = self.combo_wp.currentText()
        config_app.desfoque = NIVEIS_DESFOQUE[self.slider_blur.value()]
        config_app.espessura_borda = NIVEIS_ESPESSURA[self.slider_esp.value()]
        config_app.salvar()
        config_app.aplicar_registro_windows()

        self.parent_widget.aplicar_sempre_no_topo()
        self.parent_widget.aplicar_tema()

class ClickableMes(OutlineLabel):
    clicked = pyqtSignal(int)
    def __init__(self, text, index):
        super().__init__(text)
        self.index = index
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.index)

class JanelaCalendario(QWidget):
    def __init__(self, main_app):
        super().__init__()
        self.main_app = main_app
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(150)
        
        self.container = BlurredBackgroundFrame(self)
        self.container.setGeometry(0, 0, 150, 140)
        
        self.stacked = QStackedWidget(self.container)
        self.stacked.setGeometry(0, 0, 150, 140)
        
        self.page_grid = QWidget()
        self.layout_grid = QGridLayout(self.page_grid)
        self.layout_grid.setContentsMargins(10, 10, 10, 10)
        self.layout_grid.setSpacing(4)
        
        self.meses_nomes = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
        self.labels_meses = []
        
        for i in range(12):
            lbl = ClickableMes(self.meses_nomes[i], i + 1)
            lbl.clicked.connect(self.abrir_mes)
            self.layout_grid.addWidget(lbl, i // 3, i % 3)
            self.labels_meses.append(lbl)
            
        self.page_list = QWidget()
        layout_list = QVBoxLayout(self.page_list)
        layout_list.setContentsMargins(5, 5, 5, 5)
        
        top_list = QHBoxLayout()
        top_list.setContentsMargins(0, 0, 0, 0)
        self.lbl_titulo_mes = OutlineLabel("Mês")
        self.lbl_titulo_mes.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_list.addWidget(self.lbl_titulo_mes)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background: transparent; border: none;")
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent;")
        self.layout_nomes = QVBoxLayout(self.scroll_content)
        self.layout_nomes.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.scroll_content)

        for widget in (self.page_grid, self.page_list, self.lbl_titulo_mes, self.scroll, self.scroll.viewport(), self.scroll_content):
            widget.installEventFilter(self)
        for lbl in self.labels_meses:
            lbl.installEventFilter(self)
        
        layout_list.addLayout(top_list)
        layout_list.addWidget(self.scroll)
        
        self.stacked.addWidget(self.page_grid)
        self.stacked.addWidget(self.page_list)
        self.resize(150, 140)

        self.dados = []
        self.cor_texto = "#ffffff"
        self.borda_cor = None
        self.esp_borda = 0
        self.cores_aleatorias = ["#FF5C5C", "#5CFF5C", "#5C5CFF", "#FF5CFF", "#5CFFFF", "#FFFF5C", "#FFA65C", "#A65CFF", "#FF8C42", "#00B4D8"]

    def abrir_mes(self, mes_num):
        for i in reversed(range(self.layout_nomes.count())): 
            w = self.layout_nomes.itemAt(i).widget()
            if w: w.setParent(None)
            
        aniversariantes = []
        for item in self.dados:
            try:
                nome, data_str = item[0], item[1]
                cor_nome = item[2] if len(item) >= 3 else "#ffffff"
                d, m = map(int, data_str.split('/'))
                if m == mes_num:
                    aniversariantes.append((nome, d, normalizar_cor_hex(cor_nome)))
            except Exception:
                pass
            
        aniversariantes.sort(key=lambda x: x[1])
        self.lbl_titulo_mes.setText(f"{self.meses_nomes[mes_num-1]}")
        self.lbl_titulo_mes.atualizar_estilo(aplicar_css_fonte_base("cal_titulo"), self.cor_texto, self.borda_cor, self.esp_borda)
        
        if not aniversariantes:
            vazio = OutlineLabel("Sem aniversários")
            vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vazio.atualizar_estilo(aplicar_css_fonte_base("cal_lista"), self.cor_texto, self.borda_cor, self.esp_borda)
            self.layout_nomes.addWidget(vazio)
            vazio.installEventFilter(self)
        else:
            for nome, dia, cor in aniversariantes:
                lbl = OutlineLabel(f"{nome} - {dia}")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.atualizar_estilo(aplicar_css_fonte_base("cal_lista"), cor, self.borda_cor, self.esp_borda)
                self.layout_nomes.addWidget(lbl)
                lbl.installEventFilter(self)
                
        self.stacked.setCurrentIndex(1)
        self.main_app.reiniciar_timer_calendario()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self.main_app.reiniciar_timer_calendario()
            if self.stacked.currentIndex() == 1:
                self.stacked.setCurrentIndex(0)
                return True
        return super().eventFilter(obj, event)

    def atualizar_dados(self, dados, cor_texto, overlay_color, border_color, wp_path, blur, borda_cor=None, esp_borda=0, modo_claro=False):
        self.dados = dados
        self.cor_texto = cor_texto
        self.borda_cor = borda_cor
        self.esp_borda = esp_borda
        self.container.update_background(wp_path, blur, overlay_color, border_color, 12, modo_claro=modo_claro)
        
        meses_com_aniv = set()
        for item in dados:
            try: meses_com_aniv.add(int(item[1].split('/')[1]))
            except: pass
            
        css_base = aplicar_css_fonte_base("cal_meses")
        for i, lbl in enumerate(self.labels_meses):
            mes = i + 1
            lbl.atualizar_estilo(css_base, cor_texto, borda_cor, esp_borda)
            bg_css = f"QLabel {{ background: transparent; }} QLabel:hover {{ background-color: rgba(120,120,120,80); border-radius: 5px; }}"
            if mes in meses_com_aniv:
                bg_css = f"QLabel {{ background-color: rgba(120,120,120,50); border-radius: 5px; }} QLabel:hover {{ background-color: rgba(120,120,120,100); }}"
                lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            lbl.setStyleSheet(lbl.styleSheet() + bg_css)

class WidgetFrutigerAero(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(198, 176) 
        
        carregar_fontes()

        self.top_expanded = False
        self.top_extra = 26
        self.oldPos = None
        self.fixado = False
        self.atualizando = False
        self.pagina_atual = 0
        self.anim_group = None
        self.borda_cor = None
        self.esp_borda = 0
        
        self.timer_autoclose = QTimer(self)
        self.timer_autoclose.setSingleShot(True)
        self.timer_autoclose.timeout.connect(self.fechar_painel_topo)
        
        self.dados_planilha = []
        self.dados_jogo = [{"imagem": "", "link": ""}, {"imagem": "", "link": ""}]
        self.data_inicio_jogo = None
        self.data_fim_jogo = None
        self.timer_jogo = QTimer(self)
        self.timer_jogo.timeout.connect(self.atualizar_timer_jogo)
        self.timer_jogo.start(1000)

        self.aniversario_pulado = False
        self.timer_skip = QTimer(self)
        self.timer_skip.setSingleShot(True)
        self.timer_skip.timeout.connect(lambda: (setattr(self, 'aniversario_pulado', True), self.atualizar_interface_aniversario()))

        self.aniversario_animacao_pronta = False
        self.aniversario_animacao_executada = False
        self.animacao_parabens = None
        QTimer.singleShot(3000, self.liberar_animacao_aniversario)

        self.container = BlurredBackgroundFrame(self)
        self.container.setGeometry(24, 26, 150, 150)

        self.pages_container = QWidget(self)
        self.pages_container.setGeometry(24, 26, 150, 150)

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        for ext in ['.wav', '.mp3', '.ogg']:
            audio_path = external_resource_path("parabens" + ext)
            if os.path.exists(audio_path):
                self.player.setSource(QUrl.fromLocalFile(audio_path))
                break

        self.page_aniv = QWidget(self.pages_container)
        self.page_aniv.setGeometry(0, 0, 150, 150)
        self.nome_label = OutlineLabel("Carregando...", self.page_aniv)
        self.nome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.data_label = OutlineLabel("aguarde", self.page_aniv)
        self.data_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.linha_meio = QFrame(self.page_aniv)
        self.linha_meio.setStyleSheet("background-color: rgba(120, 120, 120, 80); border: none;")
        self.icone_label = QLabel(self.page_aniv)
        pix = QPixmap(resource_path("calendar.png"))
        if not pix.isNull(): self.icone_label.setPixmap(pix.scaled(15, 15, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else: self.icone_label.setText("📅")
        self.icone_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icone_label.setFixedSize(20, 20)
        self.faltam_label = OutlineLabel("Faltam", self.page_aniv)
        self.faltam_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dias_label = OutlineLabel("...", self.page_aniv)
        self.dias_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.page_jogo = QWidget(self.pages_container)
        self.page_jogo.setGeometry(0, 0, 150, 150)
        self.page_jogo.hide()

        self.timer_jogo_label = OutlineLabel("", self.page_jogo)
        self.timer_jogo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timer_jogo_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.timer_jogo_label.setGeometry(5, 0, 140, 70)
        self.timer_jogo_label.raise_()

        self.img_label_jogo1 = OutlineLabel("...", self.page_jogo)
        self.img_label_jogo1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label_jogo1.setGeometry(0, 28, 75, 122)
        self.btn_clique_jogo1 = QPushButton(self.page_jogo)
        self.btn_clique_jogo1.setGeometry(5, 50, 65, 65)
        self.btn_clique_jogo1.setStyleSheet("background: transparent; border: none;")
        self.btn_clique_jogo1.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clique_jogo1.clicked.connect(lambda: self.abrir_link_jogo(0))
        self.img_label_jogo2 = OutlineLabel("...", self.page_jogo)
        self.img_label_jogo2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label_jogo2.setGeometry(75, 28, 75, 122)
        self.btn_clique_jogo2 = QPushButton(self.page_jogo)
        self.btn_clique_jogo2.setGeometry(75 + 5, 50, 65, 65)
        self.btn_clique_jogo2.setStyleSheet("background: transparent; border: none;")
        self.btn_clique_jogo2.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clique_jogo2.clicked.connect(lambda: self.abrir_link_jogo(1))

        self.top_panel = QWidget(self)
        self.top_panel.setGeometry(24, 0, 150, self.top_extra)
        top_layout = QHBoxLayout(self.top_panel)
        top_layout.setContentsMargins(10, 4, 10, 2)
        top_layout.setSpacing(3)
        estilo_botoes = "QPushButton { background-color: rgba(255, 255, 255, 40); border: none; border-radius: 5px; font-size: 10px; } QPushButton:hover { background-color: rgba(255, 255, 255, 80); }"

        self.btn_refresh = QPushButton("🔄", self.top_panel)
        self.btn_refresh.setFixedSize(20, 20)
        self.btn_refresh.setStyleSheet(estilo_botoes)
        self.btn_refresh.clicked.connect(self.baixar_todos_dados)
        self.btn_lista = QPushButton("📅", self.top_panel)
        self.btn_lista.setFixedSize(20, 20)
        self.btn_lista.setStyleSheet(estilo_botoes)
        self.btn_lista.clicked.connect(self.toggle_calendario)
        self.btn_config = QPushButton("⚙️", self.top_panel)
        self.btn_config.setFixedSize(20, 20)
        self.btn_config.setStyleSheet(estilo_botoes)
        self.btn_config.clicked.connect(lambda: JanelaConfiguracoes(self).exec())
        self.btn_pin = QPushButton("🔓", self.top_panel)
        self.btn_pin.setFixedSize(20, 20)
        self.btn_pin.setStyleSheet(estilo_botoes)
        self.btn_pin.clicked.connect(self.alternar_fixacao)
        self.btn_close = QPushButton("❌", self.top_panel)
        self.btn_close.setFixedSize(20, 20)
        self.btn_close.setStyleSheet(estilo_botoes)
        self.btn_close.clicked.connect(self.fechar_app)

        for b in [self.btn_refresh, self.btn_lista, self.btn_config]: top_layout.addWidget(b)
        top_layout.addStretch()
        for b in [self.btn_pin, self.btn_close]: top_layout.addWidget(b)
        
        self.linha_top = QFrame(self)
        self.linha_top.setGeometry(24, self.top_extra - 1, 150, 1)
        self.linha_top.setStyleSheet("background-color: rgba(120, 120, 120, 80); border: none;")
        self.top_panel.hide()
        self.linha_top.hide()

        self.btn_nav_esq = QPushButton("<", self)
        self.btn_nav_esq.setGeometry(0, 89, 24, 24)
        self.btn_nav_esq.clicked.connect(lambda: self.mudar_pagina("esq"))
        self.btn_nav_esq.hide()
        self.btn_nav_dir = QPushButton(">", self)
        self.btn_nav_dir.setGeometry(174, 89, 24, 24)
        self.btn_nav_dir.clicked.connect(lambda: self.mudar_pagina("dir"))
        self.btn_nav_dir.hide()

        self.timer_hover = QTimer(self)
        self.timer_hover.timeout.connect(self.verificar_hover_bordas)
        self.timer_hover.start(100)

        self.janela_calendario = JanelaCalendario(self)
        self.calendario_aberto = False

        self.timer_calendario_autoclose = QTimer(self)
        self.timer_calendario_autoclose.setSingleShot(True)
        self.timer_calendario_autoclose.timeout.connect(self.fechar_calendario_por_inatividade)
        
        if config_app.pos_x is not None and config_app.pos_y is not None: self.move(config_app.pos_x, config_app.pos_y)
        else:
            s = QApplication.primaryScreen().geometry()
            self.move((s.width() - self.width()) // 2, (s.height() - self.height()) // 2)

        self.aplicar_sempre_no_topo()
        self.aplicar_tema()
        self.configurar_bandeja(pix)
        
        self.pulse_timer = QTimer(self)
        self.pulse_timer.timeout.connect(self.animar_emoji)
        self.pulse_size = 18
        self.pulse_dir = 1

        self.timer_internet = QTimer(self)
        self.timer_internet.timeout.connect(self.baixar_todos_dados)
        self.timer_internet.start(60 * 60 * 1000)
        self.timer_tela = QTimer(self)
        self.timer_tela.timeout.connect(self.atualizar_interface_aniversario)
        self.timer_tela.start(60 * 1000)

        QTimer.singleShot(100, self.baixar_todos_dados)
        self.posicionar_elementos()

    def aplicar_sempre_no_topo(self):
        flags = self.windowFlags()
        if config_app.sempre_no_topo: flags |= Qt.WindowType.WindowStaysOnTopHint
        else: flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    def aplicar_tema(self):
        wp_path = "Nenhum"
        if config_app.wallpaper != "Nenhum":
            caminho_wp = os.path.join(PASTA_WALLPAPERS, config_app.wallpaper)
            if os.path.exists(caminho_wp):
                wp_path = caminho_wp

        tem_wp = (wp_path != "Nenhum")
        self.esp_borda = float(config_app.espessura_borda) if tem_wp else 0.0

        if tem_wp:
            if config_app.modo_claro:
                self.cor_texto = "#000000"
                self.borda_cor = "#ffffff"
                overlay = (255, 255, 255, 25)
                border = (0, 0, 0, 100)
            else:
                self.cor_texto = "#ffffff"
                self.borda_cor = "#000000"
                overlay = (0, 0, 0, 25)
                border = (255, 255, 255, 100)
        else:
            self.borda_cor = None
            if config_app.modo_claro:
                self.cor_texto = "#111111"
                overlay = (245, 245, 245, 180)
                border = (255, 255, 255, 200)
            else:
                self.cor_texto = "#ffffff"
                overlay = (25, 25, 25, 175)
                border = (255, 255, 255, 50)
                
        self.container.update_background(wp_path, raio_desfoque(config_app.desfoque), overlay, border, modo_claro=config_app.modo_claro)
        
        bg_btn, bg_hover = ("rgba(240, 240, 240, 220)", "rgba(255, 255, 255, 255)") if config_app.modo_claro else ("rgba(20, 20, 20, 200)", "rgba(0, 0, 0, 230)")
        estilo = f"QPushButton {{ background-color: {bg_btn}; border-radius: 12px; color: {self.cor_texto}; font-weight: bold; border: none; }} QPushButton:hover {{ background-color: {bg_hover}; }}"
        self.btn_nav_esq.setStyleSheet(estilo)
        self.btn_nav_dir.setStyleSheet(estilo)
        
        self.atualizar_interface_aniversario()
        
        if self.img_label_jogo1.text() == "...":
            self.img_label_jogo1.atualizar_estilo(aplicar_css_fonte_base("nome"), self.cor_texto, self.borda_cor, self.esp_borda)
        if self.img_label_jogo2.text() == "...":
            self.img_label_jogo2.atualizar_estilo(aplicar_css_fonte_base("nome"), self.cor_texto, self.borda_cor, self.esp_borda)
        self.atualizar_timer_jogo()
        
        if self.calendario_aberto:
            self.janela_calendario.atualizar_dados(
                self.dados_planilha, self.cor_texto, overlay, border, wp_path, 
                raio_desfoque(config_app.desfoque), borda_cor=self.borda_cor, esp_borda=self.esp_borda, modo_claro=config_app.modo_claro
            )

    def verificar_atualizacoes(self, manual=False):
        if not getattr(sys, "frozen", False):
            if manual:
                QMessageBox.information(self, "Atualizações", f"Versão atual: {APP_VERSION}\n\nO atualizador automático funciona somente no .exe compilado.")
            return
            
        try:
            req = urllib.request.Request(URL_UPDATE_CHECK, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resposta:
                dados = json.loads(resposta.read().decode("utf-8"))
                
            versao_remota = str(dados.get("version", "")).strip()
            url_download = str(dados.get("download_url", dados.get("url", URL_DOWNLOAD_EXE))).strip()
            
            if not versao_remota or not url_download:
                raise ValueError("JSON de versão inválido no GitHub.")
                
            if versao_tuple(versao_remota) <= versao_tuple(APP_VERSION):
                if manual:
                    QMessageBox.information(self, "Atualizações", f"Você já está usando a versão mais recente.\n\nVersão atual: {APP_VERSION}")
                return
                
            resposta_msg = QMessageBox.question(self, "Atualização disponível", f"Uma nova versão está disponível!\n\nAtual: {APP_VERSION}\nNova: {versao_remota}\n\nDeseja baixar e instalar agora?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes)
            
            if resposta_msg != QMessageBox.StandardButton.Yes:
                return
                
            # Mostra cursor de carregamento pois o download congela a tela por uns segundos
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            
            temp_dir = tempfile.gettempdir()
            novo_exe = os.path.join(temp_dir, f"MussasWidget_new_{os.getpid()}.exe")
            req_download = urllib.request.Request(url_download, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            
            with urllib.request.urlopen(req_download, timeout=120) as resposta_download:
                with open(novo_exe, "wb") as arquivo:
                    arquivo.write(resposta_download.read())
                    
            if not os.path.exists(novo_exe) or os.path.getsize(novo_exe) < 100000:
                try: os.remove(novo_exe)
                except: pass
                raise RuntimeError("O arquivo baixado parece estar incompleto ou corrompido.")
                
            QApplication.restoreOverrideCursor()
            
            # Confirmação visual para você saber que o download realmente funcionou
            QMessageBox.information(self, "Download Concluído", "A atualização foi baixada com sucesso!\n\nO aplicativo será reiniciado agora.")
            
            executar_atualizacao_bat(novo_exe)
            
            # Fecha IMEDIATAMENTE (sem esperar a fila de eventos do PyQt) liberando o processo pro BAT
            os._exit(0)
            
        except Exception as e:
            QApplication.restoreOverrideCursor()
            if manual:
                QMessageBox.critical(self, "Erro ao atualizar", "Não foi possível verificar ou instalar a atualização.\n\nDetalhes: " + str(e))

    def fechar_painel_topo(self):
        if self.top_expanded: self.toggle_top_panel()

    def verificar_hover_bordas(self):
        pos = self.mapFromGlobal(QCursor.pos())
        y_min = 26 if self.top_expanded else 26
        if 0 <= pos.x() <= 24 and y_min <= pos.y() <= self.height(): self.btn_nav_esq.show()
        else: self.btn_nav_esq.hide()
        if 174 <= pos.x() <= 198 and y_min <= pos.y() <= self.height(): self.btn_nav_dir.show()
        else: self.btn_nav_dir.hide()
        
        if self.top_expanded and 24 <= pos.x() <= 174 and 0 <= pos.y() <= self.top_extra:
            self.timer_autoclose.start(10000)

    def mudar_pagina(self, direcao):
        if self.anim_group and self.anim_group.state() == QAbstractAnimation.State.Running: return
        page_out = self.page_aniv if self.pagina_atual == 0 else self.page_jogo
        page_in = self.page_jogo if self.pagina_atual == 0 else self.page_aniv
        self.pagina_atual = 1 if self.pagina_atual == 0 else 0
        
        start_x_in, end_x_out = (150, -150) if direcao == "dir" else (-150, 150)
        page_in.setGeometry(start_x_in, 0, 150, 150)
        page_in.show()

        self.anim_out = QPropertyAnimation(page_out, b"pos")
        self.anim_out.setDuration(250)
        self.anim_out.setStartValue(QPoint(0, 0))
        self.anim_out.setEndValue(QPoint(end_x_out, 0))
        self.anim_out.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        self.anim_in = QPropertyAnimation(page_in, b"pos")
        self.anim_in.setDuration(250)
        self.anim_in.setStartValue(QPoint(start_x_in, 0))
        self.anim_in.setEndValue(QPoint(0, 0))
        self.anim_in.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self.anim_group = QParallelAnimationGroup()
        self.anim_group.addAnimation(self.anim_out)
        self.anim_group.addAnimation(self.anim_in)
        self.anim_group.finished.connect(page_out.hide)
        self.anim_group.start()

    def posicionar_elementos(self):
        if not self.anim_group or self.anim_group.state() != QAbstractAnimation.State.Running:
            if self.pagina_atual == 0:
                self.page_aniv.setGeometry(0, 0, 150, 150)
                self.page_jogo.setGeometry(150, 0, 150, 150)
            else:
                self.page_jogo.setGeometry(0, 0, 150, 150)
                self.page_aniv.setGeometry(-150, 0, 150, 150)

        self.nome_label.setGeometry(10, 16, 130, 21)
        self.data_label.setGeometry(10, 36, 130, 16)
        self.linha_meio.setGeometry(0, 72, 150, 1)
        self.icone_label.move((150 - 20) // 2, 62)
        self.icone_label.raise_()
        self.faltam_label.setGeometry(10, 95, 130, 16)
        self.dias_label.setGeometry(10, 105, 130, 28)
        
        if self.calendario_aberto:
            self.janela_calendario.move(self.x() + 24, self.y() + self.height() + 5)

    def mousePressEvent(self, event):
        pos_y = event.position().y()
        if 26 <= pos_y < 50:
            self.toggle_top_panel()
            return
        if event.button() == Qt.MouseButton.LeftButton and not self.fixado:
            self.oldPos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if not self.fixado and self.oldPos is not None:
            delta = event.globalPosition().toPoint() - self.oldPos
            self.move(self.pos() + delta)
            self.oldPos = event.globalPosition().toPoint()
            if self.calendario_aberto: self.janela_calendario.move(self.x() + 24, self.y() + self.height() + 5)

    def mouseReleaseEvent(self, event):
        self.oldPos = None
        config_app.pos_x = self.x()
        config_app.pos_y = self.y()
        config_app.salvar()

    def closeEvent(self, event):
        config_app.pos_x = self.x()
        config_app.pos_y = self.y()
        config_app.salvar()
        if config_app.segundo_plano:
            event.ignore()
            self.hide()
            if self.calendario_aberto: self.janela_calendario.hide()
        else:
            event.accept()
            QApplication.quit()

    def toggle_top_panel(self):
        self.top_expanded = not self.top_expanded
        if self.top_expanded:
            self.container.setGeometry(24, 0, 150, 176)
            self.top_panel.show()
            self.linha_top.show()
            self.timer_autoclose.start(10000)
        else:
            self.container.setGeometry(24, 26, 150, 150)
            self.top_panel.hide()
            self.linha_top.hide()
            self.timer_autoclose.stop()

    def baixar_todos_dados(self):
        # Evita iniciar uma nova thread se já houver uma ativa
        if hasattr(self, 'worker') and self.worker.isRunning():
            return 
        
        self.worker = WorkerDownload()
        self.worker.resultado.connect(self.processar_dados_baixados)
        self.worker.start()

    def processar_dados_baixados(self, plan, jogo, data_ini, data_fim, img1, img2):
        self.dados_planilha = plan
        self.dados_jogo = jogo
        self.data_inicio_jogo = data_ini
        self.data_fim_jogo = data_fim

        self.carregar_imagem_bytes(img1, self.img_label_jogo1)
        self.carregar_imagem_bytes(img2, self.img_label_jogo2)

        self.atualizar_interface_aniversario()
        
        if self.calendario_aberto:
            self.aplicar_tema()

    def carregar_imagem_bytes(self, dados_bytes, label):
        if not dados_bytes:
            label.clear()
            label.setText("...")
            label.atualizar_estilo(aplicar_css_fonte_base("nome"), self.cor_texto, self.borda_cor, self.esp_borda)
            return
        
        pix = QPixmap()
        pix.loadFromData(dados_bytes)
        label.setPixmap(pix.scaled(65, 65, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))        

    def parse_data_jogo(self, valor):
        if not valor:
            return None
        valor = valor.strip()
        formatos = (
            "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
            "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
            "%d/%m/%y %H:%M:%S", "%d/%m/%y %H:%M", "%d/%m/%y"
        )
        for formato in formatos:
            try:
                return datetime.strptime(valor, formato)
            except ValueError:
                pass
        try:
            return datetime.fromisoformat(valor.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return None

    def atualizar_timer_jogo(self):
        if self.data_fim_jogo is None:
            self.timer_jogo_label.setText("")
            return

        agora = datetime.now()
        if self.data_inicio_jogo and agora < self.data_inicio_jogo:
            restante = self.data_inicio_jogo - agora
            texto = "Começa em " + self.formatar_tempo_jogo(restante)
        else:
            restante = self.data_fim_jogo - agora
            if restante.total_seconds() <= 0:
                texto = "Encerrado"
            else:
                texto = self.formatar_tempo_jogo(restante)

        self.timer_jogo_label.setText(texto)
        self.timer_jogo_label.atualizar_estilo(
            aplicar_css_fonte_base("cal_titulo"),
            self.cor_texto, self.borda_cor, self.esp_borda
        )

    def formatar_tempo_jogo(self, restante):
        total = max(0, int(restante.total_seconds()))
        dias, resto = divmod(total, 86400)
        horas, resto = divmod(resto, 3600)
        minutos, segundos = divmod(resto, 60)
        if dias:
            return f"{dias}d {horas:02d}:{minutos:02d}:{segundos:02d}"
        return f"{horas:02d}:{minutos:02d}:{segundos:02d}"

    def carregar_imagem_jogo(self):
        def setar_imagem(url, label):
            if not url:
                label.clear()
                label.setText("...")
                label.atualizar_estilo(aplicar_css_fonte_base("nome"), self.cor_texto, self.borda_cor, self.esp_borda)
                return
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                data = urllib.request.urlopen(req).read()
                pix = QPixmap()
                pix.loadFromData(data)
                label.setPixmap(pix.scaled(65, 65, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            except:
                label.clear()
                label.setText("...")
                label.atualizar_estilo(aplicar_css_fonte_base("nome"), self.cor_texto, self.borda_cor, self.esp_borda)
                
        setar_imagem(self.dados_jogo[0].get("imagem", ""), self.img_label_jogo1)
        setar_imagem(self.dados_jogo[1].get("imagem", ""), self.img_label_jogo2)

    def abrir_link_jogo(self, setor_idx):
        link = self.dados_jogo[setor_idx].get("link", "")
        if link: webbrowser.open(link)

    def liberar_animacao_aniversario(self):
        self.aniversario_animacao_pronta = True
        self.atualizar_interface_aniversario()

    def iniciar_animacao_parabens(self):
        if self.aniversario_animacao_executada:
            return
        self.aniversario_animacao_executada = True
        pos_nome_final = QPoint(10, 16)
        pos_data_final = QPoint(10, 36)
        pos_nome_inicial = QPoint(10, 66)
        pos_data_inicial = QPoint(10, 86)
        self.nome_label.move(pos_nome_inicial)
        self.data_label.move(pos_data_inicial)
        self.nome_label.show()
        self.data_label.show()
        anim_nome = QPropertyAnimation(self.nome_label, b"pos", self)
        anim_nome.setDuration(700)
        anim_nome.setStartValue(pos_nome_inicial)
        anim_nome.setEndValue(pos_nome_final)
        anim_nome.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim_data = QPropertyAnimation(self.data_label, b"pos", self)
        anim_data.setDuration(700)
        anim_data.setStartValue(pos_data_inicial)
        anim_data.setEndValue(pos_data_final)
        anim_data.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animacao_parabens = QParallelAnimationGroup(self)
        self.animacao_parabens.addAnimation(anim_nome)
        self.animacao_parabens.addAnimation(anim_data)
        self.animacao_parabens.start()

    def atualizar_interface_aniversario(self):
        if not self.dados_planilha: return
        hoje = date.today()
        proximo_aniv, menor_diferenca = None, 99999
        for item in self.dados_planilha:
            try:
                nome, data_str = item[0], item[1]
                cor_nome = normalizar_cor_hex(item[2] if len(item) >= 3 else "")
                d, m = map(int, data_str.split('/'))
                aniv = date(hoje.year, m, d)
                if aniv < hoje: aniv = date(hoje.year + 1, m, d)
                dias = (aniv - hoje).days
                if dias == 0 and self.aniversario_pulado: continue
                if dias < menor_diferenca: menor_diferenca, proximo_aniv = dias, (nome, d, m, dias, cor_nome)
            except: pass

        if proximo_aniv:
            nome, dia, mes, dias, cor_nome = proximo_aniv
            meses = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

            if dias == 0:
                self.pulse_timer.start(50)
                self.nome_label.setText("Parabéns")
                self.nome_label.atualizar_estilo(aplicar_css_fonte_base("parabens_titulo"), self.cor_texto, self.borda_cor, self.esp_borda)
                self.data_label.setText(f"{nome}!")
                self.data_label.atualizar_estilo(aplicar_css_fonte_base("parabens_nome"), "#d90f0f", self.borda_cor, self.esp_borda)
                self.faltam_label.setText("")
                self.dias_label.setText("🤤")
                if self.aniversario_animacao_pronta and not self.aniversario_animacao_executada:
                    self.iniciar_animacao_parabens()
                elif not self.aniversario_animacao_pronta:
                    self.nome_label.hide()
                    self.data_label.hide()
                elif self.animacao_parabens is None or self.animacao_parabens.state() != QAbstractAnimation.State.Running:
                    self.nome_label.move(10, 16)
                    self.data_label.move(10, 36)
                    self.nome_label.show()
                    self.data_label.show()
                if not self.ja_tocou_hoje():
                    self.player.play()
                    self.marcar_como_tocado()
                if not self.aniversario_pulado and not self.timer_skip.isActive():
                    self.timer_skip.start(20000)
            else:
                self.pulse_timer.stop()
                if self.animacao_parabens and self.animacao_parabens.state() == QAbstractAnimation.State.Running:
                    self.animacao_parabens.stop()
                self.nome_label.move(10, 16)
                self.data_label.move(10, 36)
                self.nome_label.show()
                self.data_label.show()
                self.nome_label.setText(nome)
                self.nome_label.atualizar_estilo(aplicar_css_fonte_base("nome"), cor_nome, self.borda_cor, self.esp_borda)
                self.data_label.setText(f"{dia} de {meses[mes]}")
                self.data_label.atualizar_estilo(aplicar_css_fonte_base("data"), self.cor_texto, self.borda_cor, self.esp_borda)
                self.faltam_label.setText("Faltam")
                self.faltam_label.atualizar_estilo(aplicar_css_fonte_base("faltam"), self.cor_texto, self.borda_cor, self.esp_borda)
                self.dias_label.setText("1 dia" if dias == 1 else f"{dias} dias")
                self.dias_label.atualizar_estilo(aplicar_css_fonte_base("dias"), self.cor_texto, self.borda_cor, self.esp_borda)

    def ja_tocou_hoje(self):
        try:
            with open(STATE_FILE, "r") as f: return f.read().strip() == date.today().isoformat()
        except: return False

    def marcar_como_tocado(self):
        try:
            with open(STATE_FILE, "w") as f: f.write(date.today().isoformat())
        except: pass

    def animar_emoji(self):
        self.pulse_size += self.pulse_dir
        if self.pulse_size >= 24: self.pulse_dir = -1
        elif self.pulse_size <= 14: self.pulse_dir = 1
        css = aplicar_css_fonte_base("dias")
        css = css.replace(f"font-size: {CONFIG_FONTES['dias']['tamanho']}px", f"font-size: {self.pulse_size}px")
        self.dias_label.atualizar_estilo(css, self.cor_texto, self.borda_cor, self.esp_borda)

    def toggle_calendario(self):
        self.calendario_aberto = not self.calendario_aberto
        if self.calendario_aberto:
            self.aplicar_tema()
            self.janela_calendario.move(self.x() + 24, self.y() + self.height() + 5)
            self.janela_calendario.stacked.setCurrentIndex(0)
            self.janela_calendario.show()
            self.reiniciar_timer_calendario()
        else:
            self.janela_calendario.hide()
            self.timer_calendario_autoclose.stop()

    def reiniciar_timer_calendario(self):
        if self.calendario_aberto and self.janela_calendario.isVisible():
            self.timer_calendario_autoclose.start(10000)

    def fechar_calendario_por_inatividade(self):
        self.calendario_aberto = False
        self.janela_calendario.hide()

    def alternar_fixacao(self):
        self.fixado = not self.fixado
        self.btn_pin.setText("📌" if self.fixado else "🔓")

    def fechar_app(self):
        self.timer_calendario_autoclose.stop()
        if config_app.segundo_plano:
            self.hide()
            if self.calendario_aberto:
                self.janela_calendario.hide()
        else: QApplication.quit()

    def configurar_bandeja(self, pix):
        self.tray_icon = QSystemTrayIcon(self)
        tray_pix = QIcon(external_resource_path("calendar.png"))
        if tray_pix.isNull():
            tray_pix = QIcon(external_resource_path("icone.ico"))
        self.tray_icon.setIcon(tray_pix)
        tray_menu = QMenu()
        acao_abrir = QAction("Abrir", self)
        acao_abrir.triggered.connect(lambda: (self.show(), self.activateWindow()))
        acao_sair = QAction("Sair", self)
        acao_sair.triggered.connect(QApplication.quit)
        tray_menu.addAction(acao_abrir)
        tray_menu.addAction(acao_sair)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.setToolTip("MussasWidget")
        self.tray_icon.show()

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = QApplication(sys.argv)
    shared_memory = QSharedMemory("MussasWidget_SingleInstance")
    if shared_memory.attach():
        sys.exit(0)
    shared_memory.create(1)
    QApplication.setQuitOnLastWindowClosed(False) 
    widget = WidgetFrutigerAero()
    widget.show()
    sys.exit(app.exec())