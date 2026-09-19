import sys
import os
import signal
import urllib.request
import csv
import codecs
import json
import winreg
import webbrowser
from datetime import date

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QFrame, QPushButton, 
    QHBoxLayout, QVBoxLayout, QDialog, QCheckBox, QSystemTrayIcon, QMenu
)
from PyQt6.QtCore import (
    Qt, QTimer, QUrl, QPoint, 
    QPropertyAnimation, QParallelAnimationGroup, QEasingCurve, QAbstractAnimation
)
from PyQt6.QtGui import QFontDatabase, QCursor, QPixmap, QIcon, QAction
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

# ==========================================
# LINKS DAS PLANILHAS (CSV)
# ==========================================
URL_CSV_ANIVERSARIOS = "https://docs.google.com/spreadsheets/d/1W1cX9dCAFnLPjDImSB6rjSSC0GhvOX0rp_HiaHeHAGI/export?format=csv&gid=0"
URL_CSV_JOGO = "https://docs.google.com/spreadsheets/d/1W1cX9dCAFnLPjDImSB6rjSSC0GhvOX0rp_HiaHeHAGI/export?format=csv&gid=36262169"

# ==========================================
# CONFIGURAÇÕES DE FONTES FACILITADA
# ==========================================
CONFIG_FONTES = {
    "nome": {"fonte": "Frutiger", "tamanho": 16, "peso": "bold"},
    "data": {"fonte": "Frutiger", "tamanho": 12, "peso": "normal"},
    "faltam": {"fonte": "Frutiger", "tamanho": 12, "peso": "normal"},
    "dias": {"fonte": "Frutiger", "tamanho": 16, "peso": "bold"},
    "parabens_titulo": {"fonte": "Frutiger", "tamanho": 14, "peso": "normal"},
    "parabens_nome": {"fonte": "Frutiger", "tamanho": 15, "peso": "bold"},
    "lista": {"fonte": "Segoe UI", "tamanho": 10, "peso": "normal"}
}

# ==========================================
# SALVAMENTO DE ESTADO E ARQUIVOS
# ==========================================
STATE_FILE = "parabens_played.txt"
CONFIG_FILE = "config.json"

def get_app_path():
    if getattr(sys, 'frozen', False):
        return sys.executable
    return os.path.abspath(sys.argv[0])

class Configuracoes:
    def __init__(self):
        self.iniciar_com_windows = False
        self.segundo_plano = False
        self.sempre_no_topo = False
        self.modo_claro = False
        self.pos_x = None
        self.pos_y = None
        self.carregar()

    def carregar(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    dados = json.load(f)
                    self.iniciar_com_windows = dados.get("iniciar_com_windows", False)
                    self.segundo_plano = dados.get("segundo_plano", False)
                    self.sempre_no_topo = dados.get("sempre_no_topo", False)
                    self.modo_claro = dados.get("modo_claro", False)
                    self.pos_x = dados.get("pos_x", None)
                    self.pos_y = dados.get("pos_y", None)
            except Exception:
                pass

    def salvar(self):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump({
                    "iniciar_com_windows": self.iniciar_com_windows,
                    "segundo_plano": self.segundo_plano,
                    "sempre_no_topo": self.sempre_no_topo,
                    "modo_claro": self.modo_claro,
                    "pos_x": self.pos_x,
                    "pos_y": self.pos_y
                }, f)
        except Exception:
            pass

    def aplicar_registro_windows(self):
        caminho_registro = r"Software\Microsoft\Windows\CurrentVersion\Run"
        nome_app = "WidgetAniversarios"
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, caminho_registro, 0, winreg.KEY_ALL_ACCESS)
            if self.iniciar_com_windows:
                winreg.SetValueEx(key, nome_app, 0, winreg.REG_SZ, f'"{get_app_path()}"')
            else:
                try: winreg.DeleteValue(key, nome_app)
                except FileNotFoundError: pass
            winreg.CloseKey(key)
        except Exception as e:
            print("Erro registro:", e)

config_app = Configuracoes()

def aplicar_css_fonte(key, cor):
    f = CONFIG_FONTES[key]
    peso_str = "bold" if f["peso"] == "bold" else "normal"
    return f"font-family: '{f['fonte']}', 'Segoe UI'; font-size: {f['tamanho']}px; font-weight: {peso_str}; color: {cor}; background: transparent; border: none;"

