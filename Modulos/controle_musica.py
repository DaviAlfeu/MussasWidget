import asyncio
import time
from datetime import datetime, timezone

from PyQt6.QtCore import (
    QEvent, QObject, QPoint, QPropertyAnimation, QRectF, QThread, QTimer, Qt, QSize,
    QEasingCurve, pyqtSignal
)
from PyQt6.QtGui import QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QGraphicsOpacityEffect, QHBoxLayout,
    QLabel, QListWidget, QPushButton, QSlider, QStackedWidget, QStyle,
    QVBoxLayout, QWidget
)

from utils import aplicar_css_fonte_base
from gerenciador_modulos import PluginBase
from ui_components import BlurredBackgroundFrame, ClickableLabel

try:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager,
        GlobalSystemMediaTransportControlsSessionPlaybackStatus,
    )
    from winrt.windows.storage.streams import DataReader
except ImportError as erro:
    GlobalSystemMediaTransportControlsSessionManager = None
    GlobalSystemMediaTransportControlsSessionPlaybackStatus = None
    DataReader = None
    ERRO_WINRT = str(erro)
else:
    ERRO_WINRT = ""


class CapaMusicaLabel(ClickableLabel):
    def paintEvent(self, evento):
        pixmap = self.pixmap()
        if pixmap is None or pixmap.isNull():
            super().paintEvent(evento)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        caminho = QPainterPath()
        caminho.addRoundedRect(QRectF(self.rect().adjusted(0, 0, -1, -1)), 8, 8)
        painter.setClipPath(caminho)
        imagem = pixmap.scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation
        )
        x = (imagem.width() - self.width()) // 2
        y = (imagem.height() - self.height()) // 2
        painter.drawPixmap(-x, -y, imagem)


