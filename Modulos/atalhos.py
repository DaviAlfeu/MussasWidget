import os
import subprocess
import time
from PyQt6.QtCore import (
    Qt, QSize, QPoint, QRect, QFileInfo, QMimeData, QTimer
)
from PyQt6.QtGui import (
    QDrag, QColor, QFont, QRegion
)
from PyQt6.QtWidgets import (
    QWidget, QPushButton, QLabel, QStackedWidget, QScrollArea,
    QGridLayout, QHBoxLayout, QVBoxLayout, QMenu, QFileDialog,
    QInputDialog, QMessageBox, QFileIconProvider, QFrame
)

from gerenciador_modulos import PluginBase
from config import config_app
from atalhos_store import AtalhosStore
from workers import WorkerMonitorProcessos
from ui_components import OutlineLabel, ClickableLabel
from utils import aplicar_css_fonte_base

LARGURA_NOME_ATALHO = 130
LARGURA_DETALHE_ATALHO = 130


class BotaoAtalhoArrastavel(QPushButton):
    """Botão de atalho com suporte a arrastar e soltar para reorganizar."""
    FORMATO_ARRASTO = "application/x-mussas-atalho"

    def __init__(self, indice, ao_reordenar, arrastavel=True, parent=None):
        super().__init__(parent)
        self.indice_atalho = indice
        self._ao_reordenar = ao_reordenar
        self._arrastavel = arrastavel
        self._pos_pressionada = None
        self._arrastando = False
        self.setAcceptDrops(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._arrastavel:
            self._pos_pressionada = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            self._arrastavel
            and self._pos_pressionada is not None
            and (event.buttons() & Qt.MouseButton.LeftButton)
            and (event.pos() - self._pos_pressionada).manhattanLength() >= 8
        ):
            self._iniciar_arrasto()
            self._pos_pressionada = None
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._pos_pressionada = None
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        event.ignore()

    def _iniciar_arrasto(self):
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(self.FORMATO_ARRASTO, str(self.indice_atalho).encode("ascii"))
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.setHotSpot(self.rect().center())
        self._arrastando = True
        self.setDown(False)
        try:
            drag.exec(Qt.DropAction.MoveAction)
        finally:
            self._arrastando = False

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(self.FORMATO_ARRASTO):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(self.FORMATO_ARRASTO):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(self.FORMATO_ARRASTO):
            super().dropEvent(event)
            return

        dados = bytes(event.mimeData().data(self.FORMATO_ARRASTO)).decode("ascii")
        try:
            origem = int(dados)
        except ValueError:
            return

        event.acceptProposedAction()
        if self._ao_reordenar is not None:
            self._ao_reordenar(origem, self.indice_atalho)


