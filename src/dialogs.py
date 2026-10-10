import os
import sys
from collections.abc import Callable
from datetime import date
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QCheckBox, QLabel, QSlider, QHBoxLayout, 
    QPushButton, QComboBox, QWidget, QStackedWidget, QGridLayout, QScrollArea,
    QApplication, QMessageBox, QInputDialog, QTabWidget, QStyle, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QEvent, QPoint, QRect, QTimer
from PyQt6.QtGui import QColor, QPainter, QFont, QPixmap, QPainterPath

from vidro import atualizar_vidro, esconder_vidro
from config import (
    config_app, APP_VERSION, PASTA_WALLPAPERS, 
    NIVEIS_DESFOQUE, NIVEIS_ESPESSURA, indice_desfoque, indice_espessura,
    MARGEM_SEGURANCA_BOLINHAS, TEMAS
)
from utils import (
    raio_desfoque, normalizar_cor_hex, aplicar_css_fonte_base, alpha_desfoque,
    versao_tuple
)
from ui_components import BlurredBackgroundFrame, OutlineLabel, ClickableMes, ClickableLabel, MarqueeLabel, WrapLabel
from gerenciador_modulos import PASTA_MODULOS, estado_modulo
from workers import WorkerModulosGitHub


class PreviewBolinhas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.posicao = "baixo"
        self.modo_claro = False
        self.estilo = "bolinhas"
        self.setGeometry(parent.rect())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet("background: transparent;")

    def set_preferencias(self, posicao, modo_claro, estilo="bolinhas"):
        self.posicao = posicao
        self.modo_claro = modo_claro
        self.estilo = estilo
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        escala = min(self.width(), self.height()) / 150
        tamanho = max(6, round(18 * escala))
        margem = round(MARGEM_SEGURANCA_BOLINHAS * escala)
        fundo = QColor("#202124") if self.modo_claro else QColor("#ffffff")
        fundo.setAlpha(204)
        texto = QColor("#ffffff") if self.modo_claro else QColor("#111111")
        if self.estilo == "numeros":
            dimensao = tamanho
            espacamento = 0
        else:
            dimensao = max(3, round(6 * escala))
            espacamento = max(1, round(8 * escala))
        total = dimensao * (1 if self.estilo == "numeros" else 3)
        if self.estilo == "bolinhas":
            total += espacamento * 2
        inicio = (self.width() - total) // 2
        for indice in range(1 if self.estilo == "numeros" else 3):
            if self.posicao in ("baixo", "cima"):
                x = inicio + indice * (dimensao + espacamento)
                y = round(4 * escala) if self.posicao == "cima" else self.height() - margem - dimensao
            else:
                x = round(4 * escala) if self.posicao == "esquerda" else self.width() - margem - dimensao
                y = inicio + indice * (dimensao + espacamento)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fundo if self.estilo == "numeros" or indice == 0 else QColor("#9aa0a6"))
            if self.estilo == "numeros":
                painter.drawEllipse(x, y, dimensao, dimensao)
                painter.setPen(texto)
                painter.setFont(QFont("Segoe UI", max(6, round(8 * escala)), QFont.Weight.Bold))
                painter.drawText(x, y, dimensao, dimensao, Qt.AlignmentFlag.AlignCenter, "1")
            else:
                painter.drawEllipse(x, y, dimensao, dimensao)