class WorkerSessoesMedia(QThread):
    sessoes_carregadas = pyqtSignal(object)
    estado_carregado = pyqtSignal(object)
    comando_concluido = pyqtSignal(bool)
    erro = pyqtSignal(str)

    def __init__(self, comando=None, chave_sessao=None, valor=None, parent=None):
        super().__init__(parent)
        self.comando = comando
        self.chave_sessao = chave_sessao
        self.valor = valor

    def run(self):
        try:
            resultado = asyncio.run(self._executar())
            if self.comando is None:
                self.sessoes_carregadas.emit(resultado)
            elif self.comando == "estado":
                self.estado_carregado.emit(resultado)
            else:
                self.comando_concluido.emit(resultado)
        except Exception as erro:
            self.erro.emit(str(erro))

    async def _executar(self):
        if GlobalSystemMediaTransportControlsSessionManager is None:
            raise RuntimeError(
                "Os componentes WinRT de mídia não estão instalados: " + ERRO_WINRT
            )

        manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
        sessoes = list(manager.get_sessions())
        if self.comando == "estado":
            sessao = await self._localizar_sessao(sessoes)
            if sessao is None:
                return None
            info_reproducao = sessao.get_playback_info()
            tocando = (
                info_reproducao.playback_status
                == GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING
            )
            linha_tempo = sessao.get_timeline_properties()
            return {
                "tocando": tocando,
                "posicao": self._posicao_linha_tempo(linha_tempo, tocando),
                "capturado_em": time.monotonic(),
                "atualizado_em": linha_tempo.last_updated_time,
            }
        if self.comando is not None:
            sessao_alvo = await self._localizar_sessao(sessoes)
            if sessao_alvo is None:
                return False
            if self.comando == "buscar":
                linha_tempo = sessao_alvo.get_timeline_properties()
                inicio = self._segundos(linha_tempo.start_time)
                minimo = self._segundos(linha_tempo.min_seek_time)
                maximo = self._segundos(linha_tempo.max_seek_time)
                posicao = max(minimo, min(maximo, inicio + int(self.valor)))
                return await sessao_alvo.try_change_playback_position_async(
                    posicao * 10_000_000
                )
            acoes = {
                "alternar": sessao_alvo.try_toggle_play_pause_async,
                "anterior": sessao_alvo.try_skip_previous_async,
                "proxima": sessao_alvo.try_skip_next_async,
                "aleatorio": lambda: sessao_alvo.try_change_shuffle_active_async(
                    bool(self.valor)
                )
            }
            operacao = acoes.get(self.comando)
            return await operacao() if operacao is not None else False

        atual = manager.get_current_session()
        ocorrencias = {}
        registros = []

        for sessao in sessoes:
            try:
                propriedades = await sessao.try_get_media_properties_async()
                fonte = sessao.source_app_user_model_id or "Aplicativo"
                titulo = propriedades.title or "Sem título"
                artista = propriedades.artist or propriedades.album_artist or ""
                base = (fonte, titulo, artista)
                ocorrencia = ocorrencias.get(base, 0)
                ocorrencias[base] = ocorrencia + 1
                chave = base + (ocorrencia,)
                info_reproducao = sessao.get_playback_info()
                controles = info_reproducao.controls
                try:
                    linha_tempo = sessao.get_timeline_properties()
                    inicio = self._segundos(linha_tempo.start_time)
                    fim = self._segundos(linha_tempo.end_time)
                    posicao = self._posicao_linha_tempo(
                        linha_tempo,
                        info_reproducao.playback_status
                        == GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING,
                    )
                    duracao = max(0, fim - inicio)
                    capturado_em = time.monotonic()
                    atualizado_em = linha_tempo.last_updated_time
                    pode_buscar = fim > inicio and (
                        self._segundos(linha_tempo.max_seek_time)
                        > self._segundos(linha_tempo.min_seek_time)
                    )
                except Exception:
                    inicio = 0
                    posicao = 0
                    duracao = 0
                    capturado_em = time.monotonic()
                    atualizado_em = None
                    pode_buscar = False
                identificador = fonte.lower()
                fonte_musical = any(
                    termo in identificador
                    for termo in ("spotify", "youtube", "soundcloud", "chrome", "msedge", "edge")
                )
                imagem = (
                    await self._ler_thumbnail(propriedades.thumbnail)
                    if self.comando is None else b""
                )
                registros.append({
                    "chave": chave,
                    "fonte": fonte,
                    "titulo": titulo,
                    "artista": artista,
                    "imagem": imagem,
                    "tocando": (
                        info_reproducao.playback_status
                        == GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING
                    ),
                    "pode_alternar": controles.is_play_pause_toggle_enabled,
                    "pode_anterior": controles.is_previous_enabled,
                    "pode_proxima": controles.is_next_enabled,
                    "posicao": max(0, posicao),
                    "duracao": duracao,
                    "inicio": inicio,
                    "capturado_em": capturado_em,
                    "atualizado_em": atualizado_em,
                    "pode_buscar": pode_buscar,
                    "pode_aleatorio": (
                        fonte_musical and controles.is_shuffle_enabled
                    ),
                    "aleatorio": info_reproducao.is_shuffle_active,
                    "atual": sessao == atual
                })
            except Exception:
                continue

        return registros

    async def _localizar_sessao(self, sessoes):
        ocorrencias = {}
        for sessao in sessoes:
            try:
                propriedades = await sessao.try_get_media_properties_async()
            except Exception:
                continue
            fonte = sessao.source_app_user_model_id or "Aplicativo"
            titulo = propriedades.title or "Sem título"
            artista = propriedades.artist or propriedades.album_artist or ""
            base = (fonte, titulo, artista)
            ocorrencia = ocorrencias.get(base, 0)
            ocorrencias[base] = ocorrencia + 1
            if base + (ocorrencia,) == self.chave_sessao:
                return sessao
        return None

    @staticmethod
    def _segundos(valor):
        if hasattr(valor, "total_seconds"):
            return int(valor.total_seconds())
        return int(valor / 10_000_000)

    @classmethod
    def _posicao_linha_tempo(cls, linha_tempo, tocando):
        posicao = (
            cls._segundos_precisos(linha_tempo.position)
            - cls._segundos_precisos(linha_tempo.start_time)
        )
        if tocando:
            atualizado_em = linha_tempo.last_updated_time
            segundos_desde_atualizacao = (
                datetime.now(timezone.utc) - atualizado_em
            ).total_seconds()
            posicao += max(0, segundos_desde_atualizacao)
        return max(0, int(posicao))

    @staticmethod
    def _segundos_precisos(valor):
        if hasattr(valor, "total_seconds"):
            return valor.total_seconds()
        return valor / 10_000_000

    async def _ler_thumbnail(self, referencia):
        if referencia is None or DataReader is None:
            return b""
        try:
            stream = await referencia.open_read_async()
            tamanho = min(int(stream.size), 4 * 1024 * 1024)
            if tamanho <= 0:
                return b""
            leitor = DataReader(stream.get_input_stream_at(0))
            await leitor.load_async(tamanho)
            dados = bytearray(tamanho)
            leitor.read_bytes(dados)
            leitor.close()
            stream.close()
            return bytes(dados)
        except Exception:
            return b""


