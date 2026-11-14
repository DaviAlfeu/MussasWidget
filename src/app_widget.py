import os
import sys
import time
import subprocess
import urllib.request
import json
import tempfile
import ctypes
from ctypes import wintypes

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QFrame, QPushButton, 
    QHBoxLayout, QVBoxLayout, QGridLayout, QDialog, QCheckBox, 
    QSystemTrayIcon, QMenu, QGraphicsScene, QGraphicsBlurEffect,
    QStackedWidget, QScrollArea, QComboBox, QSlider, QMessageBox, QProgressDialog,
    QFileDialog, QInputDialog, QFileIconProvider
)
from updater import (
    baixar_atualizacao,
    iniciar_aplicacao_da_atualizacao,
    obter_notas_release,
    pasta_updates,
    registrar_log,
    salvar_notas_release_pendentes,
)
from PyQt6.QtCore import (
    Qt, QTimer, QUrl, QPoint, QRect, pyqtSignal,
    QPropertyAnimation, QParallelAnimationGroup, QEasingCurve, QAbstractAnimation, QEvent, QSharedMemory,
    QSize, QFileInfo, QMimeData
)
from PyQt6.QtGui import (
    QCursor, QPixmap, QIcon, QAction, 
    QPainter, QPainterPath, QColor, QImage, QPen, QRegion, QDrag
)