class JanelaConfiguracoes(QDialog):
    def __init__(self, parent_widget):
        super().__init__(parent_widget)
        self.parent_widget = parent_widget
        self.setWindowTitle("Configurações")
        self.setFixedWidth(300)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        
        layout = QVBoxLayout(self)
        abas = QTabWidget()
        layout.addWidget(abas)

        pagina_personalizacao = QWidget()
        layout_personalizacao = QVBoxLayout(pagina_personalizacao)
        pagina_gerais = QWidget()
        layout_gerais = QVBoxLayout(pagina_gerais)
        pagina_modulos = QWidget()
        layout_modulos = QVBoxLayout(pagina_modulos)
        
        self.combo_tema = QComboBox()
        for chave, (nome, _, _) in TEMAS.items():
            self.combo_tema.addItem(nome, chave)
        self.combo_tema.setCurrentIndex(max(0, self.combo_tema.findData(config_app.tema)))
        
        self.check_vidro = QCheckBox("Vidro desfocado (desfoca o fundo do desktop)")
        self.check_vidro.setChecked(config_app.vidro_desfocado)

        self.check_windows = QCheckBox("Iniciar junto com o Windows")
        self.check_windows.setChecked(config_app.iniciar_com_windows)
        
        self.check_plano = QCheckBox("Ao fechar, manter em 2º plano")
        self.check_plano.setChecked(config_app.segundo_plano)
        
        self.check_topo = QCheckBox("Sempre no topo")
        self.check_topo.setChecked(config_app.sempre_no_topo)

        self.check_tempo_atalhos = QCheckBox("Contabilizar tempo dos atalhos")
        self.check_tempo_atalhos.setChecked(config_app.monitorar_tempo_atalhos)

        self.check_voltar_principal = QCheckBox("Voltar pra pagina principal após 15 segundos")
        self.check_voltar_principal.setChecked(config_app.voltar_pagina_principal)

        self.combo_pagina_principal = QComboBox()
        for nome_pagina, chave_pagina in self.parent_widget.paginas_disponiveis():
            self.combo_pagina_principal.addItem(nome_pagina, chave_pagina)
        indice_principal = self.combo_pagina_principal.findData(config_app.pagina_principal)
        self.combo_pagina_principal.setCurrentIndex(max(0, indice_principal))

        self.combo_posicao_bolinhas = QComboBox()
        for rotulo, valor in (("Embaixo", "baixo"), ("Em cima", "cima"),
                              ("À direita", "direita"), ("À esquerda", "esquerda")):
            self.combo_posicao_bolinhas.addItem(rotulo, valor)
        indice_posicao = self.combo_posicao_bolinhas.findData(config_app.posicao_bolinhas)
        self.combo_posicao_bolinhas.setCurrentIndex(max(0, indice_posicao))
        self.combo_estilo_indicador = QComboBox()
        self.combo_estilo_indicador.addItem("Bolinhas", "bolinhas")
        self.combo_estilo_indicador.addItem("Números", "numeros")
        indice_estilo = self.combo_estilo_indicador.findData(config_app.indicador_pagina)
        self.combo_estilo_indicador.setCurrentIndex(max(0, indice_estilo))

        self.lbl_tempo_parabens = QLabel()
        self.slider_tempo_parabens = QSlider(Qt.Orientation.Horizontal)
        self.slider_tempo_parabens.setRange(10, 20)
        self.slider_tempo_parabens.setValue(config_app.tempo_parabens)
        self.slider_tempo_parabens.valueChanged.connect(self.atualizar_label_tempo_parabens)
        self.atualizar_label_tempo_parabens()

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
        self.preview_bolinhas = PreviewBolinhas(self.preview_frame)
        self.preview_bolinhas.set_preferencias(
            self.combo_posicao_bolinhas.currentData(), TEMAS[self.combo_tema.currentData()][1],
            self.combo_estilo_indicador.currentData(),
        )
        self.preview_bolinhas.raise_()
        
        self.lbl_versao = QLabel(f"Versão atual: {APP_VERSION}")
        self.lbl_versao.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_update = QPushButton("Verificar Atualizações")
        self.btn_update.clicked.connect(lambda: self.parent_widget.verificar_atualizacoes(manual=True))

        layout_topo_modulos = QHBoxLayout()
        self.lbl_status_modulos = QLabel("Carregando módulos do GitHub...")
        self.btn_atualizar_lista_modulos = QPushButton("Atualizar lista")
        self.btn_abrir_pasta_modulos = QPushButton("Abrir pasta")
        self.btn_abrir_pasta_modulos.clicked.connect(self.abrir_pasta_modulos)
        layout_topo_modulos.addWidget(self.lbl_status_modulos, 1)
        layout_topo_modulos.addWidget(self.btn_atualizar_lista_modulos)
        layout_topo_modulos.addWidget(self.btn_abrir_pasta_modulos)
        self.scroll_modulos = QScrollArea()
        self.scroll_modulos.setWidgetResizable(True)
        self.conteudo_modulos = QWidget()
        self.layout_lista_modulos = QVBoxLayout(self.conteudo_modulos)
        self.layout_lista_modulos.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_modulos.setWidget(self.conteudo_modulos)
        layout_modulos.addLayout(layout_topo_modulos)
        layout_modulos.addWidget(self.scroll_modulos)
        self._botoes_modulos = {}
        self._worker_modulos = None
        self._operacao_modulos = "listar"
        self.btn_atualizar_lista_modulos.clicked.connect(self.atualizar_lista_modulos)
        
        layout_personalizacao.addWidget(QLabel("Tema:"))
        layout_personalizacao.addWidget(self.combo_tema)
        layout_personalizacao.addWidget(self.check_vidro)
        layout_personalizacao.addSpacing(6)
        layout_personalizacao.addLayout(layout_wp_top)
        layout_personalizacao.addWidget(self.combo_wp)
        layout_personalizacao.addWidget(self.lbl_blur)
        layout_personalizacao.addWidget(self.slider_blur)
        layout_personalizacao.addWidget(self.lbl_espessura)
        layout_personalizacao.addWidget(self.slider_esp)
        layout_personalizacao.addWidget(QLabel("Estilo do indicador de página:"))
        layout_personalizacao.addWidget(self.combo_estilo_indicador)
        layout_personalizacao.addWidget(QLabel("Posição do indicador de página:"))
        layout_personalizacao.addWidget(self.combo_posicao_bolinhas)
        layout_personalizacao.addWidget(self.preview_frame, alignment=Qt.AlignmentFlag.AlignCenter)
        layout_personalizacao.addStretch()

        layout_gerais.addWidget(self.check_windows)
        layout_gerais.addWidget(self.check_plano)
        layout_gerais.addWidget(self.check_topo)
        layout_gerais.addWidget(self.check_tempo_atalhos)
        layout_gerais.addWidget(self.check_voltar_principal)
        layout_gerais.addWidget(QLabel("Página principal:"))
        layout_gerais.addWidget(self.combo_pagina_principal)
        layout_gerais.addWidget(self.lbl_tempo_parabens)
        layout_gerais.addWidget(self.slider_tempo_parabens)
        layout_gerais.addStretch()
        layout_gerais.addWidget(self.lbl_versao)
        layout_gerais.addWidget(self.btn_update)

        abas.addTab(pagina_personalizacao, "Personalização")
        abas.addTab(pagina_gerais, "Gerais")
        abas.addTab(pagina_modulos, "Módulos")
        
        self.combo_tema.currentIndexChanged.connect(self.atualizar_preview)
        self.combo_tema.currentIndexChanged.connect(self.atualizar_preview_bolinhas)
        self.combo_posicao_bolinhas.currentIndexChanged.connect(self.atualizar_posicao_bolinhas)
        self.combo_estilo_indicador.currentIndexChanged.connect(self.atualizar_estilo_indicador)
        self.combo_wp.currentTextChanged.connect(self.atualizar_preview)
        self.slider_blur.valueChanged.connect(self.atualizar_preview)
        self.slider_esp.valueChanged.connect(self.atualizar_preview)
        
        self.atualizar_preview()
        self.atualizar_preview_bolinhas()
        self.atualizar_lista_modulos()

    def atualizar_preview_bolinhas(self):
        self.preview_bolinhas.set_preferencias(
            self.combo_posicao_bolinhas.currentData(), TEMAS[self.combo_tema.currentData()][1],
            self.combo_estilo_indicador.currentData(),
        )

    def atualizar_estilo_indicador(self):
        config_app.indicador_pagina = self.combo_estilo_indicador.currentData()
        self.preview_bolinhas.set_preferencias(
            self.combo_posicao_bolinhas.currentData(), TEMAS[self.combo_tema.currentData()][1],
            config_app.indicador_pagina,
        )
        self.parent_widget._criar_dots_pagina()

    def atualizar_posicao_bolinhas(self):
        config_app.posicao_bolinhas = self.combo_posicao_bolinhas.currentData()
        config_app.indicador_pagina = self.combo_estilo_indicador.currentData()
        self.atualizar_preview_bolinhas()
        self.parent_widget._criar_dots_pagina()

    def atualizar_lista_modulos(self):
        if self._worker_modulos is not None and self._worker_modulos.isRunning():
            return
        self._operacao_modulos = "listar"
        self.lbl_status_modulos.setText("Consultando GitHub...")
        self.btn_atualizar_lista_modulos.setEnabled(False)
        self._iniciar_worker_modulos()

    def baixar_modulo(self, modulo):
        if self._worker_modulos is not None and self._worker_modulos.isRunning():
            return
        nome = modulo["nome"]
        self._operacao_modulos = "baixar"
        self.lbl_status_modulos.setText(f"Baixando {os.path.splitext(nome)[0]}...")
        self._definir_botoes_modulos_habilitados(False)
        self.btn_atualizar_lista_modulos.setEnabled(False)
        self._iniciar_worker_modulos(nome, modulo["url"], "baixar")

    def _iniciar_worker_modulos(self, nome=None, url=None, acao=None):
        self._worker_modulos = WorkerModulosGitHub(nome, url, acao, self)
        self._worker_modulos.resultado.connect(self._resultado_modulos)
        self._worker_modulos.erro.connect(self._erro_modulos)
        self._worker_modulos.finished.connect(self._finalizar_worker_modulos)
        self._worker_modulos.start()

    def _resultado_modulos(self, resultado):
        if self._operacao_modulos == "listar":
            self._exibir_modulos(resultado)
            self.lbl_status_modulos.setText(f"{len(resultado)} módulo(s) disponível(is)")
            return

        nome = resultado["nome"]
        acao = resultado["acao"]
        gerenciador = self.parent_widget.gerenciador_modulos
        if acao in ("baixar", "ativar"):
            if not gerenciador.ativar_modulo(nome):
                detalhe = gerenciador.ultimo_erro_ativacao
                texto_erro = f"Não foi possível carregar {os.path.splitext(nome)[0]}."
                if detalhe:
                    texto_erro += f"\n\nDetalhes: {detalhe}"
                QMessageBox.warning(
                    self, "Módulos", texto_erro
                )
        else:
            gerenciador.desativar_modulo(nome)
            if acao == "excluir":
                self._modulos_remotos = [
                    modulo for modulo in self._modulos_remotos
                    if modulo["nome"].casefold() != nome.casefold()
                    or modulo.get("url") is not None
                ]
        self._atualizar_paginas_principais()
        self._exibir_modulos(self._modulos_remotos)
        self.lbl_status_modulos.setText(f"{len(self._modulos_remotos)} módulo(s) disponível(is)")

    def _atualizar_paginas_principais(self):
        selecao = self.combo_pagina_principal.currentData()
        self.combo_pagina_principal.clear()
        for nome_pagina, chave_pagina in self.parent_widget.paginas_disponiveis():
            self.combo_pagina_principal.addItem(nome_pagina, chave_pagina)
        indice = self.combo_pagina_principal.findData(selecao)
        if indice < 0:
            indice = self.combo_pagina_principal.findData(config_app.pagina_principal)
        self.combo_pagina_principal.setCurrentIndex(max(0, indice))

    def _erro_modulos(self, mensagem):
        self.lbl_status_modulos.setText("Não foi possível concluir a operação.")
        if self._operacao_modulos != "listar":
            self._exibir_modulos(self._modulos_remotos)
        QMessageBox.warning(self, "Módulos do GitHub", mensagem)

    def _finalizar_worker_modulos(self):
        self.btn_atualizar_lista_modulos.setEnabled(True)
        self._definir_botoes_modulos_habilitados(True)
        self._worker_modulos = None

    def _definir_botoes_modulos_habilitados(self, habilitado):
        for acoes in self._botoes_modulos.values():
            for controle in acoes:
                controle.setEnabled(
                    habilitado and not controle.property("desabilitado_por_estado")
                )

    def abrir_pasta_modulos(self):
        os.startfile(PASTA_MODULOS)

    def _exibir_modulos(self, modulos):
        self._modulos_remotos = modulos
        while self.layout_lista_modulos.count():
            item = self.layout_lista_modulos.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._botoes_modulos.clear()

        if not modulos:
            self.layout_lista_modulos.addWidget(QLabel("Nenhum arquivo .py encontrado na pasta Modulos."))
            return

        for modulo in modulos:
            linha = QWidget()
            layout_linha = QHBoxLayout(linha)
            layout_linha.setContentsMargins(0, 4, 0, 4)
            nome = modulo["nome"]
            nome_exibicao = os.path.splitext(nome)[0]
            versao = modulo.get("versao")
            if versao and versao_tuple(versao) < (1, 0, 0):
                nome_exibicao += "-BETA"
            rotulo = QLabel(nome_exibicao)
            layout_linha.addWidget(rotulo, 1)
            estado = estado_modulo(nome)
            acoes = []
            check_ativo = QCheckBox()
            check_ativo.setChecked(estado == "ativo")
            check_ativo.setToolTip("Módulo ativo" if estado == "ativo" else "Ativar módulo")
            check_ativo.setProperty("desabilitado_por_estado", estado == "nao_instalado")
            check_ativo.setEnabled(estado != "nao_instalado")
            check_ativo.toggled.connect(
                lambda ativo, item=modulo:
                self.alterar_modulo(item, "ativar" if ativo else "desativar")
            )
            layout_linha.addWidget(check_ativo)
            acoes.append(check_ativo)

            botao_acao = QPushButton()
            botao_acao.setFixedSize(26, 26)
            if estado == "nao_instalado" and modulo.get("url"):
                botao_acao.setIcon(
                    self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown)
                )
                botao_acao.setToolTip("Baixar módulo")
                botao_acao.clicked.connect(
                    lambda checked=False, item=modulo: self.baixar_modulo(item)
                )
            elif estado != "nao_instalado":
                botao_acao.setIcon(
                    self.style().standardIcon(QStyle.StandardPixmap.SP_DialogCloseButton)
                )
                botao_acao.setToolTip("Excluir módulo")
                botao_acao.clicked.connect(
                    lambda checked=False, item=modulo: self.alterar_modulo(item, "excluir")
                )
            else:
                botao_acao.setEnabled(False)
                botao_acao.setToolTip("Arquivo local indisponível")
            acoes.append(botao_acao)
            layout_linha.addWidget(botao_acao)

            if self.parent_widget.gerenciador_modulos.modulo_tem_configuracoes(nome):
                botao_config = QPushButton("⚙")
                botao_config.setFixedSize(26, 26)
                botao_config.setToolTip("Configurar módulo")
                botao_config.setProperty(
                    "desabilitado_por_estado", estado != "ativo"
                )
                botao_config.setEnabled(estado == "ativo")
                botao_config.clicked.connect(
                    lambda checked=False, item=modulo:
                    self.abrir_configuracoes_modulo(item)
                )
                acoes.append(botao_config)
                layout_linha.addWidget(botao_config)

            self.layout_lista_modulos.addWidget(linha)
            self._botoes_modulos[nome] = acoes

    def abrir_configuracoes_modulo(self, modulo):
        gerenciador = self.parent_widget.gerenciador_modulos
        try:
            abriu = gerenciador.abrir_configuracoes_modulo(
                modulo["nome"], self
            )
            if not abriu:
                QMessageBox.warning(
                    self,
                    "Configurações do módulo",
                    "Ative o módulo para abrir suas configurações.",
                )
        except Exception as erro:
            QMessageBox.warning(
                self,
                "Configurações do módulo",
                f"Não foi possível abrir as configurações:\n{erro}",
            )

    def alterar_modulo(self, modulo, acao):
        if self._worker_modulos is not None and self._worker_modulos.isRunning():
            return
        nome = modulo["nome"]
        if acao == "excluir":
            resposta = QMessageBox.question(
                self,
                "Excluir módulo",
                f"Deseja excluir o módulo {os.path.splitext(nome)[0]}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if resposta != QMessageBox.StandardButton.Yes:
                return
        rotulo = os.path.splitext(nome)[0]
        self._operacao_modulos = acao
        self.lbl_status_modulos.setText(f"{acao.capitalize()} {rotulo}...")
        self._definir_botoes_modulos_habilitados(False)
        self.btn_atualizar_lista_modulos.setEnabled(False)
        self._iniciar_worker_modulos(nome, modulo.get("url"), acao)

    def atualizar_label_tempo_parabens(self):
        self.lbl_tempo_parabens.setText(f"Duração da tela de Parabéns: {self.slider_tempo_parabens.value()}s")

    def atualizar_preview(self):
        claro = TEMAS[self.combo_tema.currentData()][1]
        cor_base = TEMAS[self.combo_tema.currentData()][2]
        wp_nome = self.combo_wp.currentText()
        wp_path = os.path.join(PASTA_WALLPAPERS, wp_nome) if wp_nome != "Nenhum" else "Nenhum"
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
            overlay = (0, 0, 0, 0)
            border = (0, 0, 0, 0)
        self.preview_frame.update_background(wp_path, raio_desfoque(blur_percent), overlay, border, 12, modo_claro=claro, cor_base=cor_base)
        if not tem_wp:
            fundo_preview = QColor(self.preview_frame.overlay_color)
            fundo_preview.setAlpha(255)
            self.preview_frame.overlay_color = fundo_preview
            self.preview_frame.update()

    def closeEvent(self, event):
        config_app.definir_tema(self.combo_tema.currentData())
        config_app.iniciar_com_windows = self.check_windows.isChecked()
        config_app.segundo_plano = self.check_plano.isChecked()
        config_app.sempre_no_topo = self.check_topo.isChecked()
        config_app.monitorar_tempo_atalhos = self.check_tempo_atalhos.isChecked()
        config_app.voltar_pagina_principal = self.check_voltar_principal.isChecked()
        config_app.tempo_parabens = self.slider_tempo_parabens.value()
        config_app.pagina_principal = self.combo_pagina_principal.currentData()
        config_app.posicao_bolinhas = self.combo_posicao_bolinhas.currentData()
        config_app.wallpaper = self.combo_wp.currentText()
        config_app.desfoque = NIVEIS_DESFOQUE[self.slider_blur.value()]
        config_app.espessura_borda = NIVEIS_ESPESSURA[self.slider_esp.value()]
        config_app.vidro_desfocado = self.check_vidro.isChecked()
        config_app.salvar()
        config_app.aplicar_registro_windows()

        self.parent_widget.aplicar_sempre_no_topo()
        self.parent_widget.aplicar_tema()
        self.parent_widget._criar_dots_pagina()
        pagina_principal = self.parent_widget._indice_pagina_principal()
        if config_app.voltar_pagina_principal and self.parent_widget.pagina_atual != pagina_principal:
            self.parent_widget.timer_inatividade.start(15000)
        else:
            self.parent_widget.timer_inatividade.stop()


LARGURA_ITEM_LISTA = 122

ESTILO_SCROLL_LIMPO = (
    "QScrollArea { background: transparent; border: none; }"
    "QScrollBar:vertical { background: transparent; width: 4px; margin: 2px 0; border: none; }"
    "QScrollBar::handle:vertical { background: rgba(160, 160, 160, 120); border-radius: 2px; min-height: 20px; }"
    "QScrollBar::handle:vertical:hover { background: rgba(200, 200, 200, 180); }"
    "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; background: none; border: none; }"
    "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
)


class PaginaDetalheEvento(QWidget):
    """Página de detalhe com a imagem cobrindo toda a área."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = QPixmap()

    def definir_imagem(self, pixmap):
        self._pixmap = pixmap
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        caminho = QPainterPath()
        caminho.addRoundedRect(0, 0, self.width(), self.height(), 12, 12)
        painter.setClipPath(caminho)
        if self._pixmap.isNull():
            return
        escalada = self._pixmap.scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (self.width() - escalada.width()) // 2
        y = (self.height() - escalada.height()) // 2
        painter.drawPixmap(x, y, escalada)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 90))


class JanelaCalendario(QWidget):
    def __init__(
        self,
        reiniciar_timer: Callable[[], None],
        adicionar_evento: Callable[[int], None] | None = None,
        excluir_evento: Callable[[str], bool] | None = None,
    ):
        super().__init__()
        self._reiniciar_timer = reiniciar_timer
        self._adicionar_evento = adicionar_evento
        self._excluir_evento = excluir_evento
        self._referencia_widget = None
        self._timer_reposicionar = QTimer(self)
        self._timer_reposicionar.setSingleShot(True)
        self._timer_reposicionar.setInterval(40)
        self._timer_reposicionar.timeout.connect(self._reposicionar_na_referencia)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(150)
        self._altura_preferida = 140
        
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
        espaco_esquerdo = QWidget()
        espaco_esquerdo.setFixedSize(24, 24)
        top_list.addWidget(espaco_esquerdo)
        self.lbl_titulo_mes = OutlineLabel("Mês")
        self.lbl_titulo_mes.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_list.addWidget(self.lbl_titulo_mes, 1)
        self.btn_adicionar_evento = QPushButton("+")
        self.btn_adicionar_evento.setFixedSize(24, 24)
        self.btn_adicionar_evento.setToolTip("Adicionar evento neste mês")
        self.btn_adicionar_evento.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_adicionar_evento.setStyleSheet(
            "QPushButton { background: rgba(120, 120, 120, 80); border: none; border-radius: 6px; }"
            "QPushButton:hover { background: rgba(120, 120, 120, 150); }"
        )
        self.btn_adicionar_evento.clicked.connect(self._pedir_adicao_evento)
        self.btn_adicionar_evento.setVisible(adicionar_evento is not None)
        top_list.addWidget(self.btn_adicionar_evento)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet(ESTILO_SCROLL_LIMPO)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent;")
        self.layout_nomes = QVBoxLayout(self.scroll_content)
        self.layout_nomes.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.scroll.setWidget(self.scroll_content)

        for widget in (self.page_grid, self.page_list, self.lbl_titulo_mes, self.scroll, self.scroll.viewport(), self.scroll_content):
            widget.installEventFilter(self)
        for lbl in self.labels_meses:
            lbl.installEventFilter(self)
        
        layout_list.addLayout(top_list)
        layout_list.addWidget(self.scroll)

        self.page_detalhe = PaginaDetalheEvento()
        layout_detalhe = QVBoxLayout(self.page_detalhe)
        layout_detalhe.setContentsMargins(5, 5, 5, 5)
        topo_detalhe = QHBoxLayout()
        topo_detalhe.setContentsMargins(0, 0, 0, 0)
        self.btn_voltar_evento = QPushButton("‹")
        self.btn_voltar_evento.setFixedSize(24, 24)
        self.btn_voltar_evento.clicked.connect(lambda: self.stacked.setCurrentIndex(1))
        self.lbl_titulo_evento = WrapLabel("")
        self.lbl_titulo_evento.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_excluir_evento = QPushButton("−")
        self.btn_excluir_evento.setFixedSize(24, 24)
        self.btn_excluir_evento.setToolTip("Excluir este evento")
        self.btn_excluir_evento.clicked.connect(self._pedir_exclusao_evento)
        for botao in (self.btn_voltar_evento, self.btn_excluir_evento):
            botao.setCursor(Qt.CursorShape.PointingHandCursor)
            botao.setStyleSheet(
                "QPushButton { background: rgba(120, 120, 120, 80); border: none; border-radius: 6px; }"
                "QPushButton:hover { background: rgba(180, 35, 35, 150); }"
            )
        topo_detalhe.addWidget(self.btn_voltar_evento)
        topo_detalhe.addStretch(1)
        topo_detalhe.addWidget(self.btn_excluir_evento)
        self.lbl_dias_evento = OutlineLabel("")
        self.lbl_dias_evento.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout_detalhe.addLayout(topo_detalhe)
        layout_detalhe.addWidget(self.lbl_titulo_evento, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout_detalhe.addStretch(1)
        layout_detalhe.addWidget(self.lbl_dias_evento)
        layout_detalhe.addStretch(1)

        self.stacked.addWidget(self.page_grid)
        self.stacked.addWidget(self.page_list)
        self.stacked.addWidget(self.page_detalhe)
        self.resize(150, 140)

        self.dados = []
        self.cor_texto = "#ffffff"
        self.borda_cor = None
        self.esp_borda = 0

    def abrir_mes(self, mes_num):
        self._mes_atual = mes_num
        for i in reversed(range(self.layout_nomes.count())): 
            item = self.layout_nomes.takeAt(i)
            widget = item.widget()
            if widget:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
            
        aniversariantes = []
        for item in self.dados:
            try:
                nome, data_str = item[0], item[1]
                cor_nome = item[2] if len(item) >= 3 else "#ffffff"
                partes = str(data_str).split('/')
                d, m = int(partes[0]), int(partes[1])
                if m == mes_num:
                    imagem = item[3] if len(item) >= 4 else ""
                    recorrente = bool(item[4]) if len(item) >= 5 else True
                    event_id = str(item[5]) if len(item) >= 6 and item[5] else ""
                    aniversariantes.append((
                        nome, d, normalizar_cor_hex(cor_nome), imagem,
                        recorrente, data_str, event_id,
                    ))
            except Exception:
                pass
            
        aniversariantes.sort(key=lambda x: x[1])
        self.lbl_titulo_mes.setText(f"{self.meses_nomes[mes_num-1]}")
        self.lbl_titulo_mes.atualizar_estilo(aplicar_css_fonte_base("cal_titulo"), self.cor_texto, self.borda_cor, self.esp_borda)
        
        if not aniversariantes:
            vazio = OutlineLabel("Sem aniversários")
            vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vazio.atualizar_estilo(aplicar_css_fonte_base("cal_lista"), self.cor_texto, self.borda_cor, self.esp_borda)
            self.layout_nomes.addWidget(vazio, alignment=Qt.AlignmentFlag.AlignHCenter)
            vazio.installEventFilter(self)
        else:
            for nome, dia, cor, imagem, recorrente, data_str, event_id in aniversariantes:
                if event_id:
                    botao = MarqueeLabel(f"{nome} - {dia}", clicavel=True)
                    botao.setFixedSize(LARGURA_ITEM_LISTA, 20)
                    botao.setCursor(Qt.CursorShape.PointingHandCursor)
                    botao.atualizar_estilo(
                        aplicar_css_fonte_base("cal_lista"), cor, self.borda_cor, self.esp_borda
                    )
                    botao.clicked.connect(
                        lambda checked=False, evento=(
                            nome, data_str, cor, imagem, recorrente, event_id
                        ): self.mostrar_detalhe_evento(evento)
                    )
                    self.layout_nomes.addWidget(botao, alignment=Qt.AlignmentFlag.AlignHCenter)
                else:
                    rotulo = MarqueeLabel(f"{nome} - {dia}")
                    rotulo.setFixedSize(LARGURA_ITEM_LISTA, 20)
                    rotulo.atualizar_estilo(
                        aplicar_css_fonte_base("cal_lista"), cor, self.borda_cor, self.esp_borda
                    )
                    self.layout_nomes.addWidget(rotulo, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.stacked.setCurrentIndex(1)
        self._reiniciar_timer()

    def _pedir_adicao_evento(self):
        if self._adicionar_evento is not None and self.stacked.currentIndex() == 1:
            self._adicionar_evento(self._mes_atual)

    def mostrar_detalhe_evento(self, evento):
        nome, data_str, cor, imagem, recorrente, event_id = evento
        self.lbl_titulo_evento.setText(nome)
        self.lbl_titulo_evento.atualizar_estilo(
            aplicar_css_fonte_base("cal_titulo"), cor, self.borda_cor, self.esp_borda
        )
        partes = str(data_str).split("/")
        dia, mes = int(partes[0]), int(partes[1])
        ano = int(partes[2]) if len(partes) > 2 else None
        hoje = date.today()
        if recorrente or ano is None:
            proximo = None
            for candidato_ano in range(hoje.year, hoje.year + 9):
                try:
                    candidato = date(candidato_ano, mes, dia)
                except ValueError:
                    continue
                if candidato >= hoje:
                    proximo = candidato
                    break
            dias = (proximo - hoje).days if proximo else None
        else:
            try:
                data_evento = date(ano, mes, dia)
                dias = (data_evento - hoje).days
            except ValueError:
                dias = None
        self.lbl_dias_evento.setText(
            "Data inválida" if dias is None else
            ("Evento já passou" if dias < 0 else
             ("Hoje" if dias == 0 else f"Faltam {dias} dias"))
        )
        self.lbl_dias_evento.atualizar_estilo(
            aplicar_css_fonte_base("cal_lista"), self.cor_texto, self.borda_cor, self.esp_borda
        )
        pixmap = QPixmap(imagem) if imagem and os.path.isfile(imagem) else QPixmap()
        self.page_detalhe.definir_imagem(pixmap)
        cor_titulo = '#ffffff' if not pixmap.isNull() else cor
        self.lbl_titulo_evento.atualizar_estilo(aplicar_css_fonte_base('cal_titulo'), cor_titulo, self.borda_cor, self.esp_borda)
        if not pixmap.isNull():
            self.lbl_dias_evento.atualizar_estilo(aplicar_css_fonte_base('cal_lista'), '#ffffff', self.borda_cor, self.esp_borda)
        self.lbl_titulo_evento.ajustar_para_largura(140)
        self._evento_selecionado_id = event_id
        self.btn_excluir_evento.setVisible(bool(event_id and self._excluir_evento))
        self.stacked.setCurrentIndex(2)
        self._reiniciar_timer()

    def _pedir_exclusao_evento(self):
        event_id = getattr(self, "_evento_selecionado_id", "")
        if not event_id or self._excluir_evento is None:
            return
        resposta = QMessageBox.question(
            self, "Excluir evento", "Deseja excluir este evento?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resposta == QMessageBox.StandardButton.Yes and self._excluir_evento(event_id):
            self.abrir_mes(self._mes_atual)

    def set_referencia_widget(self, widget):
        if self._referencia_widget is not None:
            self._referencia_widget.removeEventFilter(self)
        self._referencia_widget = widget
        if widget is not None:
            widget.installEventFilter(self)

    def _reposicionar_na_referencia(self):
        if self._referencia_widget is None or not self.isVisible():
            return
        origem = self._referencia_widget.mapToGlobal(QPoint(0, 0))
        self.ajustar_posicao_ao_espaco(
            QRect(origem.x(), origem.y(), self._referencia_widget.width(), self._referencia_widget.height())
        )

    def ajustar_posicao_ao_espaco(self, referencia):
        if not referencia:
            return
        tela_principal = QApplication.screenAt(referencia.center()) or QApplication.primaryScreen()
        if tela_principal is None:
            return
        tela = tela_principal.availableGeometry()
        margem = 6
        espacamento = 4
        largura = self.width()
        abaixo = referencia.bottom() + 1 + espacamento
        espaco_abaixo = tela.bottom() + 1 - margem - abaixo
        espaco_acima = referencia.top() - espacamento - (tela.top() + margem)
        if max(espaco_abaixo, espaco_acima) >= self._altura_preferida:
            altura = self._altura_preferida
        else:
            altura = max(40, min(self._altura_preferida, max(espaco_abaixo, espaco_acima)))
        if self.height() != altura:
            self.setFixedHeight(altura)
            self.container.setGeometry(0, 0, largura, altura)
            self.stacked.setGeometry(0, 0, largura, altura)
        acima = referencia.top() - altura - espacamento
        if espaco_abaixo >= altura:
            topo = abaixo
        elif espaco_acima >= altura:
            topo = acima
        else:
            if espaco_abaixo >= espaco_acima:
                topo = abaixo
            else:
                topo = referencia.top() - espacamento - altura
        topo = max(tela.top() + margem, min(topo, tela.bottom() + 1 - altura - margem))
        esquerda = referencia.center().x() - largura // 2
        esquerda = max(tela.left() + margem, min(esquerda, tela.right() + 1 - largura - margem))
        self.setGeometry(esquerda, topo, largura, altura)

    def eventFilter(self, obj, event):
        if obj is self._referencia_widget and event.type() in (
            QEvent.Type.Move, QEvent.Type.Resize,
        ):
            if self.isVisible():
                self._timer_reposicionar.start()
            return False
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self._reiniciar_timer()
            if self.stacked.currentIndex() == 1:
                self.stacked.setCurrentIndex(0)
                return True
        return super().eventFilter(obj, event)

    def atualizar_vidro_calendario(self):
        atualizar_vidro(self, self.container)

    def showEvent(self, event):
        super().showEvent(event)
        self.atualizar_vidro_calendario()

    def moveEvent(self, event):
        super().moveEvent(event)
        if getattr(self, "_vidro", None) is not None and self._vidro.isVisible():
            self.atualizar_vidro_calendario()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, "_vidro", None) is not None and self._vidro.isVisible():
            self.atualizar_vidro_calendario()

    def hideEvent(self, event):
        super().hideEvent(event)
        esconder_vidro(self)

    def atualizar_dados(self, dados, cor_texto, overlay_color, border_color, wp_path, blur, borda_cor=None, esp_borda=0, modo_claro=False, cor_base=None):
        self.dados = dados
        self.cor_texto = cor_texto
        self.borda_cor = borda_cor
        self.esp_borda = esp_borda
        if config_app.vidro_desfocado:
            wp_path = "Nenhum"
        self.container.update_background(wp_path, blur, overlay_color, border_color, 12, modo_claro=modo_claro, cor_base=cor_base)
        if config_app.vidro_desfocado:
            vidro = QColor(self.container.overlay_color)
            vidro.setAlpha(1)
            self.container.overlay_color = vidro
            self.container.update()
        self.atualizar_vidro_calendario()
        
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
        if self.stacked.currentIndex() == 1 and hasattr(self, "_mes_atual"):
            self.abrir_mes(self._mes_atual)