# ==========================================
# JANELA DE CONFIGURAÇÕES
# ==========================================
class JanelaConfiguracoes(QDialog):
    def __init__(self, parent_widget=None):
        super().__init__(parent_widget)
        self.parent_widget = parent_widget
        self.setWindowTitle("Configurações")
        self.setFixedSize(250, 170)
        
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        
        layout = QVBoxLayout(self)
        
        self.check_tema = QCheckBox("Modo Claro")
        self.check_tema.setChecked(config_app.modo_claro)
        self.check_tema.toggled.connect(self.salvar_configs)

        self.check_windows = QCheckBox("Iniciar junto com o Windows")
        self.check_windows.setChecked(config_app.iniciar_com_windows)
        self.check_windows.toggled.connect(self.salvar_configs)
        
        self.check_plano = QCheckBox("Ao fechar, manter em 2º plano")
        self.check_plano.setChecked(config_app.segundo_plano)
        self.check_plano.toggled.connect(self.salvar_configs)
        
        self.check_topo = QCheckBox("Sempre no topo")
        self.check_topo.setChecked(config_app.sempre_no_topo)
        self.check_topo.toggled.connect(self.salvar_configs)
        
        layout.addWidget(self.check_tema)
        layout.addWidget(self.check_windows)
        layout.addWidget(self.check_plano)
        layout.addWidget(self.check_topo)
        
    def salvar_configs(self):
        config_app.modo_claro = self.check_tema.isChecked()
        config_app.iniciar_com_windows = self.check_windows.isChecked()
        config_app.segundo_plano = self.check_plano.isChecked()
        config_app.sempre_no_topo = self.check_topo.isChecked()
        config_app.salvar()
        config_app.aplicar_registro_windows()
        if self.parent_widget:
            self.parent_widget.aplicar_sempre_no_topo()
            self.parent_widget.aplicar_tema()
            
