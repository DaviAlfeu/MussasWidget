import os
import sys
import time
import subprocess
import webbrowser
import urllib.request
import json
import tempfile
from datetime import date, datetime, timedelta

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QFrame, QPushButton, 
    QHBoxLayout, QVBoxLayout, QGridLayout, QDialog, QCheckBox, 
    QSystemTrayIcon, QMenu, QGraphicsScene, QGraphicsBlurEffect,
    QStackedWidget, QScrollArea, QComboBox, QSlider, QMessageBox,
    QFileDialog, QInputDialog, QFileIconProvider
)
from PyQt6.QtCore import (
    Qt, QTimer, QUrl, QPoint, pyqtSignal,
    QPropertyAnimation, QParallelAnimationGroup, QEasingCurve, QAbstractAnimation, QEvent, QSharedMemory,
    QSize, QFileInfo
)
from PyQt6.QtGui import (
    QCursor, QPixmap, QIcon, QAction, 
    QPainter, QPainterPath, QColor, QImage, QPen
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from config import (
    config_app, APP_VERSION, URL_UPDATE_CHECK, URL_DOWNLOAD_EXE, 
    STATE_FILE, PASTA_WALLPAPERS, CONFIG_FONTES
)
from utils import (
    parse_data_jogo_bg, raio_desfoque, alpha_desfoque, get_app_dir, resource_path, external_resource_path, carregar_fontes, versao_tuple, caminho_executavel_atual, executar_atualizacao_bat, normalizar_cor_hex, aplicar_css_fonte_base
)
from workers import WorkerDownload, WorkerMonitorProcessos
from ui_components import OutlineLabel, BlurredBackgroundFrame, ClickableLabel, ClickableMes
from dialogs import JanelaConfiguracoes, JanelaCalendario

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
        self.mostrando_parabens = False
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
            audio_path = external_resource_path("assets/parabens" + ext)
            if os.path.exists(audio_path):
                self.player.setSource(QUrl.fromLocalFile(audio_path))
                break

        # -- PÁGINA 1: ANIVERSÁRIOS --
        self.page_aniv = QWidget(self.pages_container)
        self.page_aniv.setGeometry(0, 0, 150, 150)
        self.nome_label = OutlineLabel("Carregando...", self.page_aniv)
        self.nome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.data_label = OutlineLabel("aguarde", self.page_aniv)
        self.data_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.linha_meio = QFrame(self.page_aniv)
        self.linha_meio.setStyleSheet("background-color: rgba(120, 120, 120, 80); border: none;")
        self.icone_label = QLabel(self.page_aniv)
        pix = QPixmap(resource_path("assets/calendar.png"))
        if not pix.isNull(): self.icone_label.setPixmap(pix.scaled(15, 15, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else: self.icone_label.setText("📅")
        self.icone_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icone_label.setFixedSize(20, 20)
        self.faltam_label = OutlineLabel("Faltam", self.page_aniv)
        self.faltam_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dias_label = OutlineLabel("...", self.page_aniv)
        self.dias_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # -- PÁGINA 2: JOGOS --
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

        # -- PÁGINA 3: ATALHOS (Modificada para 3x3 Dinâmico e Subpágina de Tempo) --
        self.page_atalhos = QWidget(self.pages_container)
        self.page_atalhos.setGeometry(0, 0, 150, 150)
        self.page_atalhos.hide()
        
        self.stacked_atalhos = QStackedWidget(self.page_atalhos)
        self.stacked_atalhos.setGeometry(0, 0, 150, 150)
        
        # Subpágina 3.1: Grelha com Scroll (3x3)
        self.atalhos_grid_page = QWidget()
        self.scroll_atalhos = QScrollArea(self.atalhos_grid_page)
        self.scroll_atalhos.setGeometry(0, 0, 150, 150)
        self.scroll_atalhos.setWidgetResizable(True)
        self.scroll_atalhos.setStyleSheet("background: transparent; border: none;")
        self.scroll_atalhos.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.scroll_content_atalhos = QWidget()
        self.scroll_content_atalhos.setStyleSheet("background: transparent;")
        self.layout_atalhos = QGridLayout(self.scroll_content_atalhos)
        self.layout_atalhos.setContentsMargins(10, 15, 10, 15)
        self.layout_atalhos.setSpacing(8)
        self.scroll_atalhos.setWidget(self.scroll_content_atalhos)
        
        # Subpágina 3.2: Detalhes do Atalho e Cronómetro de Uso
        self.atalhos_detail_page = QWidget()
        layout_detalhes = QVBoxLayout(self.atalhos_detail_page)
        layout_detalhes.setContentsMargins(10, 10, 10, 10)
        layout_detalhes.setSpacing(5)
        
        self.btn_voltar_atalho = QPushButton("⬅️")
        self.btn_voltar_atalho.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_voltar_atalho.clicked.connect(self.fechar_detalhes_atalho)
        
        self.lbl_nome_atalho = ClickableLabel("Nome do App")
        self.lbl_nome_atalho.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_nome_atalho.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_nome_atalho.setToolTip("Clique para renomear")
        self.lbl_nome_atalho.clicked.connect(self.renomear_atalho_atual)
        
        self.btn_abrir_atalho = QPushButton("Abrir App")
        self.btn_abrir_atalho.setFixedSize(90, 24)
        self.btn_abrir_atalho.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_abrir_atalho.clicked.connect(self.executar_atalho_atual)
        
        self.lbl_tempo_atalho = OutlineLabel("00:00:00")
        self.lbl_tempo_atalho.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_apagar_atalho = QPushButton("🗑️ Apagar")
        self.btn_apagar_atalho.setFixedSize(90, 24)
        self.btn_apagar_atalho.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apagar_atalho.clicked.connect(self.apagar_atalho_atual)

        layout_detalhes.addWidget(self.btn_voltar_atalho, alignment=Qt.AlignmentFlag.AlignLeft)
        layout_detalhes.addStretch()
        layout_detalhes.addWidget(self.lbl_nome_atalho)
        layout_detalhes.addWidget(self.lbl_tempo_atalho)
        layout_detalhes.addWidget(self.btn_abrir_atalho, alignment=Qt.AlignmentFlag.AlignCenter)
        layout_detalhes.addWidget(self.btn_apagar_atalho, alignment=Qt.AlignmentFlag.AlignCenter)
        layout_detalhes.addStretch()
        
        self.stacked_atalhos.addWidget(self.atalhos_grid_page)
        self.stacked_atalhos.addWidget(self.atalhos_detail_page)
        self.atalho_atual_idx = None
        self._ultimo_check_processos = time.monotonic()
        self._nomes_processo_cache = {}
        
        # Iniciar Worker para monitorizar processos (Tempo de uso)
        self.worker_processos = WorkerMonitorProcessos()
        self.worker_processos.processos_atualizados.connect(self.processar_nomes_rodando)
        self.worker_processos.start()

        # -- PAINEL SUPERIOR --
        self.top_panel = QWidget(self)
        self.top_panel.setGeometry(24, 0, 150, self.top_extra)
        top_layout = QHBoxLayout(self.top_panel)
        top_layout.setContentsMargins(10, 4, 10, 2)
        top_layout.setSpacing(3)
        estilo_botoes_top = "QPushButton { background-color: rgba(255, 255, 255, 40); border: none; border-radius: 5px; font-size: 10px; } QPushButton:hover { background-color: rgba(255, 255, 255, 80); }"

        self.btn_refresh = QPushButton("🔄", self.top_panel)
        self.btn_refresh.setFixedSize(20, 20)
        self.btn_refresh.setStyleSheet(estilo_botoes_top)
        self.btn_refresh.clicked.connect(self.baixar_todos_dados)
        self.btn_lista = QPushButton("📅", self.top_panel)
        self.btn_lista.setFixedSize(20, 20)
        self.btn_lista.setStyleSheet(estilo_botoes_top)
        self.btn_lista.clicked.connect(self.toggle_calendario)
        self.btn_config = QPushButton("⚙️", self.top_panel)
        self.btn_config.setFixedSize(20, 20)
        self.btn_config.setStyleSheet(estilo_botoes_top)
        self.btn_config.clicked.connect(lambda: JanelaConfiguracoes(self).exec())
        self.btn_pin = QPushButton("🔓", self.top_panel)
        self.btn_pin.setFixedSize(20, 20)
        self.btn_pin.setStyleSheet(estilo_botoes_top)
        self.btn_pin.clicked.connect(self.alternar_fixacao)
        self.btn_close = QPushButton("❌", self.top_panel)
        self.btn_close.setFixedSize(20, 20)
        self.btn_close.setStyleSheet(estilo_botoes_top)
        self.btn_close.clicked.connect(self.fechar_app)

        for b in [self.btn_refresh, self.btn_lista, self.btn_config]: top_layout.addWidget(b)
        top_layout.addStretch()
        for b in [self.btn_pin, self.btn_close]: top_layout.addWidget(b)
        
        self.linha_top = QFrame(self)
        self.linha_top.setGeometry(24, self.top_extra - 1, 150, 1)
        self.linha_top.setStyleSheet("background-color: rgba(120, 120, 120, 80); border: none;")
        self.top_panel.hide()
        self.linha_top.hide()

        # -- BOTÕES DE NAVEGAÇÃO --
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
        self.atualizar_botoes_atalhos()
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

        self.timer_update = QTimer(self)
        self.timer_update.timeout.connect(lambda: self.verificar_atualizacoes(manual=False))
        self.timer_update.start(24 * 60 * 60 * 1000)

        QTimer.singleShot(100, self.baixar_todos_dados)
        QTimer.singleShot(5000, lambda: self.verificar_atualizacoes(manual=False))
        self.posicionar_elementos()

    # ---- FUNÇÕES DA NOVA PÁGINA DE ATALHOS ----
    
    def atualizar_botoes_atalhos(self):
        # Limpa os botões existentes na grelha
        for i in reversed(range(self.layout_atalhos.count())):
            widget = self.layout_atalhos.itemAt(i).widget()
            if widget:
                widget.setParent(None)
                
        provider = QFileIconProvider()
        linha, coluna = 0, 0
        
        # Adiciona botões dos atalhos guardados
        for idx, caminho in enumerate(config_app.atalhos):
            btn = QPushButton()
            btn.setFixedSize(36, 36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            
            if caminho and os.path.exists(caminho):
                icon = provider.icon(QFileInfo(caminho))
                btn.setIcon(icon)
                btn.setIconSize(QSize(24, 24))
            else:
                btn.setText("?")
                
            btn.clicked.connect(lambda checked, i=idx: self.abrir_detalhes_atalho(i))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda pos, i=idx: self.menu_atalho(pos, i))
            
            self.layout_atalhos.addWidget(btn, linha, coluna)
            coluna += 1
            if coluna > 2: # Passar para próxima linha após a 3ª coluna
                coluna = 0
                linha += 1

        # Adiciona o botão de [+] no final
        btn_add = QPushButton("+")
        btn_add.setFixedSize(36, 36)
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.clicked.connect(self.adicionar_novo_atalho)
        self.layout_atalhos.addWidget(btn_add, linha, coluna)

        self.aplicar_estilos_aos_botoes_atalho()

    def adicionar_novo_atalho(self):
        novo_caminho, _ = QFileDialog.getOpenFileName(self, "Selecionar Atalho/Executável", "", "Executáveis/Atalhos (*.exe *.lnk *.bat);;Todos os Arquivos (*.*)")
        if novo_caminho:
            config_app.atalhos.append(novo_caminho)
            config_app.salvar()
            self.atualizar_botoes_atalhos()

    def menu_atalho(self, pos, idx):
        menu = QMenu(self)
        acao_remover = QAction("Remover Atalho", self)
        acao_remover.triggered.connect(lambda: self.remover_atalho(idx))
        
        # Encontra o botão clicado para abrir o menu
        botao = None
        # Procura o widget correto dentro do GridLayout
        for i in range(self.layout_atalhos.count()):
            widget = self.layout_atalhos.itemAt(i).widget()
            if isinstance(widget, QPushButton) and widget.underMouse():
                botao = widget
                break
                
        if botao:
            menu.exec(botao.mapToGlobal(pos))
            
    def remover_atalho(self, idx):
        if 0 <= idx < len(config_app.atalhos):
            config_app.atalhos.pop(idx)

            # Remover o atalho NÃO remove o histórico de tempo.
            config_app.salvar()

            if self.atalho_atual_idx == idx:
                self.atalho_atual_idx = None
                self.stacked_atalhos.setCurrentIndex(0)
            elif self.atalho_atual_idx is not None and self.atalho_atual_idx > idx:
                self.atalho_atual_idx -= 1

            self.atualizar_botoes_atalhos()

    def abrir_detalhes_atalho(self, idx):
        self.atalho_atual_idx = idx
        caminho = config_app.atalhos[idx]
        self.lbl_nome_atalho.setText(self.nome_exibicao_atalho(caminho))
        self.atualizar_label_tempo()
        self.stacked_atalhos.setCurrentIndex(1)
        self.aplicar_estilos_aos_botoes_atalho()

    def nome_exibicao_atalho(self, caminho):
        nome_custom = config_app.nomes_atalhos.get(caminho)
        if nome_custom: return nome_custom
        nome = os.path.basename(caminho) if caminho else "Atalho"
        return os.path.splitext(nome)[0].capitalize()

    def renomear_atalho_atual(self):
        if self.atalho_atual_idx is None or self.atalho_atual_idx >= len(config_app.atalhos): return
        caminho = config_app.atalhos[self.atalho_atual_idx]
        nome_atual = self.lbl_nome_atalho.text()
        novo_nome, ok = QInputDialog.getText(self, "Renomear Atalho", "Novo nome:", text=nome_atual)
        if ok and novo_nome.strip():
            config_app.nomes_atalhos[caminho] = novo_nome.strip()
            config_app.salvar()
            self.lbl_nome_atalho.setText(novo_nome.strip())

    def fechar_detalhes_atalho(self):
        self.stacked_atalhos.setCurrentIndex(0)
        self.atalho_atual_idx = None

    def apagar_atalho_atual(self):
        if self.atalho_atual_idx is None or self.atalho_atual_idx >= len(config_app.atalhos): return
        nome = self.lbl_nome_atalho.text()
        resposta = QMessageBox.question(
            self, "Apagar Atalho",
            f"Tem certeza que deseja apagar o atalho \"{nome}\"?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if resposta == QMessageBox.StandardButton.Yes:
            self.remover_atalho(self.atalho_atual_idx)

    def executar_atalho_atual(self):
        if self.atalho_atual_idx is not None and self.atalho_atual_idx < len(config_app.atalhos):
            caminho = config_app.atalhos[self.atalho_atual_idx]
            try:
                os.startfile(caminho)
            except Exception as e:
                QMessageBox.warning(self, "Erro", f"Não foi possível abrir o atalho:\n{e}")

    def atualizar_label_tempo(self):
        if self.atalho_atual_idx is not None and self.atalho_atual_idx < len(config_app.atalhos):
            caminho = config_app.atalhos[self.atalho_atual_idx]
            segundos = int(config_app.tempos_uso.get(caminho, 0))
            m, s = divmod(segundos, 60)
            h, m = divmod(m, 60)
            self.lbl_tempo_atalho.setText(f"{h:02d}:{m:02d}:{s:02d}")

    def _nomes_processo_do_atalho(self, caminho):
        caminho = os.path.abspath(caminho)
        if caminho in self._nomes_processo_cache:
            return self._nomes_processo_cache[caminho]

        nomes = set()
        nome = os.path.basename(caminho).lower()
        base = os.path.splitext(nome)[0]

        if nome:
            nomes.add(nome)
        if base:
            nomes.add(base)

        # Resolve .lnk uma única vez para detectar executáveis cujo
        # nome é diferente do nome do atalho.
        if caminho.lower().endswith(".lnk") and os.path.exists(caminho):
            try:
                comando = [
                    "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-Command",
                    "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($args[0]); "
                    "[Console]::Write($s.TargetPath)", caminho
                ]
                alvo = subprocess.check_output(
                    comando,
                    creationflags=0x08000000,
                    text=True,
                    timeout=2
                ).strip()

                if alvo:
                    alvo_nome = os.path.basename(alvo).lower()
                    alvo_base = os.path.splitext(alvo_nome)[0]
                    if alvo_nome:
                        nomes.add(alvo_nome)
                    if alvo_base:
                        nomes.add(alvo_base)
            except Exception:
                pass

        self._nomes_processo_cache[caminho] = nomes
        return nomes

    def processar_nomes_rodando(self, nomes_rodando):
        agora = time.monotonic()

        if not config_app.monitorar_tempo_atalhos:
            self._ultimo_check_processos = agora
            return

        ultimo = self._ultimo_check_processos
        self._ultimo_check_processos = agora
        delta = max(0.0, min(1.5, agora - ultimo))

        if delta <= 0:
            return

        houve_alteracao = False

        for caminho in list(config_app.atalhos):
            if not caminho:
                continue

            candidatos = self._nomes_processo_do_atalho(caminho)

            is_running = any(
                processo in candidatos or
                any(
                    processo.startswith(candidato)
                    for candidato in candidatos
                    if candidato
                )
                for processo in nomes_rodando
            )

            if is_running:
                config_app.tempos_uso[caminho] = (
                    config_app.tempos_uso.get(caminho, 0) + delta
                )
                houve_alteracao = True

        if houve_alteracao:
            if self.stacked_atalhos.currentIndex() == 1:
                self.atualizar_label_tempo()

            if int(time.time()) % 15 == 0:
                config_app.salvar()

    # ---- RESTANTE DA LÓGICA GERAL ----

    def aplicar_sempre_no_topo(self):
        flags = self.windowFlags()
        if config_app.sempre_no_topo: flags |= Qt.WindowType.WindowStaysOnTopHint
        else: flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    def cores_botoes(self):
        alpha = alpha_desfoque(config_app.desfoque)
        alpha_hover = min(255, alpha + 40)
        if config_app.modo_claro:
            return f"rgba(240, 240, 240, {alpha})", f"rgba(255, 255, 255, {alpha_hover})"
        return f"rgba(20, 20, 20, {alpha})", f"rgba(0, 0, 0, {alpha_hover})"

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
        
        bg_btn, bg_hover = self.cores_botoes()
        estilo = f"QPushButton {{ background-color: {bg_btn}; border-radius: 12px; color: {self.cor_texto}; font-weight: bold; border: none; }} QPushButton:hover {{ background-color: {bg_hover}; }}"
        self.btn_nav_esq.setStyleSheet(estilo)
        self.btn_nav_dir.setStyleSheet(estilo)
        
        self.aplicar_estilos_aos_botoes_atalho()
        
        # Estilos das labels da página de atalhos
        self.lbl_nome_atalho.atualizar_estilo(aplicar_css_fonte_base("lista"), self.cor_texto, self.borda_cor, self.esp_borda)
        self.lbl_tempo_atalho.atualizar_estilo(aplicar_css_fonte_base("nome"), self.cor_texto, self.borda_cor, self.esp_borda)
        
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

    def aplicar_estilos_aos_botoes_atalho(self):
        bg_btn, bg_hover = self.cores_botoes()
        estilo_atalhos = f"QPushButton {{ background-color: {bg_btn}; border-radius: 12px; color: {self.cor_texto}; font-weight: bold; font-size: 18px; border: none; }} QPushButton:hover {{ background-color: {bg_hover}; }}"
        
        for i in range(self.layout_atalhos.count()):
            widget = self.layout_atalhos.itemAt(i).widget()
            if isinstance(widget, QPushButton):
                widget.setStyleSheet(estilo_atalhos)
                
        # Estilos dos botões na página de detalhes
        estilo_menor = f"QPushButton {{ background-color: {bg_btn}; border-radius: 8px; color: {self.cor_texto}; font-size: 11px; font-weight: bold; padding: 4px; border: none; }} QPushButton:hover {{ background-color: {bg_hover}; }}"
        self.btn_voltar_atalho.setStyleSheet(estilo_menor)
        self.btn_abrir_atalho.setStyleSheet(estilo_menor)

        estilo_apagar = "QPushButton { background-color: rgba(217, 15, 15, 180); border-radius: 8px; color: #ffffff; font-size: 11px; font-weight: bold; padding: 4px; border: none; } QPushButton:hover { background-color: rgba(217, 15, 15, 230); }"
        self.btn_apagar_atalho.setStyleSheet(estilo_apagar)

    def verificar_atualizacoes(self, manual=False):
        if not getattr(sys, "frozen", False):
            if manual: QMessageBox.information(self, "Atualizações", f"Versão atual: {APP_VERSION}\n\nO atualizador automático funciona somente no .exe compilado.")
            return
            
        try:
            req = urllib.request.Request(URL_UPDATE_CHECK, headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/vnd.github.v3.raw"
            })
            with urllib.request.urlopen(req, timeout=10) as resposta:
                dados = json.loads(resposta.read().decode("utf-8"))
                
            versao_remota = str(dados.get("version", "")).strip()
            url_download = str(dados.get("download_url", dados.get("url", URL_DOWNLOAD_EXE))).strip()
            
            if not versao_remota or not url_download: raise ValueError("JSON de versão inválido no GitHub.")
            if versao_tuple(versao_remota) <= versao_tuple(APP_VERSION):
                if manual: QMessageBox.information(self, "Atualizações", f"Você já está usando a versão mais recente.\n\nVersão atual: {APP_VERSION}")
                return
                
            resposta_msg = QMessageBox.question(self, "Atualização disponível", f"Uma nova versão está disponível!\n\nAtual: {APP_VERSION}\nNova: {versao_remota}\n\nDeseja baixar e instalar agora?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes)
            if resposta_msg != QMessageBox.StandardButton.Yes: return
                
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            temp_dir = tempfile.gettempdir()
            novo_exe = os.path.join(temp_dir, f"MussasWidget_new_{os.getpid()}.exe")
            req_download = urllib.request.Request(url_download, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            
            with urllib.request.urlopen(req_download, timeout=120) as resposta_download:
                with open(novo_exe, "wb") as arquivo: arquivo.write(resposta_download.read())
                    
            if not os.path.exists(novo_exe) or os.path.getsize(novo_exe) < 100000:
                try: os.remove(novo_exe)
                except: pass
                raise RuntimeError("O arquivo baixado parece estar incompleto ou corrompido.")
                
            QApplication.restoreOverrideCursor()
            QMessageBox.information(self, "Download Concluído", "A atualização foi baixada com sucesso!\n\nO aplicativo será reiniciado agora.")
            executar_atualizacao_bat(novo_exe)
            os._exit(0)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            if manual: QMessageBox.critical(self, "Erro ao atualizar", "Não foi possível verificar ou instalar a atualização.\n\nDetalhes: " + str(e))

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
        
        paginas = [self.page_aniv, self.page_jogo, self.page_atalhos]
        page_out = paginas[self.pagina_atual]
        
        if direcao == "dir":
            self.pagina_atual = (self.pagina_atual + 1) % 3
            start_x_in, end_x_out = 150, -150
        else:
            self.pagina_atual = (self.pagina_atual - 1) % 3
            start_x_in, end_x_out = -150, 150
            
        page_in = paginas[self.pagina_atual]
        
        for i, p in enumerate(paginas):
            if i != self.pagina_atual and p != page_out: p.hide()
                
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
            paginas = [self.page_aniv, self.page_jogo, self.page_atalhos]
            for i, p in enumerate(paginas):
                if i == self.pagina_atual:
                    p.setGeometry(0, 0, 150, 150)
                    p.show()
                else:
                    p.setGeometry(150, 0, 150, 150)
                    p.hide()

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
        if event.button() == Qt.MouseButton.LeftButton:
            pos_x = event.position().x()
            if self.pagina_atual == 0 and self.mostrando_parabens and 24 <= pos_x <= 174 and 26 <= pos_y <= 176:
                self.pular_tela_parabens()
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
        if hasattr(self, 'worker') and self.worker.isRunning(): return 
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
        if self.calendario_aberto: self.aplicar_tema()

    def carregar_imagem_bytes(self, dados_bytes, label):
        if not dados_bytes:
            label.clear()
            label.setText("...")
            label.atualizar_estilo(aplicar_css_fonte_base("nome"), self.cor_texto, self.borda_cor, self.esp_borda)
            return
        pix = QPixmap()
        pix.loadFromData(dados_bytes)
        label.setPixmap(pix.scaled(65, 65, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))        

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
            if restante.total_seconds() <= 0: texto = "Encerrado"
            else: texto = self.formatar_tempo_jogo(restante)

        self.timer_jogo_label.setText(texto)
        self.timer_jogo_label.atualizar_estilo(aplicar_css_fonte_base("cal_titulo"), self.cor_texto, self.borda_cor, self.esp_borda)

    def formatar_tempo_jogo(self, restante):
        total = max(0, int(restante.total_seconds()))
        dias, resto = divmod(total, 86400)
        horas, resto = divmod(resto, 3600)
        minutos, segundos = divmod(resto, 60)
        if dias: return f"{dias}d {horas:02d}:{minutos:02d}:{segundos:02d}"
        return f"{horas:02d}:{minutos:02d}:{segundos:02d}"

    def abrir_link_jogo(self, setor_idx):
        link = self.dados_jogo[setor_idx].get("link", "")
        if link: webbrowser.open(link)

    def pular_tela_parabens(self):
        if not self.mostrando_parabens or self.aniversario_pulado: return
        self.timer_skip.stop()
        self.aniversario_pulado = True
        self.atualizar_interface_aniversario()

    def liberar_animacao_aniversario(self):
        self.aniversario_animacao_pronta = True
        self.atualizar_interface_aniversario()

    def iniciar_animacao_parabens(self):
        if self.aniversario_animacao_executada: return
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
                self.mostrando_parabens = True
                self.pulse_timer.start(50)
                self.nome_label.setText("Parabéns")
                self.nome_label.atualizar_estilo(aplicar_css_fonte_base("parabens_titulo"), self.cor_texto, self.borda_cor, self.esp_borda)
                self.data_label.setText(f"{nome}!")
                self.data_label.atualizar_estilo(aplicar_css_fonte_base("parabens_nome"), "#d90f0f", self.borda_cor, self.esp_borda)
                self.faltam_label.setText("")
                self.dias_label.setText("🤤")
                if self.aniversario_animacao_pronta and not self.aniversario_animacao_executada: self.iniciar_animacao_parabens()
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
                    self.timer_skip.start(config_app.tempo_parabens * 1000)
            else:
                self.mostrando_parabens = False
                self.pulse_timer.stop()
                if self.animacao_parabens and self.animacao_parabens.state() == QAbstractAnimation.State.Running: self.animacao_parabens.stop()
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
        if self.calendario_aberto and self.janela_calendario.isVisible(): self.timer_calendario_autoclose.start(10000)

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
            if self.calendario_aberto: self.janela_calendario.hide()
        else: QApplication.quit()

    def configurar_bandeja(self, pix):
        self.tray_icon = QSystemTrayIcon(self)
        tray_pix = QIcon(external_resource_path("assets/calendar.png"))
        if tray_pix.isNull(): tray_pix = QIcon(external_resource_path("assets/icone.ico"))
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

