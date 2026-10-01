import os
import sys
import time
import subprocess
import urllib.request
import json
import tempfile

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QFrame, QPushButton, 
    QHBoxLayout, QVBoxLayout, QGridLayout, QDialog, QCheckBox, 
    QSystemTrayIcon, QMenu, QGraphicsScene, QGraphicsBlurEffect,
    QStackedWidget, QScrollArea, QComboBox, QSlider, QMessageBox,
    QFileDialog, QInputDialog, QFileIconProvider
)
from PyQt6.QtCore import (
    Qt, QTimer, QUrl, QPoint, QRect, pyqtSignal,
    QPropertyAnimation, QParallelAnimationGroup, QEasingCurve, QAbstractAnimation, QEvent, QSharedMemory,
    QSize, QFileInfo
)
from PyQt6.QtGui import (
    QCursor, QPixmap, QIcon, QAction, 
    QPainter, QPainterPath, QColor, QImage, QPen, QRegion
)

from config import (
    config_app, APP_VERSION, URL_UPDATE_CHECK, URL_DOWNLOAD_EXE, 
    PASTA_WALLPAPERS, CONFIG_FONTES, MARGEM_SEGURANCA_BOLINHAS,
    MARGEM_AREA_ICONES
)
from utils import (
    raio_desfoque, alpha_desfoque, get_app_dir, resource_path, external_resource_path, carregar_fontes, versao_tuple, caminho_executavel_atual, executar_atualizacao_bat, normalizar_cor_hex, aplicar_css_fonte_base
)
from workers import WorkerMonitorProcessos
from ui_components import OutlineLabel, BlurredBackgroundFrame, ClickableLabel
from dialogs import JanelaConfiguracoes