# ==========================================
# JANELA DA LISTA
# ==========================================
class JanelaLista(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(0.95)
        self.setFixedWidth(150)
        
        self.container = QFrame(self)
        self.container.setStyleSheet("""
            QFrame { background-color: rgba(240, 240, 240, 190); border-radius: 10px; border: 1px solid rgba(255, 255, 255, 150); }
        """)
        
        self.layout_lista = QVBoxLayout(self.container)
        self.layout_lista.setContentsMargins(10, 10, 10, 10)
        self.layout_lista.setSpacing(3)
        
    def atualizar_dados(self, dados, cor_texto):
        bg_lista = "rgba(40, 40, 40, 190)" if cor_texto == "#ffffff" else "rgba(240, 240, 240, 190)"
        border_lista = "rgba(255, 255, 255, 50)" if cor_texto == "#ffffff" else "rgba(255, 255, 255, 150)"
        self.container.setStyleSheet(f"""
            QFrame {{ background-color: {bg_lista}; border-radius: 10px; border: 1px solid {border_lista}; }}
        """)

        while self.layout_lista.count():
            item = self.layout_lista.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        meses = ["", "Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
        for nome, data_str in dados:
            try:
                partes = data_str.split('/')
                lbl = QLabel(f"• {nome}: {int(partes[0])} de {meses[int(partes[1])]}")
                lbl.setStyleSheet(aplicar_css_fonte("lista", cor_texto))
                self.layout_lista.addWidget(lbl)
            except: pass
                
        num_itens = max(len(dados), 1)
        nova_altura = (num_itens * 18) + 20
        self.resize(150, nova_altura)
        self.container.resize(150, nova_altura)

# ==========================================
# WIDGET PRINCIPAL
# ==========================================
class WidgetFrutigerAero(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.resize(198, 150) 
        
        QFontDatabase.addApplicationFont("frutiger.ttf")

        # Variáveis de Estado
        self.cor_texto = "#ffffff"
        self.top_expanded = False
        self.top_extra = 26
        self.oldPos = None
        self.fixado = False
        self.pagina_atual = 0  # 0: Aniversários, 1: Jogo
        self.anim_group = None
        
        # Timer para recuar a bandeja após 10 segundos
        self.timer_autoclose = QTimer(self)
        self.timer_autoclose.setSingleShot(True)
        self.timer_autoclose.timeout.connect(self.fechar_painel_topo)
        
        # Dados das planilhas
        self.dados_planilha = []
        self.dados_jogo = [{"imagem": "", "link": ""}, {"imagem": "", "link": ""}] 
        
        # Variáveis do pulo de 10 segundos
        self.aniversario_pulado = False
        self.timer_skip_10s = QTimer(self)
        self.timer_skip_10s.setSingleShot(True)
        self.timer_skip_10s.timeout.connect(self.executar_pulo_aniversario)

        # Container Principal
        self.container = QFrame(self)
        self.container.setObjectName("ContainerPrincipal")
        self.container.setGeometry(24, 0, 150, 150)
        self.atualizar_estilo_container()

        # Player
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        for ext in ['.wav', '.mp3', '.ogg']:
            if os.path.exists("parabens" + ext):
                self.player.setSource(QUrl.fromLocalFile(os.path.abspath("parabens" + ext)))
                break

        # ================= PÁGINA 1: ANIVERSÁRIOS =================
        self.page_aniv = QWidget(self.container)
        self.page_aniv.setGeometry(0, 0, 150, 150)
        
        self.nome_label = QLabel("Carregando...", self.page_aniv)
        self.nome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.data_label = QLabel("aguarde", self.page_aniv)
        self.data_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.linha_meio = QFrame(self.page_aniv)
        self.linha_meio.setStyleSheet("background-color: rgba(120, 120, 120, 80); border: none;")
        
        self.icone_label = QLabel(self.page_aniv)
        pix = QPixmap("calendar.png")
        if not pix.isNull():
            self.icone_label.setPixmap(pix.scaled(15, 15, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self.icone_label.setText("📅")
        self.icone_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icone_label.setFixedSize(20, 20)

        self.faltam_label = QLabel("Faltam", self.page_aniv)
        self.faltam_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dias_label = QLabel("...", self.page_aniv)
        self.dias_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # ================= PÁGINA 2: JOGO (Dividido em 2 Setores) =================
        self.page_jogo = QWidget(self.container)
        self.page_jogo.setGeometry(0, 0, 150, 150)
        self.page_jogo.hide()
        
        # SETOR 1
        self.img_label_jogo1 = QLabel("...", self.page_jogo)
        self.img_label_jogo1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label_jogo1.setGeometry(0, 0, 75, 150)
        
        self.btn_clique_jogo1 = QPushButton(self.page_jogo)
        self.btn_clique_jogo1.setGeometry(5, 42, 65, 65)
        self.btn_clique_jogo1.setStyleSheet("background: transparent; border: none;")
        self.btn_clique_jogo1.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clique_jogo1.clicked.connect(lambda: self.abrir_link_jogo(0))

        # SETOR 2
        self.img_label_jogo2 = QLabel("...", self.page_jogo)
        self.img_label_jogo2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label_jogo2.setGeometry(75, 0, 75, 150)
        
        self.btn_clique_jogo2 = QPushButton(self.page_jogo)
        self.btn_clique_jogo2.setGeometry(75 + 5, 42, 65, 65)
        self.btn_clique_jogo2.setStyleSheet("background: transparent; border: none;")
        self.btn_clique_jogo2.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clique_jogo2.clicked.connect(lambda: self.abrir_link_jogo(1))

        # ================= PAINEL SUPERIOR (BOTOES) =================
        self.top_panel = QWidget(self.container)
        self.top_panel.setGeometry(0, 0, 150, self.top_extra)
        top_layout = QHBoxLayout(self.top_panel)
        top_layout.setContentsMargins(10, 4, 10, 2)
        top_layout.setSpacing(3)

        estilo_botoes = "QPushButton { background-color: rgba(255, 255, 255, 40); border: none; border-radius: 5px; font-size: 10px; } QPushButton:hover { background-color: rgba(255, 255, 255, 80); }"

        self.btn_refresh = QPushButton("🔄", self.top_panel)
        self.btn_refresh.setFixedSize(20, 20)
        self.btn_refresh.setStyleSheet(estilo_botoes)
        self.btn_refresh.clicked.connect(self.baixar_todos_dados)

        self.btn_lista = QPushButton("📋", self.top_panel)
        self.btn_lista.setFixedSize(20, 20)
        self.btn_lista.setStyleSheet(estilo_botoes)
        self.btn_lista.clicked.connect(self.toggle_lista)
        
        self.btn_config = QPushButton("⚙️", self.top_panel)
        self.btn_config.setFixedSize(20, 20)
        self.btn_config.setStyleSheet(estilo_botoes)
        self.btn_config.clicked.connect(self.abrir_configuracoes)

        self.btn_pin = QPushButton("🔓", self.top_panel)
        self.btn_pin.setFixedSize(20, 20)
        self.btn_pin.setStyleSheet(estilo_botoes)
        self.btn_pin.clicked.connect(self.alternar_fixacao)

        self.btn_close = QPushButton("❌", self.top_panel)
        self.btn_close.setFixedSize(20, 20)
        self.btn_close.setStyleSheet(estilo_botoes)
        self.btn_close.clicked.connect(self.fechar_app)

        top_layout.addWidget(self.btn_refresh)
        top_layout.addWidget(self.btn_lista)
        top_layout.addWidget(self.btn_config)
        top_layout.addStretch()
        top_layout.addWidget(self.btn_pin)
        top_layout.addWidget(self.btn_close)
        
        self.linha_top = QFrame(self.container)
        self.linha_top.setStyleSheet("background-color: rgba(120, 120, 120, 80); border: none;")
        self.top_panel.hide()
        self.linha_top.hide()

        # ================= NAVEGAÇÃO DE PÁGINAS =================
        self.btn_nav_esq = QPushButton("<", self)
        self.btn_nav_esq.setGeometry(0, 63, 24, 24)
        self.btn_nav_esq.clicked.connect(lambda: self.mudar_pagina("esq"))
        self.btn_nav_esq.hide()

        self.btn_nav_dir = QPushButton(">", self)
        self.btn_nav_dir.setGeometry(174, 63, 24, 24)
        self.btn_nav_dir.clicked.connect(lambda: self.mudar_pagina("dir"))
        self.btn_nav_dir.hide()

        self.timer_hover = QTimer(self)
        self.timer_hover.timeout.connect(self.verificar_hover_bordas)
        self.timer_hover.start(100)

        # ================= INICIALIZAÇÃO =================
        self.janela_lista = JanelaLista()
        self.lista_aberta = False
        
        if config_app.pos_x is not None and config_app.pos_y is not None:
            self.move(config_app.pos_x, config_app.pos_y)
        else:
            screen = QApplication.primaryScreen().geometry()
            self.move((screen.width() - self.width()) // 2, (screen.height() - self.height()) // 2)

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
        if config_app.sempre_no_topo:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    def aplicar_tema(self):
        self.cor_texto = "#111111" if config_app.modo_claro else "#ffffff"
        self.atualizar_estilo_container()
        self.atualizar_estilo_setas()
        self.atualizar_interface_aniversario()
        if self.img_label_jogo1.text() == "...": self.img_label_jogo1.setStyleSheet(f"color: {self.cor_texto};")
        if self.img_label_jogo2.text() == "...": self.img_label_jogo2.setStyleSheet(f"color: {self.cor_texto};")
        if self.lista_aberta:
            self.janela_lista.atualizar_dados(self.dados_planilha, self.cor_texto)

    def fechar_painel_topo(self):
        if self.top_expanded:
            self.toggle_top_panel()

    def atualizar_estilo_container(self):
        if self.cor_texto == "#ffffff":
            bg_color = "rgba(25, 25, 25, 175)"
            border_color = "rgba(255, 255, 255, 50)"
        else:
            bg_color = "rgba(245, 245, 245, 180)"
            border_color = "rgba(255, 255, 255, 200)"

        self.container.setStyleSheet(f"""
            QFrame#ContainerPrincipal {{
                background-color: {bg_color}; 
                border-radius: 18px; 
                border: 1px solid {border_color};
            }}
            QLabel {{ background: transparent; border: none; }}
        """)

    def atualizar_estilo_setas(self):
        if self.cor_texto == "#ffffff":
            bg_btn = "rgba(20, 20, 20, 200)"
            bg_hover = "rgba(0, 0, 0, 230)"
            cor = "#ffffff"
        else:
            bg_btn = "rgba(240, 240, 240, 220)"
            bg_hover = "rgba(255, 255, 255, 255)"
            cor = "#111111"

        estilo = f"""
            QPushButton {{
                background-color: {bg_btn};
                border-radius: 12px;
                color: {cor};
                font-weight: bold;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {bg_hover};
            }}
        """
        self.btn_nav_esq.setStyleSheet(estilo)
        self.btn_nav_dir.setStyleSheet(estilo)

    # ----------------------------------------------------
    # LÓGICA DE NAVEGAÇÃO E HOVER (COM ANIMAÇÃO)
    # ----------------------------------------------------
    def verificar_hover_bordas(self):
        pos = self.mapFromGlobal(QCursor.pos())
        y_min = self.top_extra if self.top_expanded else 0
        
        if 0 <= pos.x() <= 24 and y_min <= pos.y() <= self.height():
            self.btn_nav_esq.show()
        else:
            self.btn_nav_esq.hide()
            
        if 174 <= pos.x() <= 198 and y_min <= pos.y() <= self.height():
            self.btn_nav_dir.show()
        else:
            self.btn_nav_dir.hide()

        # Reinicia o temporizador de 10s se o mouse passar sobre a área da bandeja
        if self.top_expanded:
            if 24 <= pos.x() <= 174 and 0 <= pos.y() <= self.top_extra:
                self.timer_autoclose.start(10000)

    def mudar_pagina(self, direcao):
        if self.anim_group and self.anim_group.state() == QAbstractAnimation.State.Running:
            return

        offset = self.top_extra if self.top_expanded else 0
        page_out = self.page_aniv if self.pagina_atual == 0 else self.page_jogo
        page_in = self.page_jogo if self.pagina_atual == 0 else self.page_aniv

        self.pagina_atual = 1 if self.pagina_atual == 0 else 0

        if direcao == "dir":
            start_x_in = 150
            end_x_out = -150
        else:
            start_x_in = -150
            end_x_out = 150

        page_in.setGeometry(start_x_in, offset, 150, 150)
        page_in.show()

        self.anim_out = QPropertyAnimation(page_out, b"pos")
        self.anim_out.setDuration(250)
        self.anim_out.setStartValue(QPoint(0, offset))
        self.anim_out.setEndValue(QPoint(end_x_out, offset))
        self.anim_out.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self.anim_in = QPropertyAnimation(page_in, b"pos")
        self.anim_in.setDuration(250)
        self.anim_in.setStartValue(QPoint(start_x_in, offset))
        self.anim_in.setEndValue(QPoint(0, offset))
        self.anim_in.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self.anim_group = QParallelAnimationGroup()
        self.anim_group.addAnimation(self.anim_out)
        self.anim_group.addAnimation(self.anim_in)
        
        self.anim_group.finished.connect(page_out.hide)
        self.anim_group.start()

    # ----------------------------------------------------
    # LÓGICA DE LAYOUT
    # ----------------------------------------------------
    def posicionar_elementos(self):
        offset = self.top_extra if self.top_expanded else 0
        self.top_panel.setGeometry(0, 0, 150, self.top_extra)
        self.linha_top.setGeometry(0, self.top_extra - 1, 150, 1)

        if not self.anim_group or self.anim_group.state() != QAbstractAnimation.State.Running:
            if self.pagina_atual == 0:
                self.page_aniv.setGeometry(0, offset, 150, 150)
                self.page_jogo.setGeometry(150, offset, 150, 150)
            else:
                self.page_jogo.setGeometry(0, offset, 150, 150)
                self.page_aniv.setGeometry(-150, offset, 150, 150)

        self.nome_label.setGeometry(10, 16, 130, 21)
        self.data_label.setGeometry(10, 36, 130, 16)
        self.linha_meio.setGeometry(0, 72, 150, 1)
        self.icone_label.move((150 - 20) // 2, 62)
        self.icone_label.raise_()
        self.faltam_label.setGeometry(10, 95, 130, 16)
        self.dias_label.setGeometry(10, 105, 130, 28)
        
        self.btn_nav_esq.move(0, 63 + offset)
        self.btn_nav_dir.move(174, 63 + offset)

        if self.lista_aberta:
            self.janela_lista.move(self.x() + 24, self.y() + self.height() + 5)

    def mousePressEvent(self, event):
        pos_y = event.position().y()
        if not self.top_expanded and pos_y < 25:
            self.toggle_top_panel()
            return
        if self.top_expanded and pos_y < self.top_extra:
            self.toggle_top_panel()
            return
            
        if event.button() == Qt.MouseButton.LeftButton and not self.fixado:
            self.oldPos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if not self.fixado and self.oldPos is not None:
            delta = event.globalPosition().toPoint() - self.oldPos
            self.move(self.pos() + delta)
            self.oldPos = event.globalPosition().toPoint()
            if self.lista_aberta:
                self.janela_lista.move(self.x() + 24, self.y() + self.height() + 5)

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
            if self.lista_aberta:
                self.janela_lista.hide()
        else:
            event.accept()
            QApplication.quit()

    def toggle_top_panel(self):
        self.top_expanded = not self.top_expanded
        if self.top_expanded:
            self.resize(198, 150 + self.top_extra)
            self.container.resize(150, 150 + self.top_extra)
            self.top_panel.show()
            self.linha_top.show()
            self.timer_autoclose.start(10000) # Inicia os 10s ao abrir
        else:
            self.top_panel.hide()
            self.linha_top.hide()
            self.resize(198, 150)
            self.container.resize(150, 150)
            self.timer_autoclose.stop() # Para o timer se for fechado manualmente
        self.posicionar_elementos()

    # ----------------------------------------------------
    # DADOS E REDE
    # ----------------------------------------------------
    def baixar_todos_dados(self):
        try:
            req_aniv = urllib.request.urlopen(URL_CSV_ANIVERSARIOS)
            csv_aniv = csv.reader(codecs.iterdecode(req_aniv, 'utf-8'))
            next(csv_aniv, None)
            self.dados_planilha = [(r[0].strip(), r[1].strip()) for r in csv_aniv if len(r) >= 2 and r[0].strip()]
        except: pass

        self.dados_jogo = [{"imagem": "", "link": ""}, {"imagem": "", "link": ""}]
        try:
            req_jogo = urllib.request.urlopen(URL_CSV_JOGO)
            csv_jogo = list(csv.reader(codecs.iterdecode(req_jogo, 'utf-8')))
            
            if len(csv_jogo) > 1 and len(csv_jogo[1]) >= 1:
                self.dados_jogo[0]["imagem"] = csv_jogo[1][0].strip()
                if len(csv_jogo[1]) >= 2:
                    self.dados_jogo[0]["link"] = csv_jogo[1][1].strip()
                    
            if len(csv_jogo) > 2 and len(csv_jogo[2]) >= 1:
                self.dados_jogo[1]["imagem"] = csv_jogo[2][0].strip()
                if len(csv_jogo[2]) >= 2:
                    self.dados_jogo[1]["link"] = csv_jogo[2][1].strip()
        except: pass

        self.carregar_imagem_jogo()
        self.atualizar_interface_aniversario()
        
        if self.lista_aberta:
            self.janela_lista.atualizar_dados(self.dados_planilha, self.cor_texto)

    def carregar_imagem_jogo(self):
        def setar_imagem(url, label):
            if not url:
                label.clear()
                label.setText("...")
                label.setStyleSheet(f"color: {self.cor_texto};")
                return
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
                data = urllib.request.urlopen(req).read()
                pix = QPixmap()
                pix.loadFromData(data)
                
                if pix.isNull():
                    raise Exception("Imagem Inválida")
                    
                label.setPixmap(pix.scaled(65, 65, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            except Exception as e:
                print(f"Erro imagem: {e}")
                label.clear()
                label.setText("...")
                label.setStyleSheet(f"color: {self.cor_texto};")

        setar_imagem(self.dados_jogo[0].get("imagem", ""), self.img_label_jogo1)
        setar_imagem(self.dados_jogo[1].get("imagem", ""), self.img_label_jogo2)

    def abrir_link_jogo(self, setor_idx):
        link = self.dados_jogo[setor_idx].get("link", "")
        if link:
            webbrowser.open(link)

    # ----------------------------------------------------
    # LÓGICA DE ANIVERSÁRIO
    # ----------------------------------------------------
    def executar_pulo_aniversario(self):
        self.aniversario_pulado = True
        self.atualizar_interface_aniversario()

    def atualizar_interface_aniversario(self):
        if not self.dados_planilha: return
        hoje = date.today()
        proximo_aniv, menor_diferenca = None, 99999

        for nome, data_str in self.dados_planilha:
            try:
                partes = data_str.split('/')
                dia, mes = int(partes[0]), int(partes[1])
                aniv = date(hoje.year, mes, dia)
                if aniv < hoje: aniv = date(hoje.year + 1, mes, dia)
                
                dias = (aniv - hoje).days
                
                if dias == 0 and self.aniversario_pulado:
                    continue

                if dias < menor_diferenca:
                    menor_diferenca, proximo_aniv = dias, (nome, dia, mes, dias)
            except: pass

        if proximo_aniv:
            nome, dia, mes, dias = proximo_aniv
            meses = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

            if dias == 0:
                self.pulse_timer.start(50)
                self.nome_label.setText("Parabéns")
                self.nome_label.setStyleSheet(aplicar_css_fonte("parabens_titulo", self.cor_texto))
                
                self.data_label.setText(f"{nome}!")
                self.data_label.setStyleSheet(aplicar_css_fonte("parabens_nome", "#d9480f"))
                
                self.faltam_label.setText("")
                self.dias_label.setText("🥳")

                if not self.ja_tocou_hoje():
                    self.player.play()
                    self.marcar_como_tocado()
                
                if not self.aniversario_pulado and not self.timer_skip_10s.isActive():
                    self.timer_skip_10s.start(10000)
            else:
                self.pulse_timer.stop()
                self.nome_label.setText(nome)
                self.nome_label.setStyleSheet(aplicar_css_fonte("nome", self.cor_texto))
                
                self.data_label.setText(f"{dia} de {meses[mes]}")
                self.data_label.setStyleSheet(aplicar_css_fonte("data", self.cor_texto))
                
                self.faltam_label.setText("Faltam")
                self.faltam_label.setStyleSheet(aplicar_css_fonte("faltam", self.cor_texto))
                
                texto_dias = "1 dia" if dias == 1 else f"{dias} dias"
                self.dias_label.setText(texto_dias)
                self.dias_label.setStyleSheet(aplicar_css_fonte("dias", self.cor_texto))

    def ja_tocou_hoje(self):
        try:
            with open(STATE_FILE, "r") as f: return f.read().strip() == date.today().isoformat()
        except: return False

    def marcar_como_tocado(self):
        try:
            with open(STATE_FILE, "w") as f: f.write(date.today().isoformat())
        except: pass

    # ----------------------------------------------------
    # FUNÇÕES UTILITÁRIAS
    # ----------------------------------------------------
    def animar_emoji(self):
        self.pulse_size += self.pulse_dir
        if self.pulse_size >= 24: self.pulse_dir = -1
        elif self.pulse_size <= 14: self.pulse_dir = 1
        self.dias_label.setStyleSheet(aplicar_css_fonte("dias", self.cor_texto).replace(f"font-size: {CONFIG_FONTES['dias']['tamanho']}px", f"font-size: {self.pulse_size}px"))

    def toggle_lista(self):
        self.lista_aberta = not self.lista_aberta
        if self.lista_aberta:
            self.janela_lista.atualizar_dados(self.dados_planilha, self.cor_texto)
            self.janela_lista.move(self.x() + 24, self.y() + self.height() + 5)
            self.janela_lista.show()
        else:
            self.janela_lista.hide()

    def abrir_configuracoes(self):
        self.janela_config = JanelaConfiguracoes(self)
        self.janela_config.exec()

    def alternar_fixacao(self):
        self.fixado = not self.fixado
        self.btn_pin.setText("📌" if self.fixado else "🔓")

    def fechar_app(self):
        if config_app.segundo_plano:
            self.hide()
            if self.lista_aberta:
                self.janela_lista.hide()
        else:
            QApplication.quit()

    def configurar_bandeja(self, pix):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon("calendar.png") if not pix.isNull() else QIcon())
        tray_menu = QMenu()
        acao_abrir = QAction("Abrir", self)
        acao_abrir.triggered.connect(lambda: (self.show(), self.activateWindow()))
        acao_sair = QAction("Sair", self)
        acao_sair.triggered.connect(QApplication.quit)
        tray_menu.addAction(acao_abrir)
        tray_menu.addAction(acao_sair)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    QApplication.setQuitOnLastWindowClosed(False) 
    app = QApplication(sys.argv)
    widget = WidgetFrutigerAero()
    widget.show()
    sys.exit(app.exec())