class Plugin(PluginBase):
    nome = "Atalhos"
    versao = "1.0.0"
    dependencias = []

    def __init__(self, app):
        super().__init__(app)
        self.atalhos_store = AtalhosStore(config_app)
        self.atalho_atual_idx = None
        self._ultimo_check_processos = time.monotonic()
        self._nomes_processo_cache = {}
        self._icon_cache = {}
        self._provider = QFileIconProvider()

        # Página raiz
        self.page = QWidget()
        self.page.setObjectName("page_atalhos")
        self.page.setGeometry(0, 0, 150, 150)

        self.stacked_atalhos = QStackedWidget(self.page)
        self.stacked_atalhos.setGeometry(0, 0, 150, 150)

        # Subpágina: Grelha com Scroll (3x3)
        self.atalhos_grid_page = QWidget()
        layout_grid_page = QVBoxLayout(self.atalhos_grid_page)
        layout_grid_page.setContentsMargins(0, 0, 0, 0)
        layout_grid_page.setSpacing(0)

        self.scroll_atalhos = QScrollArea(self.atalhos_grid_page)
        self.scroll_atalhos.setWidgetResizable(True)
        self.scroll_atalhos.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_atalhos.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_atalhos.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_atalhos.setStyleSheet("background: transparent; border: none;")

        self.scroll_content_atalhos = QWidget()
        self.scroll_content_atalhos.setStyleSheet("background: transparent;")
        self.layout_atalhos = QGridLayout(self.scroll_content_atalhos)
        self.layout_atalhos.setContentsMargins(6, 6, 6, 6)
        self.layout_atalhos.setSpacing(4)
        self.scroll_atalhos.setWidget(self.scroll_content_atalhos)
        layout_grid_page.addWidget(self.scroll_atalhos)

        # Subpágina: Detalhes do Atalho
        self.atalhos_detail_page = QWidget()
        layout_detalhes = QVBoxLayout(self.atalhos_detail_page)
        layout_detalhes.setContentsMargins(10, 10, 10, 10)

        self.btn_voltar_atalho = QPushButton("<")
        self.btn_voltar_atalho.setFixedSize(24, 24)
        self.btn_voltar_atalho.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_voltar_atalho.clicked.connect(self.voltar_para_grade)

        self.lbl_nome_atalho = ClickableLabel("App")
        self.lbl_nome_atalho.setToolTip("Clique para renomear")
        self.lbl_nome_atalho.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_nome_atalho.clicked.connect(self.renomear_atalho_atual)

        self.btn_abrir_atalho = QPushButton("Abrir")
        self.btn_abrir_atalho.setFixedSize(LARGURA_DETALHE_ATALHO - 20, 26)
        self.btn_abrir_atalho.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_abrir_atalho.clicked.connect(self.executar_atalho_atual)

        self.lbl_tempo_atalho = OutlineLabel("00:00:00")
        self.lbl_tempo_atalho.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_apagar_atalho = QPushButton("🗑")
        self.btn_apagar_atalho.setFixedSize(24, 24)
        self.btn_apagar_atalho.setToolTip("Apagar atalho")
        self.btn_apagar_atalho.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apagar_atalho.clicked.connect(self.apagar_atalho_atual)

        top_detalhes = QHBoxLayout()
        top_detalhes.setContentsMargins(0, 0, 0, 0)
        top_detalhes.setSpacing(2)
        top_detalhes.addWidget(self.btn_voltar_atalho, alignment=Qt.AlignmentFlag.AlignTop)
        top_detalhes.addStretch(1)
        top_detalhes.addWidget(self.lbl_nome_atalho, alignment=Qt.AlignmentFlag.AlignTop)
        top_detalhes.addStretch(1)
        top_detalhes.addWidget(self.btn_apagar_atalho, alignment=Qt.AlignmentFlag.AlignTop)

        layout_detalhes.addLayout(top_detalhes)
        layout_detalhes.addStretch(1)
        layout_detalhes.addWidget(self.lbl_tempo_atalho)
        layout_detalhes.addStretch(1)
        layout_detalhes.addWidget(self.btn_abrir_atalho, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.stacked_atalhos.addWidget(self.atalhos_grid_page)
        self.stacked_atalhos.addWidget(self.atalhos_detail_page)
        self.stacked_atalhos.currentChanged.connect(lambda _: self._ajustar_geometria_atalhos())

        # Worker monitor de processos
        self.worker_processos = WorkerMonitorProcessos()
        self.worker_processos.processos_atualizados.connect(self.processar_nomes_rodando)
        if config_app.monitorar_tempo_atalhos:
            self.worker_processos.start()

        self._ajustar_geometria_atalhos()
        self.atualizar_botoes_atalhos()

    def criar_pagina(self):
        self.page.setProperty("mussas_page_key", "atalhos")
        self.page.setProperty("mussas_page_name", "Atalhos")
        return self.page

    def _obter_icone_em_cache(self, caminho):
        if not caminho or not os.path.exists(caminho):
            return None
        if caminho in self._icon_cache:
            return self._icon_cache[caminho]
        try:
            icon = self._provider.icon(QFileInfo(caminho))
            self._icon_cache[caminho] = icon
            return icon
        except Exception:
            return None

    def atualizar_botoes_atalhos(self):
        while self.layout_atalhos.count():
            item = self.layout_atalhos.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self.layout_atalhos.setContentsMargins(6, 6, 6, 6)
        self.layout_atalhos.setSpacing(4)
        self.layout_atalhos.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        max_colunas = 3
        area = self._obter_area_segura()
        atalhos = self.atalhos_store.caminhos()
        total_itens = len(atalhos) + 1
        total_linhas = max(3, (total_itens + max_colunas - 1) // max_colunas)
        largura_botao = (area.width() - 12 - 4 * (max_colunas - 1)) // max_colunas
        altura_botao = (area.height() - 12 - 4 * (3 - 1)) // 3
        tamanho_botao = max(12, min(36, largura_botao, altura_botao))
        tamanho_icone = max(10, min(24, tamanho_botao - 8))

        self.scroll_content_atalhos.setFixedWidth(area.width())
        self.scroll_content_atalhos.setMinimumHeight(
            12 + total_linhas * tamanho_botao + 4 * (total_linhas - 1),
        )
        for indice in range(self.layout_atalhos.rowCount()):
            self.layout_atalhos.setRowMinimumHeight(indice, 0)
            self.layout_atalhos.setRowStretch(indice, 0)
        for indice in range(max_colunas):
            self.layout_atalhos.setColumnMinimumWidth(indice, tamanho_botao)
            self.layout_atalhos.setColumnStretch(indice, 0)
        for indice in range(total_linhas):
            self.layout_atalhos.setRowMinimumHeight(indice, tamanho_botao)
            self.layout_atalhos.setRowStretch(indice, 0)

        for idx, caminho in enumerate(atalhos):
            btn = BotaoAtalhoArrastavel(idx, self.reordenar_atalho)
            btn.setFixedSize(tamanho_botao, tamanho_botao)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip("Arraste para reorganizar")

            icon = self._obter_icone_em_cache(caminho)
            if icon is not None and not icon.isNull():
                btn.setIcon(icon)
                btn.setIconSize(QSize(tamanho_icone, tamanho_icone))
            else:
                btn.setText("?")

            btn.clicked.connect(lambda checked, i=idx: self.abrir_detalhes_atalho(i))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda pos, i=idx: self.menu_atalho(pos, i))

            self.layout_atalhos.addWidget(btn, idx // max_colunas, idx % max_colunas, Qt.AlignmentFlag.AlignCenter)

        btn_add = BotaoAtalhoArrastavel(
            len(atalhos), self.reordenar_atalho, arrastavel=False
        )
        btn_add.setText("+")
        btn_add.setFixedSize(tamanho_botao, tamanho_botao)
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.setToolTip("Adicionar atalho ou solte aqui para movê-lo ao fim")
        btn_add.clicked.connect(self.adicionar_novo_atalho)
        self.layout_atalhos.addWidget(
            btn_add, len(atalhos) // max_colunas,
            len(atalhos) % max_colunas,
            Qt.AlignmentFlag.AlignCenter,
        )

        self.aplicar_estilos_aos_botoes_atalho()

    def reordenar_atalho(self, origem, destino):
        quantidade = self.atalhos_store.quantidade()
        if (
            not isinstance(origem, int)
            or not isinstance(destino, int)
            or origem < 0
            or origem >= quantidade
            or destino < 0
            or destino > quantidade
            or origem == destino
        ):
            return

        if not self.atalhos_store.mover(origem, destino):
            return

        if self.atalho_atual_idx is not None:
            if self.atalho_atual_idx == origem:
                self.atalho_atual_idx = destino
            elif origem < self.atalho_atual_idx <= destino:
                self.atalho_atual_idx -= 1
            elif destino <= self.atalho_atual_idx < origem:
                self.atalho_atual_idx += 1

        self.atualizar_botoes_atalhos()

    def adicionar_novo_atalho(self):
        caminho, _ = QFileDialog.getOpenFileName(
            self.app, "Selecionar Executável ou Atalho", "", "Executáveis (*.exe *.lnk);;Todos os Arquivos (*.*)"
        )
        if caminho:
            self._icon_cache.pop(caminho, None)
            if self.atalhos_store.adicionar(caminho):
                self.atualizar_botoes_atalhos()

    def abrir_detalhes_atalho(self, idx):
        if idx >= self.atalhos_store.quantidade():
            return
        self.atalho_atual_idx = idx
        caminho = self.atalhos_store.caminho_por_indice(idx)

        nome = self.atalhos_store.nome_customizado(caminho)
        if not nome:
            nome = os.path.splitext(os.path.basename(caminho))[0]
        self.lbl_nome_atalho.setText(nome)
        self.lbl_nome_atalho.ajustar_para_largura(LARGURA_NOME_ATALHO, max_linhas=2)

        segundos = self.atalhos_store.segundos_uso(caminho)
        self.atualizar_label_tempo(segundos)

        self.stacked_atalhos.setCurrentWidget(self.atalhos_detail_page)

    def voltar_para_grade(self):
        self.atalho_atual_idx = None
        self.stacked_atalhos.setCurrentWidget(self.atalhos_grid_page)

    def fechar_paineis(self):
        self.voltar_para_grade()

    def ao_desativar_pagina(self, pagina=None):
        self.fechar_paineis()

    def executar_atalho_atual(self):
        if self.atalho_atual_idx is not None and self.atalho_atual_idx < self.atalhos_store.quantidade():
            caminho = self.atalhos_store.caminho_por_indice(self.atalho_atual_idx)
            if caminho and os.path.exists(caminho):
                try:
                    os.startfile(caminho)
                except Exception as e:
                    QMessageBox.warning(self.app, "Erro", f"Não foi possível iniciar o atalho:\n{e}")
            else:
                QMessageBox.warning(self.app, "Erro", "Arquivo não encontrado ou inválido.")

    def renomear_atalho_atual(self):
        if self.atalho_atual_idx is None or self.atalho_atual_idx >= self.atalhos_store.quantidade():
            return
        caminho = self.atalhos_store.caminho_por_indice(self.atalho_atual_idx)
        nome_atual = self.atalhos_store.nome_customizado(caminho) or os.path.splitext(os.path.basename(caminho))[0]

        novo_nome, ok = QInputDialog.getText(
            self.app, "Renomear Atalho", "Digite o novo nome para o atalho:", text=nome_atual
        )
        if ok and novo_nome.strip():
            self.atalhos_store.renomear(caminho, novo_nome.strip())
            self.lbl_nome_atalho.setText(novo_nome.strip())
            self.lbl_nome_atalho.ajustar_para_largura(LARGURA_NOME_ATALHO, max_linhas=2)

    def apagar_atalho_atual(self):
        if self.atalho_atual_idx is None or self.atalho_atual_idx >= self.atalhos_store.quantidade():
            return
        caminho = self.atalhos_store.caminho_por_indice(self.atalho_atual_idx)
        resposta = QMessageBox.question(
            self.app, "Apagar Atalho",
            f"Tem certeza que deseja apagar o atalho '{os.path.basename(caminho)}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resposta == QMessageBox.StandardButton.Yes:
            self._icon_cache.pop(caminho, None)
            self.atalhos_store.remover(self.atalho_atual_idx)
            self.voltar_para_grade()
            self.atualizar_botoes_atalhos()

    def menu_atalho(self, pos, idx):
        if idx >= self.atalhos_store.quantidade():
            return
        menu = QMenu(self.app)
        acao_abrir = menu.addAction("Abrir")
        acao_detalhes = menu.addAction("Detalhes")
        acao_apagar = menu.addAction("Apagar")
        
        btn = self.layout_atalhos.itemAt(idx).widget()
        ponto_global = btn.mapToGlobal(pos) if btn else self.app.mapToGlobal(pos)
        acao_escolhida = menu.exec(ponto_global)
        
        if acao_escolhida == acao_abrir:
            self.atalho_atual_idx = idx
            self.executar_atalho_atual()
        elif acao_escolhida == acao_detalhes:
            self.abrir_detalhes_atalho(idx)
        elif acao_escolhida == acao_apagar:
            self.atalho_atual_idx = idx
            self.apagar_atalho_atual()

    def atualizar_label_tempo(self, segundos):
        horas = int(segundos // 3600)
        minutos = int((segundos % 3600) // 60)
        segs = int(segundos % 60)
        self.lbl_tempo_atalho.setText(f"{horas:02d}:{minutos:02d}:{segs:02d}")

    def processar_nomes_rodando(self, nomes_rodando):
        if not config_app.monitorar_tempo_atalhos:
            return

        agora = time.monotonic()
        delta = agora - self._ultimo_check_processos
        self._ultimo_check_processos = agora

        if delta <= 0 or delta > 10:
            return

        atalhos = self.atalhos_store.caminhos()
        houve_alteracao = False

        for idx, caminho in enumerate(atalhos):
            nomes_possiveis = self._nomes_processo_do_atalho(caminho)
            if any(nome.lower() in nomes_rodando for nome in nomes_possiveis):
                self.atalhos_store.incrementar_tempo(caminho, delta)
                houve_alteracao = True
                if self.atalho_atual_idx == idx:
                    segundos = self.atalhos_store.segundos_uso(caminho)
                    self.atualizar_label_tempo(segundos)

        if houve_alteracao:
            self.atalhos_store.salvar_tempos()

    def _nomes_processo_do_atalho(self, caminho):
        if not caminho:
            return []
        caminho_normalizado = os.path.normpath(caminho).lower()
        if caminho_normalizado in self._nomes_processo_cache:
            return self._nomes_processo_cache[caminho_normalizado]

        nomes = []
        base = os.path.basename(caminho)
        nome_base, ext = os.path.splitext(base)

        if ext.lower() == ".exe":
            nomes.append(base.lower())
        elif ext.lower() == ".lnk":
            nomes.append(nome_base.lower() + ".exe")
            try:
                cmd = f'(New-Object -COM WScript.Shell).CreateShortcut("{caminho}").TargetPath'
                res = subprocess.check_output(["powershell", "-NoProfile", "-Command", cmd], text=True, timeout=2).strip()
                if res and res.lower().endswith(".exe"):
                    nomes.append(os.path.basename(res).lower())
            except Exception:
                pass
        else:
            nomes.append(base.lower())

        nomes = list(set(nomes))
        self._nomes_processo_cache[caminho_normalizado] = nomes
        return nomes

    def _obter_area_segura(self):
        area = self.page.property("mussas_safe_area")
        if area is None:
            margem = getattr(config_app, "margem_area_icones", 14)
            area = QRect(margem, margem, 150 - margem * 2, 150 - margem * 2)
        elif isinstance(area, (tuple, list)):
            area = QRect(*area)
        return area

    def _ajustar_geometria_atalhos(self):
        area = self._obter_area_segura()
        self.scroll_atalhos.setGeometry(0, 0, area.width(), area.height())
        if self.stacked_atalhos.currentIndex() == 1:
            self.stacked_atalhos.setGeometry(0, 0, 150, 150)
            self.page.clearMask()
        else:
            self.stacked_atalhos.setGeometry(area)
            self.page.setMask(QRegion(area))

    def ao_mudar_area_pagina(self, area):
        if isinstance(area, (tuple, list)):
            rect = QRect(*area)
        else:
            rect = area
        self.page.setProperty("mussas_safe_area", rect)
        self._ajustar_geometria_atalhos()
        self.atualizar_botoes_atalhos()

    def ao_aplicar_tema(self):
        bg_btn, bg_hover = self.app.cores_botoes()
        cor_texto = self.app.cor_texto
        borda_cor = self.app.borda_cor
        esp_borda = self.app.esp_borda

        self.lbl_nome_atalho.atualizar_estilo(aplicar_css_fonte_base("lista"), cor_texto, borda_cor, esp_borda)
        if self.atalho_atual_idx is not None:
            self.lbl_nome_atalho.ajustar_para_largura(LARGURA_NOME_ATALHO, max_linhas=2)
        self.lbl_tempo_atalho.atualizar_estilo(aplicar_css_fonte_base("nome"), cor_texto, borda_cor, esp_borda)

        self.aplicar_estilos_aos_botoes_atalho()

    def aplicar_estilos_aos_botoes_atalho(self):
        bg_btn, bg_hover = self.app.cores_botoes()
        cor_texto = self.app.cor_texto
        estilo_atalhos = f"QPushButton {{ background-color: {bg_btn}; border-radius: 12px; color: {cor_texto}; font-weight: bold; font-size: 18px; border: none; }} QPushButton:hover {{ background-color: {bg_hover}; }}"
        for i in range(self.layout_atalhos.count()):
            item = self.layout_atalhos.itemAt(i)
            if item:
                widget = item.widget()
                if widget:
                    widget.setStyleSheet(estilo_atalhos)

        estilo_neutro = f"QPushButton {{ background-color: {bg_btn}; border-radius: 6px; color: {cor_texto}; font-weight: bold; font-size: 14px; border: none; }} QPushButton:hover {{ background-color: {bg_hover}; }}"
        estilo_apagar = f"QPushButton {{ background-color: {bg_btn}; border-radius: 6px; color: {cor_texto}; font-size: 12px; border: none; }} QPushButton:hover {{ background-color: rgba(255, 60, 60, 180); }}"
        self.btn_voltar_atalho.setStyleSheet(estilo_neutro)
        self.btn_abrir_atalho.setStyleSheet(estilo_neutro.replace("font-size: 14px", "font-size: 11px"))
        self.btn_apagar_atalho.setStyleSheet(estilo_apagar)

    def encerrar(self):
        if hasattr(self, "worker_processos") and self.worker_processos is not None:
            self.worker_processos.parar()
            self.worker_processos.wait(2000)
        self.atalhos_store.salvar_tempos()
        return True