class WidgetFrutigerAero(QWidget):
    def _aplicar_icone_botao(self, botao, nome_png, texto_fallback, icon_size=14):
        caminho = resource_path(f"assets/{nome_png}")
        if os.path.exists(caminho):
            botao.setText("")
            botao.setIcon(QIcon(caminho))
            botao.setIconSize(QSize(icon_size, icon_size))
        else:
            botao.setText(texto_fallback)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(198, 176) 
        
        carregar_fontes()

        # Estado base
        self.calendario_aberto = False
        self.janela_calendario = None
        self.top_expanded = False
        self.top_extra = 26
        self.oldPos = None
        self.fixado = False
        self.pagina_atual = 0
        self.anim_group = None
        self.borda_cor = None
        self.esp_borda = 0
        self.cor_texto = "#ffffff"
        self.paginas = []  # Lista dinâmica de páginas (QWidgets)

        # Timer de inatividade: volta para página principal após 15s
        self.timer_inatividade = QTimer(self)
        self.timer_inatividade.setSingleShot(True)
        self.timer_inatividade.timeout.connect(self._voltar_pagina_principal)
        
        self.timer_autoclose = QTimer(self)
        self.timer_autoclose.setSingleShot(True)
        self.timer_autoclose.timeout.connect(self.fechar_painel_topo)

        # Container principal
        self.container = BlurredBackgroundFrame(self)
        self.container.setGeometry(24, 26, 150, 150)

        self.pages_container = QWidget(self)
        self.pages_container.setGeometry(24, 26, 150, 150)

        # -- PÁGINA DE ATALHOS (sempre presente, é a base do app) --
        self.page_atalhos = QWidget(self.pages_container)
        self.page_atalhos.setGeometry(0, 0, 150, 150)
        
        self.stacked_atalhos = QStackedWidget(self.page_atalhos)
        self.stacked_atalhos.setGeometry(0, 0, 150, 150)
        
        # Subpágina: Grelha com Scroll (3x3)
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
        
        # Subpágina: Detalhes do Atalho
        self.atalhos_detail_page = QWidget()
        layout_detalhes = QVBoxLayout(self.atalhos_detail_page)
        layout_detalhes.setContentsMargins(10, 10, 10, 10)
        layout_detalhes.setSpacing(5)
        
        self.btn_voltar_atalho = QPushButton("⬅️")
        self.btn_voltar_atalho.setFixedSize(24, 24)
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

        top_detalhes = QHBoxLayout()
        top_detalhes.setContentsMargins(0, 0, 0, 0)
        top_detalhes.addWidget(self.btn_voltar_atalho, alignment=Qt.AlignmentFlag.AlignLeft)
        top_detalhes.addWidget(self.lbl_nome_atalho, 1, alignment=Qt.AlignmentFlag.AlignCenter)
        dummy = QWidget()
        dummy.setFixedSize(24, 24)
        top_detalhes.addWidget(dummy)
        
        layout_detalhes.addLayout(top_detalhes)
        layout_detalhes.addSpacing(5)
        layout_detalhes.addWidget(self.lbl_tempo_atalho)
        layout_detalhes.addSpacing(5)
        layout_detalhes.addWidget(self.btn_abrir_atalho, alignment=Qt.AlignmentFlag.AlignCenter)
        layout_detalhes.addWidget(self.btn_apagar_atalho, alignment=Qt.AlignmentFlag.AlignCenter)
        layout_detalhes.addStretch()
        
        self.stacked_atalhos.addWidget(self.atalhos_grid_page)
        self.stacked_atalhos.addWidget(self.atalhos_detail_page)
        self.atalho_atual_idx = None
        self._ultimo_check_processos = time.monotonic()
        self._nomes_processo_cache = {}

        # Registrar a página de atalhos como a primeira página
        self.page_atalhos.setProperty("mussas_page_key", "atalhos")
        self.page_atalhos.setProperty("mussas_page_name", "Atalhos")
        self.paginas.append(self.page_atalhos)
        self.page_atalhos.show()
        
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
        self.estilo_botoes_top = "QPushButton { background-color: rgba(255, 255, 255, 40); border: none; border-radius: 5px; font-size: 10px; } QPushButton:hover { background-color: rgba(255, 255, 255, 80); }"

        # Botões fixos do painel: config, pin, close (módulos inserirão os seus)
        self.btn_config = QPushButton(self.top_panel)
        self.btn_config.setFixedSize(20, 20)
        self.btn_config.setStyleSheet(self.estilo_botoes_top)
        self._aplicar_icone_botao(self.btn_config, "config.png", "⚙️")
        self.btn_config.clicked.connect(lambda: JanelaConfiguracoes(self).exec())
        
        self.btn_pin = QPushButton(self.top_panel)
        self.btn_pin.setFixedSize(20, 20)
        self.btn_pin.setStyleSheet(self.estilo_botoes_top)
        self._aplicar_icone_botao(self.btn_pin, "pin.png", "🔓")
        self.btn_pin.clicked.connect(self.alternar_fixacao)
        
        self.btn_close = QPushButton(self.top_panel)
        self.btn_close.setFixedSize(20, 20)
        self.btn_close.setStyleSheet(self.estilo_botoes_top)
        self._aplicar_icone_botao(self.btn_close, "close.png", "❌")
        self.btn_close.clicked.connect(self.fechar_app)

        # Layout do topo: [módulos inserem aqui] config | stretch | pin close
        self.top_layout = top_layout
        self._posicao_botoes_modulos = 0  # Índice onde inserir botões de módulos
        self.top_layout.addWidget(self.btn_config)
        self.top_layout.addStretch()
        self.top_layout.addWidget(self.btn_pin)
        self.top_layout.addWidget(self.btn_close)
        
        self.linha_top = QFrame(self)
        self.linha_top.setGeometry(24, self.top_extra - 1, 150, 1)
        self.linha_top.setStyleSheet("background-color: rgba(120, 120, 120, 80); border: none;")
        self.top_panel.hide()
        self.linha_top.hide()

        # -- BOTÕES DE NAVEGAÇÃO --
        self.btn_nav_esq = QPushButton(self)
        self.btn_nav_esq.setGeometry(0, 89, 24, 24)
        self._aplicar_icone_botao(self.btn_nav_esq, "seta_esq.png", "<")
        self.btn_nav_esq.clicked.connect(lambda: self.mudar_pagina("esq"))
        self.btn_nav_esq.hide()
        self.btn_nav_dir = QPushButton(self)
        self.btn_nav_dir.setGeometry(174, 89, 24, 24)
        self._aplicar_icone_botao(self.btn_nav_dir, "seta_dir.png", ">")
        self.btn_nav_dir.clicked.connect(lambda: self.mudar_pagina("dir"))
        self.btn_nav_dir.hide()

        self.timer_hover = QTimer(self)
        self.timer_hover.timeout.connect(self.verificar_hover_bordas)
        self.timer_hover.start(100)
        self._cursor_dentro_widget = False
        self._bolinhas_visiveis = False
        self.timer_ocultar_bolinhas = QTimer(self)
        self.timer_ocultar_bolinhas.setSingleShot(True)
        self.timer_ocultar_bolinhas.setInterval(10000)
        self.timer_ocultar_bolinhas.timeout.connect(self._ocultar_bolinhas)

        if config_app.pos_x is not None and config_app.pos_y is not None: self.move(config_app.pos_x, config_app.pos_y)
        else:
            s = QApplication.primaryScreen().geometry()
            self.move((s.width() - self.width()) // 2, (s.height() - self.height()) // 2)

        self.aplicar_sempre_no_topo()
        
        # Carregar módulos dinâmicos
        from gerenciador_modulos import GerenciadorModulos
        self.gerenciador_modulos = GerenciadorModulos(self)
        self.gerenciador_modulos.carregar_modulos()
        self.pagina_atual = self._indice_pagina_principal()

        # Bolinhas indicadoras de página
        self._criar_dots_pagina()

        self.aplicar_tema()
        self.atualizar_botoes_atalhos()
        
        pix = QPixmap(resource_path("assets/calendar.png"))
        self.configurar_bandeja(pix)

        self.timer_update = QTimer(self)
        self.timer_update.timeout.connect(lambda: self.verificar_atualizacoes(manual=False))
        self.timer_update.start(24 * 60 * 60 * 1000)
        QTimer.singleShot(5000, lambda: self.verificar_atualizacoes(manual=False))

        self.posicionar_elementos()

    # ---- API para módulos ----

    def registrar_pagina(self, widget, posicao=None, chave=None, nome=None):
        """Registra um QWidget como nova página. Retorna o índice."""
        widget.setProperty("mussas_page_key", chave or widget.objectName() or f"pagina_{len(self.paginas)}")
        widget.setProperty("mussas_page_name", nome or widget.objectName() or f"Página {len(self.paginas) + 1}")
        widget.setParent(self.pages_container)
        widget.setGeometry(150, 0, 150, 150)
        widget.hide()
        if posicao is not None and posicao < len(self.paginas):
            self.paginas.insert(posicao, widget)
            # Ajustar pagina_atual se necessário
            if self.pagina_atual >= posicao:
                self.pagina_atual += 1
        else:
            self.paginas.append(widget)
        self._aplicar_area_segura_paginas()
        return self.paginas.index(widget)

    def paginas_disponiveis(self):
        return [
            (pagina.property("mussas_page_name"), pagina.property("mussas_page_key"))
            for pagina in self.paginas
        ]

    def _indice_pagina_principal(self):
        chave = config_app.pagina_principal
        for indice, pagina in enumerate(self.paginas):
            if pagina.property("mussas_page_key") == chave:
                return indice
        return 0

    def adicionar_botao_topo(self, nome_png, texto_fallback, callback, posicao=None):
        """Adiciona um botão no painel superior. Retorna o QPushButton."""
        btn = QPushButton(self.top_panel)
        btn.setFixedSize(20, 20)
        btn.setStyleSheet(self.estilo_botoes_top)
        self._aplicar_icone_botao(btn, nome_png, texto_fallback)
        btn.clicked.connect(callback)
        
        if posicao is not None:
            insert_idx = min(posicao, self._posicao_botoes_modulos)
            self.top_layout.insertWidget(insert_idx, btn)
        else:
            self.top_layout.insertWidget(self._posicao_botoes_modulos, btn)
        self._posicao_botoes_modulos += 1
        return btn

    # ---- FUNÇÕES DA PÁGINA DE ATALHOS ----
    
    def atualizar_botoes_atalhos(self):
        for i in reversed(range(self.layout_atalhos.count())):
            widget = self.layout_atalhos.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        self.layout_atalhos.setContentsMargins(6, 6, 6, 6)
        self.layout_atalhos.setSpacing(4)
                
        provider = QFileIconProvider()
        linha, coluna = 0, 0
        max_colunas = 3
        area = self._area_segura_pagina()
        total_itens = len(config_app.atalhos) + 1
        total_linhas = max(1, (total_itens + max_colunas - 1) // max_colunas)
        largura_botao = (area.width() - 12 - 4 * (max_colunas - 1)) // max_colunas
        altura_botao = (area.height() - 12 - 4 * (total_linhas - 1)) // total_linhas
        tamanho_botao = max(12, min(36, largura_botao, altura_botao))
        tamanho_icone = max(10, min(24, tamanho_botao - 8))
        
        for idx, caminho in enumerate(config_app.atalhos):
            btn = QPushButton()
            btn.setFixedSize(tamanho_botao, tamanho_botao)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            
            if caminho and os.path.exists(caminho):
                icon = provider.icon(QFileInfo(caminho))
                btn.setIcon(icon)
                btn.setIconSize(QSize(tamanho_icone, tamanho_icone))
            else:
                btn.setText("?")
                
            btn.clicked.connect(lambda checked, i=idx: self.abrir_detalhes_atalho(i))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda pos, i=idx: self.menu_atalho(pos, i))
            
            self.layout_atalhos.addWidget(btn, linha, coluna)
            coluna += 1
            if coluna >= max_colunas:
                coluna = 0
                linha += 1

        btn_add = QPushButton("+")
        btn_add.setFixedSize(tamanho_botao, tamanho_botao)
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
        
        botao = None
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

        if nome: nomes.add(nome)
        if base: nomes.add(base)

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
                    if alvo_nome: nomes.add(alvo_nome)
                    if alvo_base: nomes.add(alvo_base)
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

    # ---- BOLINHAS INDICADORAS DE PÁGINA ----

    def _criar_dots_pagina(self):
        """Cria os indicadores sobre uma pequena área reservada da página."""
        num_dots = len(self.paginas)
        DOT_SIZE = 6
        DOT_SPACING = 8

        if hasattr(self, "container_dots"):
            self.container_dots.hide()
            self.container_dots.deleteLater()
            del self.container_dots
        if hasattr(self, "dots"):
            for dot in self.dots:
                dot.hide()
                dot.deleteLater()
        self.dots = []
        if num_dots <= 1:
            self._aplicar_area_segura_paginas()
            return

        posicao = config_app.posicao_bolinhas
        if posicao not in ("baixo", "cima", "esquerda", "direita"):
            posicao = "baixo"
        margem = MARGEM_SEGURANCA_BOLINHAS
        recuo_ponto = (margem - DOT_SIZE) // 2
        total = num_dots * DOT_SIZE + (num_dots - 1) * DOT_SPACING
        if posicao in ("baixo", "cima"):
            inicio = (150 - total) // 2
            x_base = inicio
            y_base = 150 - margem + recuo_ponto if posicao == "baixo" else recuo_ponto
        else:
            inicio = (150 - total) // 2
            x_base = recuo_ponto if posicao == "esquerda" else 150 - margem + recuo_ponto
            y_base = inicio

        for i in range(num_dots):
            dot = QFrame(self.pages_container)
            dot.setFixedSize(DOT_SIZE, DOT_SIZE)
            if posicao in ("baixo", "cima"):
                dot.move(x_base + i * (DOT_SIZE + DOT_SPACING), y_base)
            else:
                dot.move(x_base, y_base + i * (DOT_SIZE + DOT_SPACING))
            dot.raise_()
            dot.setVisible(self._bolinhas_visiveis)
            self.dots.append(dot)

        self._aplicar_area_segura_paginas()
        self._atualizar_dots_pagina()

    def _area_segura_pagina(self):
        margem = MARGEM_AREA_ICONES
        return QRect(margem, margem, 150 - margem * 2, 150 - margem * 2)

    def _aplicar_area_segura_paginas(self):
        area = self._area_segura_pagina()
        for pagina in self.paginas:
            pagina.setProperty("mussas_safe_area", area)
            pagina.setMask(QRegion(area))

        if hasattr(self, "stacked_atalhos"):
            self.stacked_atalhos.setGeometry(area)
            self.scroll_atalhos.setGeometry(0, 0, area.width(), area.height())
            self.atualizar_botoes_atalhos()

        if hasattr(self, "gerenciador_modulos"):
            self.gerenciador_modulos.notificar_area_pagina(
                (area.x(), area.y(), area.width(), area.height())
            )

    def _atualizar_dots_pagina(self):
        """Atualiza a cor das bolinhas conforme a página atual e o tema."""
        if not hasattr(self, 'dots') or not self.dots:
            return
        cor_ativa  = "#111111" if config_app.modo_claro else "#ffffff"
        cor_inativa = "rgba(150, 150, 150, 140)"
        for i, dot in enumerate(self.dots):
            cor = cor_ativa if i == self.pagina_atual else cor_inativa
            dot.setStyleSheet(f"QFrame {{ background-color: {cor}; border-radius: 3px; border: none; }}")
            dot.raise_()

    def _voltar_pagina_principal(self):
        """Retorna à página principal após inatividade."""
        pagina_principal = self._indice_pagina_principal()
        if self.pagina_atual != pagina_principal:
            self.mudar_pagina("dir")
            if self.pagina_atual != pagina_principal:
                QTimer.singleShot(300, self._voltar_pagina_principal)

    # ---- LÓGICA GERAL ----

    def aplicar_sempre_no_topo(self):
        flags = self.windowFlags()
        if config_app.sempre_no_topo: flags |= Qt.WindowType.WindowStaysOnTopHint
        else: flags &= ~Qt.WindowType.WindowStaysOnTopHint
        if flags == self.windowFlags():
            return
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
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

        # Notificar módulos sobre mudança de tema
        if hasattr(self, 'gerenciador_modulos'):
            self.gerenciador_modulos.notificar_tema()

        # Atualiza cor das bolinhas conforme o tema
        if hasattr(self, 'dots'):
            self._atualizar_dots_pagina()

    def aplicar_estilos_aos_botoes_atalho(self):
        bg_btn, bg_hover = self.cores_botoes()
        estilo_atalhos = f"QPushButton {{ background-color: {bg_btn}; border-radius: 12px; color: {self.cor_texto}; font-weight: bold; font-size: 18px; border: none; }} QPushButton:hover {{ background-color: {bg_hover}; }}"
        
        for i in range(self.layout_atalhos.count()):
            widget = self.layout_atalhos.itemAt(i).widget()
            if isinstance(widget, QPushButton):
                widget.setStyleSheet(estilo_atalhos)
                
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
        cursor_dentro = self.rect().contains(pos)
        if cursor_dentro and not self._cursor_dentro_widget:
            self._mostrar_bolinhas()
        self._cursor_dentro_widget = cursor_dentro

        y_min = 26
        if 0 <= pos.x() <= 24 and y_min <= pos.y() <= self.height(): self.btn_nav_esq.show()
        else: self.btn_nav_esq.hide()
        if 174 <= pos.x() <= 198 and y_min <= pos.y() <= self.height(): self.btn_nav_dir.show()
        else: self.btn_nav_dir.hide()
        
        if self.top_expanded and 24 <= pos.x() <= 174 and 0 <= pos.y() <= self.top_extra:
            self.timer_autoclose.start(10000)

    def _mostrar_bolinhas(self):
        self._bolinhas_visiveis = True
        for dot in getattr(self, "dots", []):
            dot.show()
            dot.raise_()
        self.timer_ocultar_bolinhas.start()

    def _ocultar_bolinhas(self):
        self._bolinhas_visiveis = False
        for dot in getattr(self, "dots", []):
            dot.hide()

    def mudar_pagina(self, direcao):
        if self.anim_group and self.anim_group.state() == QAbstractAnimation.State.Running: return
        
        num_paginas = len(self.paginas)
        if num_paginas <= 1: return

        page_out = self.paginas[self.pagina_atual]
        
        if direcao == "dir":
            self.pagina_atual = (self.pagina_atual + 1) % num_paginas
            start_x_in, end_x_out = 150, -150
        else:
            self.pagina_atual = (self.pagina_atual - 1) % num_paginas
            start_x_in, end_x_out = -150, 150
            
        page_in = self.paginas[self.pagina_atual]
        
        for i, p in enumerate(self.paginas):
            if i != self.pagina_atual and p != page_out: p.hide()
                
        page_in.setGeometry(start_x_in, 0, 150, 150)
        page_in.show()

        self.anim_out = QPropertyAnimation(page_out, b"pos")
        self.anim_out.setDuration(200)
        self.anim_out.setStartValue(QPoint(0, 0))
        self.anim_out.setEndValue(QPoint(end_x_out, 0))
        self.anim_out.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        self.anim_in = QPropertyAnimation(page_in, b"pos")
        self.anim_in.setDuration(200)
        self.anim_in.setStartValue(QPoint(start_x_in, 0))
        self.anim_in.setEndValue(QPoint(0, 0))
        self.anim_in.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self.anim_group = QParallelAnimationGroup()
        self.anim_group.addAnimation(self.anim_out)
        self.anim_group.addAnimation(self.anim_in)
        self.anim_group.finished.connect(page_out.hide)
        self.anim_group.start()

        self._atualizar_dots_pagina()

        # Timer de inatividade
        if self.pagina_atual != self._indice_pagina_principal() and config_app.voltar_pagina_principal:
            self.timer_inatividade.start(15000)
        else:
            self.timer_inatividade.stop()

    def posicionar_elementos(self):
        if not self.anim_group or self.anim_group.state() != QAbstractAnimation.State.Running:
            for i, p in enumerate(self.paginas):
                if i == self.pagina_atual:
                    p.setGeometry(0, 0, 150, 150)
                    p.show()
                else:
                    p.setGeometry(150, 0, 150, 150)
                    p.hide()

        if self.calendario_aberto and self.janela_calendario:
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
            if self.calendario_aberto and self.janela_calendario:
                self.janela_calendario.move(self.x() + 24, self.y() + self.height() + 5)

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
            if self.calendario_aberto and self.janela_calendario: self.janela_calendario.hide()
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

    def alternar_fixacao(self):
        self.fixado = not self.fixado
        self._aplicar_icone_botao(self.btn_pin, "pin_locked.png" if self.fixado else "pin.png", "📌" if self.fixado else "🔓")

    def fechar_app(self):
        if config_app.segundo_plano:
            self.hide()
            if self.calendario_aberto and self.janela_calendario: self.janela_calendario.hide()
        else: QApplication.quit()

    def configurar_bandeja(self, pix):
        self.tray_icon = QSystemTrayIcon(self)
        tray_pix = QIcon(external_resource_path("assets/icone.ico"))
        if tray_pix.isNull(): tray_pix = QIcon(external_resource_path("assets/calendar.png"))
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