class FiltroJanelaMusica(QObject):
    def __init__(self, plugin):
        super().__init__(plugin.app)
        self.plugin = plugin
        self.playlist_viewport = plugin.lista_playlist.viewport()

    def eventFilter(self, observado, evento):
        plugin = self.plugin
        tipo = evento.type()
        if observado is plugin.app:
            if tipo in (QEvent.Type.Move, QEvent.Type.Resize):
                plugin._posicionar_widgets()
            elif tipo == QEvent.Type.Show and not plugin._overlay_oculto:
                plugin._mostrar_overlay()
            elif tipo == QEvent.Type.Hide:
                plugin._animacao_capa.stop()
                plugin.painel_capa.hide()
        elif observado is plugin.app.container:
            if tipo in (QEvent.Type.Move, QEvent.Type.Resize):
                plugin._posicionar_widgets()
        elif observado is self.playlist_viewport:
            if tipo in (
                QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick,
                QEvent.Type.Wheel, QEvent.Type.KeyPress
            ):
                plugin._interacao_playlist()
        return False


class Plugin(PluginBase):
    nome = "Música"
    versao = "0.1.0"

    def __init__(self, app):
        super().__init__(app)
        self._encerrando = False
        self._worker = None
        self._worker_estado = None
        self._atualizar_pendente = False
        self._sessoes = []
        self._arrastando_progresso = False
        self._posicao_base = 0
        self._inicio_relogio = time.monotonic()
        self._ultima_atualizacao_estado = 0.0
        self._tocando = False
        self._busca_em_confirmacao = False
        self._busca_solicitada_em = None
        self._imagem_capa = QPixmap()
        self._overlay_oculto = True
        self._retorno_capa_apos_fade = False
        self._seek_pendente = False
        self._comando_pendente = None
        self._comando_em_execucao = None

        self.page = QWidget(app.pages_container)
        self.page.setGeometry(0, 0, 150, 150)
        self.page.hide()
        self.conteudo = QWidget(self.page)
        layout = QVBoxLayout(self.conteudo)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)

        flags = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
        self.painel_capa = BlurredBackgroundFrame(app)
        self.painel_capa.setWindowFlags(flags)
        self.painel_capa.setObjectName("painelCapaMusica")
        self.painel_capa.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.painel_capa.setFixedSize(150, 150)
        layout_capa = QVBoxLayout(self.painel_capa)
        layout_capa.setContentsMargins(7, 7, 7, 7)
        layout_capa.setSpacing(2)

        self.pilha_capa = QStackedWidget()
        self.pagina_capa = QWidget()
        layout_imagem = QVBoxLayout(self.pagina_capa)
        layout_imagem.setContentsMargins(0, 0, 0, 0)
        layout_imagem.setSpacing(2)

        self.capa = CapaMusicaLabel("♪", self.painel_capa)
        self.capa.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.capa.setStyleSheet(
            "background: rgba(255, 255, 255, 35); border-radius: 4px;"
        )
        self.capa.clicked.connect(self._mostrar_playlist)
        layout_imagem.addWidget(self.capa, 1)

        linha_progresso = QHBoxLayout()
        linha_progresso.setContentsMargins(0, 0, 0, 0)
        linha_progresso.setSpacing(3)
        self.tempo_atual = QLabel("0:00")
        self.tempo_total = QLabel("0:00")
        self.tempo_atual.setMinimumWidth(42)
        self.tempo_total.setMinimumWidth(42)
        self.tempo_total.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.progresso = QSlider(Qt.Orientation.Horizontal)
        self.progresso.setRange(0, 0)
        self.progresso.setFixedHeight(12)
        self.progresso.sliderPressed.connect(self._iniciar_arrasto)
        self.progresso.sliderReleased.connect(self._confirmar_busca)
        linha_progresso.addWidget(self.progresso, 1)
        tempos = QHBoxLayout()
        tempos.setContentsMargins(0, 0, 0, 0)
        tempos.addWidget(self.tempo_atual)
        tempos.addStretch()
        tempos.addWidget(self.tempo_total)
        layout_imagem.addLayout(linha_progresso)
        layout_imagem.addLayout(tempos)

        self.pagina_playlist = QWidget()
        layout_playlist = QVBoxLayout(self.pagina_playlist)
        layout_playlist.setContentsMargins(2, 2, 2, 2)
        layout_playlist.setSpacing(2)
        self.lista_playlist = QListWidget()
        self.lista_playlist.setStyleSheet(
            "QListWidget { background: transparent; border: none; }"
        )
        self.estado_playlist = QLabel(
            "A fila não está disponível nesta sessão."
        )
        self.estado_playlist.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.estado_playlist.setWordWrap(True)
        layout_playlist.addWidget(self.lista_playlist, 1)
        layout_playlist.addWidget(self.estado_playlist)

        self.pilha_capa.addWidget(self.pagina_capa)
        self.pilha_capa.addWidget(self.pagina_playlist)
        layout_capa.addWidget(self.pilha_capa)
        self.pilha_capa.setCurrentWidget(self.pagina_capa)

        self._animacao_capa = QPropertyAnimation(
            self.painel_capa, b"windowOpacity", self.app
        )
        self._animacao_capa.setDuration(180)
        self._animacao_capa.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._animacao_capa.finished.connect(self._fim_animacao_capa)
        self.timer_playlist = QTimer(self.app)
        self.timer_playlist.setSingleShot(True)
        self.timer_playlist.setInterval(10_000)
        self.timer_playlist.timeout.connect(self._voltar_capa)
        self.timer_ocultar_overlay = QTimer(self.app)
        self.timer_ocultar_overlay.setSingleShot(True)
        self.timer_ocultar_overlay.setInterval(15_000)
        self.timer_ocultar_overlay.timeout.connect(self._ocultar_overlay)
        self.lista_playlist.itemClicked.connect(
            lambda _item: self._interacao_playlist()
        )

        self.combo_sessoes = QComboBox()
        self.combo_sessoes.setEditable(True)
        self.combo_sessoes.lineEdit().setReadOnly(True)
        self.combo_sessoes.lineEdit().setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.combo_sessoes.setFixedHeight(16)
        self.combo_sessoes.hide()
        self.combo_sessoes.currentIndexChanged.connect(self._selecionar_sessao)

        self.titulo = QLabel("Nenhuma mídia encontrada")
        self.titulo.setFixedHeight(18)
        self.titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.artista = QLabel("")
        self.artista.setMaximumHeight(14)
        self.artista.setAlignment(Qt.AlignmentFlag.AlignCenter)

        controles_principais = QHBoxLayout()
        controles_principais.setContentsMargins(0, 0, 0, 0)
        controles_principais.setSpacing(5)
        estilo = QApplication.style()
        self.btn_anterior = self._criar_botao(
            estilo.standardIcon(QStyle.StandardPixmap.SP_MediaSkipBackward),
            "Música anterior", "anterior", tamanho=28
        )
        self.btn_play_pause = self._criar_botao(
            estilo.standardIcon(QStyle.StandardPixmap.SP_MediaPlay),
            "Reproduzir ou pausar", "alternar", tamanho=28
        )
        self.btn_proxima = self._criar_botao(
            estilo.standardIcon(QStyle.StandardPixmap.SP_MediaSkipForward),
            "Próxima música", "proxima", tamanho=28
        )
        controles_principais.addStretch()
        controles_principais.addWidget(self.btn_anterior)
        controles_principais.addWidget(self.btn_play_pause)
        controles_principais.addWidget(self.btn_proxima)
        controles_principais.addStretch()

        controles_secundarios = QHBoxLayout()
        controles_secundarios.setContentsMargins(0, 0, 0, 0)
        controles_secundarios.setSpacing(5)
        self.btn_voltar_10 = self._criar_botao(
            None, "Voltar 10 segundos", "voltar_10", "-10", tamanho=28
        )
        self.btn_avancar_10 = self._criar_botao(
            None, "Avançar 10 segundos", "avancar_10", "+10", tamanho=28
        )
        self.btn_aleatorio = self._criar_botao(
            None, "Reprodução aleatória", "aleatorio", "⤨", tamanho=28
        )
        self.indicador_aleatorio = QLabel()
        self.indicador_aleatorio.setFixedSize(4, 4)
        self.indicador_aleatorio.setStyleSheet(
            "background: #55d98b; border-radius: 2px;"
        )
        self.indicador_aleatorio.hide()
        grupo_aleatorio = QVBoxLayout()
        grupo_aleatorio.setContentsMargins(0, 0, 0, 0)
        grupo_aleatorio.setSpacing(0)
        grupo_aleatorio.addWidget(self.btn_aleatorio, 0, Qt.AlignmentFlag.AlignCenter)
        grupo_aleatorio.addWidget(self.indicador_aleatorio, 0, Qt.AlignmentFlag.AlignCenter)
        self.btn_alternar_overlay = self._criar_botao(
            estilo.standardIcon(QStyle.StandardPixmap.SP_TitleBarShadeButton),
            "Mostrar ou ocultar capa e playlist", "alternar_overlay", tamanho=28
        )
        self.btn_alternar_overlay.setEnabled(True)
        controles_secundarios.addStretch()
        controles_secundarios.addWidget(self.btn_voltar_10)
        controles_secundarios.addWidget(self.btn_alternar_overlay)
        controles_secundarios.addWidget(self.btn_avancar_10)
        controles_secundarios.addStretch()

        controles_mp3 = QVBoxLayout()
        controles_mp3.setContentsMargins(0, 0, 0, 0)
        controles_mp3.setSpacing(0)
        controles_mp3.addLayout(grupo_aleatorio)
        controles_mp3.addLayout(controles_principais)
        controles_mp3.addLayout(controles_secundarios)

        layout.addWidget(self.combo_sessoes)
        layout.addWidget(self.titulo)
        layout.addWidget(self.artista)
        layout.addLayout(controles_mp3)

        self._filtro_janela = FiltroJanelaMusica(self)
        self.app.installEventFilter(self._filtro_janela)
        self.app.container.installEventFilter(self._filtro_janela)
        self._filtro_janela.playlist_viewport.installEventFilter(self._filtro_janela)

        self.timer_atualizar = QTimer(self.app)
        self.timer_atualizar.setInterval(4000)
        self.timer_atualizar.timeout.connect(self.atualizar_sessoes)
        self.timer_atualizar.start()
        self.timer_progresso = QTimer(self.app)
        self.timer_progresso.setInterval(1000)
        self.timer_progresso.timeout.connect(self._atualizar_progresso)
        self.timer_progresso.start()
        self.timer_estado = QTimer(self.app)
        self.timer_estado.setInterval(500)
        self.timer_estado.timeout.connect(self._atualizar_estado)
        self.timer_estado.start()
        QTimer.singleShot(0, self.atualizar_sessoes)

    def criar_pagina(self):
        self.app.registrar_pagina(
            self.page, chave="controle_musica", nome="Música"
        )
        return None

    def ao_mudar_area_pagina(self, area):
        x, y, largura, altura = area
        self.conteudo.setGeometry(x, y, largura, altura)

    def ao_aplicar_tema(self):
        cor = self.app.cor_texto
        self.painel_capa.overlay_color = self.app.container.overlay_color
        self.painel_capa.border_color = self.app.container.border_color
        self.painel_capa.border_radius = self.app.container.border_radius
        self.painel_capa.bg_pixmap = self.app.container.bg_pixmap
        self.painel_capa.update()
        self.capa.setStyleSheet(
            aplicar_css_fonte_base("lista")
            + f"color: {cor}; background: rgba(255, 255, 255, 35); "
            "border-radius: 4px; font-size: 40px;"
        )
        self.artista.setStyleSheet(
            aplicar_css_fonte_base("data") + f" color: {cor};"
        )
        for label in (self.tempo_atual, self.tempo_total):
            label.setStyleSheet(
                aplicar_css_fonte_base("cal_meses") + f" color: {cor};"
            )
        self.estado_playlist.setStyleSheet(
            aplicar_css_fonte_base("lista") + f" color: {cor};"
        )
        self.lista_playlist.setStyleSheet(
            "QListWidget { background: transparent; border: none; "
            f"color: {cor}; {aplicar_css_fonte_base('cal_lista')} }}"
        )
        self.titulo.setStyleSheet(
            aplicar_css_fonte_base("lista") + f"color: {cor};"
        )
        self.combo_sessoes.setStyleSheet(
            "QComboBox { " + aplicar_css_fonte_base("cal_lista")
            + f" color: {cor}; background: rgba(120, 120, 120, 55); "
            "border-radius: 4px; padding: 2px; text-align: center; }"
        )
        for botao in (self.btn_voltar_10, self.btn_avancar_10, self.btn_aleatorio):
            botao.setStyleSheet(
                aplicar_css_fonte_base("cal_lista")
                + f"color: {cor}; font-size: 9px; font-weight: bold;"
            )
        self.progresso.setStyleSheet(
            "QSlider::groove:horizontal { height: 3px; background: rgba(255,255,255,70); }"
            "QSlider::sub-page:horizontal { background: #55d98b; }"
            "QSlider::handle:horizontal { width: 7px; margin: -2px 0; "
            "border-radius: 3px; background: white; }"
        )

    def encerrar(self):
        self._encerrando = True
        self.timer_atualizar.stop()
        self.timer_progresso.stop()
        self.timer_estado.stop()
        self.timer_playlist.stop()
        self.timer_ocultar_overlay.stop()
        self.app.removeEventFilter(self._filtro_janela)
        self.app.container.removeEventFilter(self._filtro_janela)
        self.lista_playlist.viewport().removeEventFilter(self._filtro_janela)
        self._filtro_janela.deleteLater()
        self.painel_capa.hide()
        self.painel_capa.deleteLater()
        self._animacao_capa.stop()
        return not any(
            worker is not None and worker.isRunning()
            for worker in (self._worker, self._worker_estado)
        )

    def _criar_botao(self, icone, dica, comando, texto="", tamanho=24):
        botao = QPushButton()
        botao.setFixedSize(tamanho, tamanho)
        if icone is not None:
            botao.setIcon(icone)
            botao.setIconSize(QSize(tamanho - 10, tamanho - 10))
        else:
            botao.setText(texto)
            botao.setStyleSheet(
                "QPushButton { font-size: 9px; font-weight: bold; padding: 0; }"
            )
        botao.setToolTip(dica)
        botao.clicked.connect(lambda: self._enviar_comando(comando))
        botao.setEnabled(False)
        if comando == "aleatorio":
            self._opacidade_aleatorio = QGraphicsOpacityEffect(botao)
            self._opacidade_aleatorio.setOpacity(0.25)
            botao.setGraphicsEffect(self._opacidade_aleatorio)
        return botao

    def _posicionar_widgets(self):
        area = self.app.container.geometry()
        posicao = self.app.mapToGlobal(area.topLeft())
        self.painel_capa.move(
            posicao.x(), posicao.y() - self.painel_capa.height() - 5
        )

    def _mostrar_overlay(self):
        if self._encerrando:
            return
        self._posicionar_widgets()
        self.pilha_capa.setCurrentWidget(self.pagina_capa)
        self.painel_capa.show()
        self.painel_capa.setWindowOpacity(0)
        self._animacao_capa.stop()
        self._animacao_capa.setStartValue(0)
        self._animacao_capa.setEndValue(1)
        self._retorno_capa_apos_fade = False
        self._animacao_capa.start()
        self.timer_ocultar_overlay.start()
        self.painel_capa.layout().activate()
        self._atualizar_imagem_capa()

    def _alternar_overlay(self):
        if not self._overlay_oculto:
            self._ocultar_overlay()
            return
        self._overlay_oculto = False
        self._mostrar_overlay()

    def _ocultar_overlay(self):
        if self._overlay_oculto:
            return
        self._overlay_oculto = True
        self.timer_playlist.stop()
        self.pilha_capa.setCurrentWidget(self.pagina_capa)
        self._animacao_capa.stop()
        self._animacao_capa.setStartValue(self.painel_capa.windowOpacity())
        self._animacao_capa.setEndValue(0)
        self._retorno_capa_apos_fade = True
        self._animacao_capa.start()

    def _fim_animacao_capa(self):
        if self._retorno_capa_apos_fade:
            self.painel_capa.hide()
            self._retorno_capa_apos_fade = False

    def _mostrar_playlist(self):
        if self._encerrando or self._overlay_oculto:
            return
        self.lista_playlist.clear()
        self.estado_playlist.setText(
            "A fila de reprodução não é fornecida por esta sessão."
        )
        self.estado_playlist.show()
        self.pilha_capa.setCurrentWidget(self.pagina_playlist)
        self.timer_playlist.start()
        self.timer_ocultar_overlay.start()

    def _voltar_capa(self):
        self.pilha_capa.setCurrentWidget(self.pagina_capa)

    def _interacao_playlist(self):
        if self.pilha_capa.currentWidget() is self.pagina_playlist:
            self.timer_playlist.start()
            self.timer_ocultar_overlay.start()

    def _atualizar_imagem_capa(self):
        if not self._imagem_capa.isNull():
            self.capa.setPixmap(self._imagem_capa)

    def atualizar_sessoes(self):
        if self._encerrando:
            return
        if self._worker is not None and self._worker.isRunning():
            self._atualizar_pendente = True
            return
        self._iniciar_worker()

    def _iniciar_worker(self, comando=None, chave=None, valor=None):
        if self._worker is not None and self._worker.isRunning():
            if comando == "buscar":
                self._comando_pendente = (comando, chave, valor)
            return
        if comando == "buscar":
            self._busca_solicitada_em = datetime.now(timezone.utc)
        self._comando_em_execucao = comando
        self._worker = WorkerSessoesMedia(
            comando, chave, valor=valor, parent=self.app
        )
        self._worker.sessoes_carregadas.connect(self._mostrar_sessoes)
        self._worker.estado_carregado.connect(self._mostrar_estado)
        self._worker.comando_concluido.connect(self._comando_concluido)
        self._worker.erro.connect(self._mostrar_erro)
        self._worker.finished.connect(self._worker_finalizado)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _worker_finalizado(self):
        self._worker = None
        if self._comando_em_execucao == "buscar":
            self._seek_pendente = False
        self._comando_em_execucao = None
        if self._comando_pendente is not None and not self._encerrando:
            comando, chave, valor = self._comando_pendente
            self._comando_pendente = None
            self._iniciar_worker(comando, chave, valor)
            return
        if self._atualizar_pendente and not self._encerrando:
            self._atualizar_pendente = False
            self.atualizar_sessoes()

    def _mostrar_sessoes(self, sessoes):
        if self._encerrando:
            return
        selecao = self.combo_sessoes.currentData()
        self._sessoes = sessoes
        self.combo_sessoes.blockSignals(True)
        self.combo_sessoes.clear()
        for sessao in sessoes:
            fonte = self._nome_fonte(sessao["fonte"])
            nome = f'{fonte} | {sessao["titulo"]}'
            self.combo_sessoes.addItem(nome, sessao["chave"])
        self.combo_sessoes.setVisible(len(sessoes) > 1)
        indice = self.combo_sessoes.findData(selecao)
        if indice < 0:
            indice = next(
                (i for i, sessao in enumerate(sessoes) if sessao["atual"]), 0
            )
        self.combo_sessoes.setCurrentIndex(indice if sessoes else -1)
        self.combo_sessoes.blockSignals(False)
        self._selecionar_sessao()

    def _selecionar_sessao(self):
        chave = self.combo_sessoes.currentData()
        sessao = next((item for item in self._sessoes if item["chave"] == chave), None)
        if sessao is None:
            self.titulo.setText("Nenhuma mídia encontrada")
            self.artista.clear()
            self._imagem_capa = QPixmap()
            self.capa.setPixmap(QPixmap())
            self.capa.setText("♪")
            self.progresso.setRange(0, 0)
            self.progresso.setEnabled(False)
            self.tempo_atual.setText("0:00")
            self.tempo_total.setText("0:00")
            self.indicador_aleatorio.hide()
            self._opacidade_aleatorio.setOpacity(0.25)
            for botao in (
                self.btn_voltar_10, self.btn_anterior, self.btn_play_pause,
                self.btn_proxima, self.btn_avancar_10, self.btn_aleatorio
            ):
                botao.setEnabled(False)
            return

        self.titulo.setText(sessao["titulo"])
        self.artista.setText(sessao["artista"] or self._nome_fonte(sessao["fonte"]))
        pixmap = QPixmap()
        if sessao["imagem"] and pixmap.loadFromData(sessao["imagem"]):
            self._imagem_capa = pixmap
            self.capa.setText("")
            self._atualizar_imagem_capa()
        else:
            self._imagem_capa = QPixmap()
            self.capa.setPixmap(QPixmap())
            self.capa.setText("♪")
        self._tocando = sessao["tocando"]
        self._ultima_atualizacao_estado = max(
            self._ultima_atualizacao_estado, sessao["capturado_em"]
        )
        self.progresso.setRange(0, sessao["duracao"])
        self.progresso.setEnabled(sessao["pode_buscar"])
        if not self._arrastando_progresso and not self._seek_pendente:
            if self._pode_sincronizar_posicao(sessao["atualizado_em"]):
                self._posicao_base = sessao["posicao"]
                self._inicio_relogio = sessao["capturado_em"]
            posicao = self._posicao_atual()
            self.progresso.setValue(posicao)
            self.tempo_atual.setText(self._formatar_tempo(posicao))
        self.tempo_total.setText(self._formatar_tempo(sessao["duracao"]))
        self.btn_anterior.setEnabled(sessao["pode_anterior"])
        self.btn_proxima.setEnabled(sessao["pode_proxima"])
        self.btn_voltar_10.setEnabled(sessao["pode_buscar"])
        self.btn_avancar_10.setEnabled(sessao["pode_buscar"])
        self.btn_play_pause.setEnabled(sessao["pode_alternar"])
        self.btn_aleatorio.setEnabled(sessao["pode_aleatorio"])
        self._opacidade_aleatorio.setOpacity(1.0 if sessao["pode_aleatorio"] else 0.25)
        self.indicador_aleatorio.setVisible(
            sessao["pode_aleatorio"] and sessao["aleatorio"]
        )
        icone = QStyle.StandardPixmap.SP_MediaPause if sessao["tocando"] else QStyle.StandardPixmap.SP_MediaPlay
        self.btn_play_pause.setIcon(QApplication.style().standardIcon(icone))

    def _pode_sincronizar_posicao(self, atualizado_em):
        if not self._busca_em_confirmacao:
            return True
        if (
            atualizado_em is not None
            and self._busca_solicitada_em is not None
            and atualizado_em >= self._busca_solicitada_em
        ):
            self._busca_em_confirmacao = False
            self._busca_solicitada_em = None
            return True
        return False

    def _enviar_comando(self, comando, valor=None):
        if comando == "alternar_overlay":
            self._alternar_overlay()
            return
        chave = self.combo_sessoes.currentData()
        if chave is None:
            return
        if comando == "voltar_10":
            comando = "buscar"
            valor = max(0, self._posicao_atual() - 10)
        elif comando == "avancar_10":
            sessao = next((item for item in self._sessoes if item["chave"] == chave), None)
            comando = "buscar"
            valor = min(
                sessao["duracao"], self._posicao_atual() + 10
            ) if sessao else self._posicao_atual() + 10
        elif comando == "aleatorio":
            sessao = next((item for item in self._sessoes if item["chave"] == chave), None)
            valor = not sessao["aleatorio"] if sessao else False
        elif comando == "buscar":
            self._seek_pendente = True
            valor = self.progresso.value() if valor is None else valor
            self._posicao_base = max(0, min(self.progresso.maximum(), int(valor)))
            self._inicio_relogio = time.monotonic()
            self._busca_em_confirmacao = True
            self.tempo_atual.setText(self._formatar_tempo(valor))
            self.progresso.setValue(valor)
        self._iniciar_worker(comando, chave, valor)

    def _iniciar_arrasto(self):
        self._arrastando_progresso = True

    def _confirmar_busca(self):
        self._arrastando_progresso = False
        self._enviar_comando("buscar", self.progresso.value())

    def _atualizar_progresso(self):
        if self._arrastando_progresso or self._seek_pendente:
            return
        posicao = self._posicao_atual()
        self.tempo_atual.setText(self._formatar_tempo(posicao))
        if self.progresso.maximum() > 0:
            self.progresso.setValue(posicao)

    def _atualizar_estado(self):
        if self._encerrando or self._worker_estado is not None:
            return
        chave = self.combo_sessoes.currentData()
        if chave is None:
            return
        worker = WorkerSessoesMedia("estado", chave, parent=self.app)
        self._worker_estado = worker
        worker.estado_carregado.connect(self._mostrar_estado)
        worker.erro.connect(self._mostrar_erro)
        worker.finished.connect(self._worker_estado_finalizado)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _worker_estado_finalizado(self):
        self._worker_estado = None

    def _mostrar_estado(self, estado):
        if self._encerrando or estado is None:
            return
        if estado["capturado_em"] < self._ultima_atualizacao_estado:
            return
        chave = self.combo_sessoes.currentData()
        sessao = next(
            (item for item in self._sessoes if item["chave"] == chave), None
        )
        if sessao is None:
            return
        posicao_local = self._posicao_atual()
        sessao["tocando"] = estado["tocando"]
        self._ultima_atualizacao_estado = estado["capturado_em"]
        self._tocando = estado["tocando"]
        if (
            not self._seek_pendente
            and self._pode_sincronizar_posicao(estado["atualizado_em"])
        ):
            sessao["posicao"] = estado["posicao"]
            self._posicao_base = estado["posicao"]
            self._inicio_relogio = estado["capturado_em"]
        else:
            self._posicao_base = posicao_local
            self._inicio_relogio = estado["capturado_em"]
        if not self._arrastando_progresso and not self._seek_pendente:
            posicao = self._posicao_atual()
            self.tempo_atual.setText(self._formatar_tempo(posicao))
            self.progresso.setValue(posicao)
        icone = (
            QStyle.StandardPixmap.SP_MediaPause
            if self._tocando else QStyle.StandardPixmap.SP_MediaPlay
        )
        self.btn_play_pause.setIcon(QApplication.style().standardIcon(icone))

    def _posicao_atual(self):
        decorrido = int(time.monotonic() - self._inicio_relogio) if self._tocando else 0
        return min(self.progresso.maximum(), self._posicao_base + decorrido)

    @staticmethod
    def _formatar_tempo(segundos):
        minutos, segundos = divmod(max(0, int(segundos)), 60)
        horas, minutos = divmod(minutos, 60)
        return f"{horas}:{minutos:02d}:{segundos:02d}" if horas else f"{minutos}:{segundos:02d}"

    def _comando_concluido(self, sucesso):
        if not self._encerrando and self._comando_em_execucao != "alternar":
            self.atualizar_sessoes()

    def _mostrar_erro(self, mensagem):
        if not self._encerrando:
            self.titulo.setText("Controle de mídia indisponível")
            self.titulo.setToolTip(mensagem)

    @staticmethod
    def _nome_fonte(fonte):
        identificador = fonte.lower()
        if "chrome" in identificador:
            return "Chrome"
        if "msedge" in identificador or "edge" in identificador:
            return "Edge"
        if "spotify" in identificador:
            return "Spotify"
        return fonte.rsplit("!", 1)[-1].rsplit(".", 1)[-1] or fonte