from config import (
    config_app, APP_VERSION, URL_UPDATE_CHECK, URL_DOWNLOAD_EXE, 
    PASTA_WALLPAPERS, CONFIG_FONTES, MARGEM_SEGURANCA_BOLINHAS,
    MARGEM_AREA_ICONES
)
from utils import (
    raio_desfoque, alpha_desfoque, get_app_dir, resource_path, external_resource_path,
    carregar_fontes, versao_tuple, caminho_executavel_atual,
    executar_atualizacao_bat, pasta_temporaria_widget,
    normalizar_cor_hex, aplicar_css_fonte_base
)
from ui_components import OutlineLabel, BlurredBackgroundFrame, ClickableLabel, WrapLabel
from dialogs import JanelaConfiguracoes
from vidro import atualizar_vidro, esconder_vidro


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
        self._vidro = None
        self.paginas = []  # Lista dinâmica de páginas (QWidgets)
        self.espacamento_container = 4

        # Timer de inatividade: volta para página principal após 15s
        self.timer_inatividade = QTimer(self)
        self.timer_inatividade.setSingleShot(True)
        self.timer_inatividade.timeout.connect(self._voltar_pagina_principal)
        self.callbacks_interacao = []
        QApplication.instance().installEventFilter(self)
        
        self.timer_autoclose = QTimer(self)
        self.timer_autoclose.setSingleShot(True)
        self.timer_autoclose.timeout.connect(self.fechar_painel_topo)

        # Container principal
        self.container = BlurredBackgroundFrame(self)
        self.container.setGeometry(24, 26, 150, 150)

        self.pages_container = QWidget(self)
        self.pages_container.setGeometry(24, 26, 150, 150)

        # -- PÁGINA SEM MÓDULOS (exibida quando nenhum módulo estiver ativo) --
        self.page_sem_modulos = QWidget(self.pages_container)
        self.page_sem_modulos.setGeometry(0, 0, 150, 150)
        layout_sem_modulos = QVBoxLayout(self.page_sem_modulos)
        layout_sem_modulos.setContentsMargins(14, 14, 14, 14)
        layout_sem_modulos.setSpacing(8)
        layout_sem_modulos.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_sem_modulos_logo = QLabel(self.page_sem_modulos)
        self.lbl_sem_modulos_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._carregar_logo_sem_modulos()

        self.btn_baixar_modulos = QPushButton("Baixar Módulos", self.page_sem_modulos)
        self.btn_baixar_modulos.setFixedHeight(28)
        self.btn_baixar_modulos.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_baixar_modulos.clicked.connect(lambda: JanelaConfiguracoes(self, aba_inicial="modulos").exec())

        layout_sem_modulos.addStretch()
        layout_sem_modulos.addWidget(self.lbl_sem_modulos_logo, 0, Qt.AlignmentFlag.AlignCenter)
        layout_sem_modulos.addWidget(self.btn_baixar_modulos, 0, Qt.AlignmentFlag.AlignCenter)
        layout_sem_modulos.addStretch()

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
        self._atualizar_estado_sem_modulos()
        return self.paginas.index(widget)

    def paginas_disponiveis(self):
        return [
            (pagina.property("mussas_page_name"), pagina.property("mussas_page_key"))
            for pagina in self.paginas
        ]

    def _carregar_logo_sem_modulos(self):
        caminho_logo = resource_path("assets/logo.png")
        if os.path.exists(caminho_logo):
            pixmap = QPixmap(caminho_logo)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(
                    54, 54, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.lbl_sem_modulos_logo.setPixmap(pixmap)
                self.lbl_sem_modulos_logo.setText("")
                return
        self.lbl_sem_modulos_logo.setPixmap(QPixmap())
        self.lbl_sem_modulos_logo.setText("🙂")
        self.lbl_sem_modulos_logo.setStyleSheet("font-size: 42px; background: transparent;")

    def _atualizar_estado_sem_modulos(self):
        sem_modulos = len(self.paginas) == 0
        if sem_modulos:
            self.page_sem_modulos.show()
            self.btn_nav_esq.hide()
            self.btn_nav_dir.hide()
        else:
            self.page_sem_modulos.hide()
            if len(self.paginas) > 1 and self._cursor_dentro_widget:
                self.btn_nav_esq.show()
                self.btn_nav_dir.show()

    def rect_container_global(self):
        """Retorna o QRect global exato do container central (150x150 em repouso, ou 150x176 quando o topo expande)."""
        pos = self.mapToGlobal(self.container.pos())
        return QRect(pos.x(), pos.y(), self.container.width(), self.container.height())

    def notificar_geometria_alterada(self):
        """Notifica módulos e janelas satélites quando a geometria do container muda."""
        if hasattr(self, 'gerenciador_modulos') and self.gerenciador_modulos is not None:
            self.gerenciador_modulos.notificar_geometria()
        if hasattr(self, 'janela_calendario') and self.janela_calendario is not None and self.janela_calendario.isVisible():
            self.janela_calendario._reposicionar_na_referencia()

    def _indice_pagina_principal(self):
        if not self.paginas:
            return 0
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

    # ---- INDICADOR DE PÁGINA ----

    def _criar_dots_pagina(self):
        """Cria o indicador no estilo e na posição escolhidos."""
        num_paginas = len(self.paginas)
        numeros = config_app.indicador_pagina == "numeros"
        dot_size = 18 if numeros else 6
        spacing = 8

        if hasattr(self, "container_dots"):
            self.container_dots.hide()
            self.container_dots.deleteLater()
            del self.container_dots
        if hasattr(self, "dots"):
            for dot in self.dots:
                dot.hide()
                dot.deleteLater()
        self.dots = []
        if num_paginas <= 1:
            self._aplicar_area_segura_paginas()
            return

        posicao = config_app.posicao_bolinhas
        if posicao not in ("baixo", "cima", "esquerda", "direita"):
            posicao = "baixo"
        margem = MARGEM_SEGURANCA_BOLINHAS
        quantidade = 1 if numeros else num_paginas
        total = quantidade * dot_size + (quantidade - 1) * spacing
        recuo = (margem - dot_size) // 2
        if posicao in ("baixo", "cima"):
            inicio = (150 - total) // 2
            x_base = inicio
            y_base = (150 - margem + recuo) if posicao == "baixo" else recuo
        else:
            inicio = (150 - total) // 2
            x_base = recuo if posicao == "esquerda" else 150 - margem + recuo
            y_base = inicio

        for i in range(quantidade):
            dot = QLabel(self.pages_container)
            if numeros:
                dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dot.setFixedSize(dot_size, dot_size)
            if posicao in ("baixo", "cima"):
                dot.move(x_base + i * (dot_size + spacing), y_base)
            else:
                dot.move(x_base, y_base + i * (dot_size + spacing))
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
            if pagina.property("mussas_full_page_hit_area"):
                pagina.setMask(QRegion(0, 0, 150, 150))
            else:
                pagina.setMask(QRegion(area))

        if hasattr(self, "gerenciador_modulos"):
            self.gerenciador_modulos.notificar_area_pagina(
                (area.x(), area.y(), area.width(), area.height())
            )

    def _atualizar_dots_pagina(self):
        """Atualiza os indicadores numéricos da página atual e o tema."""
        if not hasattr(self, 'dots') or not self.dots:
            return
        cor_ativa = "#111111" if config_app.modo_claro else "#ffffff"
        cor_ativa_txt = "#ffffff" if config_app.modo_claro else "#111111"
        if config_app.indicador_pagina == "numeros":
            dot = self.dots[0]
            dot.setText(str(self.pagina_atual + 1))
            dot.setStyleSheet(
                f"QLabel {{ background-color: rgba({17 if config_app.modo_claro else 255}, {17 if config_app.modo_claro else 255}, {17 if config_app.modo_claro else 255}, 204); color: {cor_ativa_txt}; border-radius: 9px; border: none; font-size: 8px; font-weight: bold; qproperty-alignment: AlignCenter; }}"
            )
            dot.setVisible(self._bolinhas_visiveis)
            dot.raise_()
            return

        for indice, dot in enumerate(self.dots):
            cor = cor_ativa if indice == self.pagina_atual else "rgba(150, 150, 150, 140)"
            dot.setStyleSheet(
                f"QLabel {{ background-color: {cor}; border-radius: 3px; border: none; }}"
            )
            dot.setVisible(self._bolinhas_visiveis)
            dot.raise_()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.WindowActivate:
            if obj is self:
                QTimer.singleShot(0, lambda: self.aplicar_vidro_desfocado(forcar_blur=True))
            elif obj is getattr(self, "janela_calendario", None):
                QTimer.singleShot(
                    0,
                    lambda: atualizar_vidro(obj, obj.container, forcar_blur=True),
                )
        if event.type() in (
            QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress,
            QEvent.Type.Wheel, QEvent.Type.KeyPress,
        ) and isinstance(obj, QWidget):
            janela = obj.window()
            if janela is self or janela is getattr(self, "janela_calendario", None):
                self.registrar_interacao()
        return super().eventFilter(obj, event)

    def registrar_interacao(self):
        if self.timer_inatividade.isActive():
            self.timer_inatividade.start(15000)
        for callback in self.callbacks_interacao:
            callback()

    def _voltar_pagina_principal(self):
        """Retorna à página principal após inatividade."""
        if self.underMouse():
            self.timer_inatividade.start(15000)
            return
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
        self.aplicar_vidro_desfocado()

    def showEvent(self, event):
        super().showEvent(event)
        self.aplicar_vidro_desfocado()

    def aplicar_vidro_desfocado(self, forcar_blur=False):
        atualizar_vidro(self, self.container, forcar_blur=forcar_blur)

    def moveEvent(self, event):
        super().moveEvent(event)
        if getattr(self, "_vidro", None) is not None and self._vidro.isVisible():
            self.aplicar_vidro_desfocado()

    def hideEvent(self, event):
        super().hideEvent(event)
        esconder_vidro(self)
        if hasattr(self, 'gerenciador_modulos') and self.gerenciador_modulos is not None:
            self.gerenciador_modulos.notificar_ocultar_todos()

    def cores_botoes(self):
        alpha = alpha_desfoque(config_app.desfoque)
        alpha_hover = min(255, alpha + 40)
        base = QColor(config_app.cor_base)
        r, g, b = base.red(), base.green(), base.blue()
        if config_app.modo_claro:
            return f"rgba({r}, {g}, {b}, {alpha})", f"rgba({min(255, r + 15)}, {min(255, g + 15)}, {min(255, b + 15)}, {alpha_hover})"
        return f"rgba({r}, {g}, {b}, {alpha})", f"rgba({max(0, r - 15)}, {max(0, g - 15)}, {max(0, b - 15)}, {alpha_hover})"

    def aplicar_tema(self):
        wp_path = "Nenhum"
        if config_app.wallpaper != "Nenhum":
            caminho_wp = os.path.join(PASTA_WALLPAPERS, config_app.wallpaper)
            if os.path.exists(caminho_wp):
                wp_path = caminho_wp

        if config_app.vidro_desfocado:
            wp_path = "Nenhum"
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
                overlay = (120, 165, 196, 190)
                border = (255, 255, 255, 200)
            else:
                self.cor_texto = "#ffffff"
                overlay = (48, 66, 78, 190)
                border = (255, 255, 255, 50)
                
        self.aplicar_vidro_desfocado()
        self.container.update_background(wp_path, raio_desfoque(config_app.desfoque), overlay, border, 12, modo_claro=config_app.modo_claro, cor_base=config_app.cor_base)
        if config_app.vidro_desfocado:
            # Overlay translúcido para o desfoque do Windows aparecer por trás
            vidro = QColor(self.container.overlay_color)
            vidro.setAlpha(1)
            self.container.overlay_color = vidro
            self.container.update()
        
        bg_btn, bg_hover = self.cores_botoes()
        estilo = f"QPushButton {{ background-color: {bg_btn}; border-radius: 12px; color: {self.cor_texto}; font-weight: bold; border: none; }} QPushButton:hover {{ background-color: {bg_hover}; }}"
        self.btn_nav_esq.setStyleSheet(estilo)
        self.btn_nav_dir.setStyleSheet(estilo)
        
        self.btn_baixar_modulos.setStyleSheet(
            f"QPushButton {{ background-color: {bg_btn}; border-radius: 8px; color: {self.cor_texto}; font-weight: bold; font-size: 11px; padding: 4px 10px; border: none; }} "
            f"QPushButton:hover {{ background-color: {bg_hover}; }}"
        )

        # Notificar módulos sobre mudança de tema
        if hasattr(self, 'gerenciador_modulos'):
            self.gerenciador_modulos.notificar_tema()

        # Atualiza cor das bolinhas conforme o tema
        if hasattr(self, 'dots'):
            self._atualizar_dots_pagina()

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

            try:
                notas_release = obter_notas_release(versao_remota)
            except Exception as erro_release:
                registrar_log(
                    f"nao foi possivel obter notas da release {versao_remota}: "
                    f"{erro_release!r}"
                )
                notas_release = {
                    "version": versao_remota,
                    "name": f"Versão {versao_remota}",
                    "body": "",
                    "error": (
                        "Não foi possível obter as notas desta versão.\n\n"
                        f"Detalhes: {erro_release}"
                    ),
                }
                
            progresso = QProgressDialog("Baixando atualização...", None, 0, 100, self)
            progresso.setWindowTitle("Atualizando")
            progresso.setWindowModality(Qt.WindowModality.WindowModal)
            progresso.setMinimumDuration(0)
            progresso.setValue(0)

            def ao_progresso(pct):
                progresso.setValue(pct)
                QApplication.processEvents()

            try:
                novo_exe = baixar_atualizacao(url_download, versao_remota, ao_progresso)
            finally:
                progresso.close()

            salvar_notas_release_pendentes(notas_release)
            QMessageBox.information(self, "Download Concluído", "A atualização foi baixada com sucesso!\n\nO aplicativo será reiniciado agora.")
            iniciar_aplicacao_da_atualizacao(novo_exe)
            os._exit(0)
        except Exception as e:
            registrar_log(f"erro na atualizacao: {e!r}")
            if manual: QMessageBox.critical(self, "Erro ao atualizar", "Não foi possível verificar ou instalar a atualização.\n\nDetalhes: " + str(e) + "\n\nLog: " + str(pasta_updates() / "update.log"))

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

        # Fechar tudo referente ao módulo anterior e popups abertos
        if hasattr(self, 'gerenciador_modulos') and self.gerenciador_modulos is not None:
            self.gerenciador_modulos.notificar_troca_pagina(page_out, page_in)

        if getattr(self, "calendario_aberto", False) and getattr(self, "janela_calendario", None):
            self.calendario_aberto = False
            self.janela_calendario.hide()

        for top in QApplication.topLevelWidgets():
            if isinstance(top, QMenu) and top.isVisible():
                top.close()
        
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
        self._atualizar_estado_sem_modulos()
        if not self.anim_group or self.anim_group.state() != QAbstractAnimation.State.Running:
            for i, p in enumerate(self.paginas):
                if i == self.pagina_atual:
                    p.setGeometry(0, 0, 150, 150)
                    p.show()
                else:
                    p.setGeometry(150, 0, 150, 150)
                    p.hide()

        if self.calendario_aberto and self.janela_calendario:
            self.janela_calendario._reposicionar_na_referencia()

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
            self.aplicar_vidro_desfocado()
        else:
            self.container.setGeometry(24, 26, 150, 150)
            self.top_panel.hide()
            self.linha_top.hide()
            self.timer_autoclose.stop()
            self.aplicar_vidro_desfocado()

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
