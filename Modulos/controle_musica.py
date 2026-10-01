import asyncio

from PyQt6.QtCore import QThread, QTimer, Qt, QSize, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QHBoxLayout, QLabel, QPushButton, QStyle,
    QVBoxLayout, QWidget
)

from config import MARGEM_AREA_ICONES
from gerenciador_modulos import PluginBase

try:
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
    from winrt.windows.storage.streams import DataReader
except ImportError as erro:
    GlobalSystemMediaTransportControlsSessionManager = None
    DataReader = None
    ERRO_WINRT = str(erro)
else:
    ERRO_WINRT = ""


class WorkerSessoesMedia(QThread):
    sessoes_carregadas = pyqtSignal(object)
    comando_concluido = pyqtSignal(bool)
    erro = pyqtSignal(str)

    def __init__(self, comando=None, chave_sessao=None, parent=None):
        super().__init__(parent)
        self.comando = comando
        self.chave_sessao = chave_sessao

    def run(self):
        try:
            resultado = asyncio.run(self._executar())
            if self.comando is None:
                self.sessoes_carregadas.emit(resultado)
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
                controles = sessao.get_playback_info().controls
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
                    "tocando": controles.is_pause_enabled,
                    "pode_alternar": controles.is_play_pause_toggle_enabled,
                    "pode_anterior": controles.is_previous_enabled,
                    "pode_proxima": controles.is_next_enabled,
                    "atual": sessao == atual
                })
            except Exception:
                continue

        if self.comando is None:
            return registros

        registro = next(
            (item for item in registros if item["chave"] == self.chave_sessao), None
        )
        if registro is None:
            return False

        sessao_alvo = None
        ocorrencias.clear()
        for sessao in sessoes:
            propriedades = await sessao.try_get_media_properties_async()
            fonte = sessao.source_app_user_model_id or "Aplicativo"
            titulo = propriedades.title or "Sem título"
            artista = propriedades.artist or propriedades.album_artist or ""
            base = (fonte, titulo, artista)
            ocorrencia = ocorrencias.get(base, 0)
            ocorrencias[base] = ocorrencia + 1
            if base + (ocorrencia,) == self.chave_sessao:
                sessao_alvo = sessao
                break

        if sessao_alvo is None:
            return False
        acoes = {
            "alternar": sessao_alvo.try_toggle_play_pause_async,
            "anterior": sessao_alvo.try_skip_previous_async,
            "proxima": sessao_alvo.try_skip_next_async
        }
        operacao = acoes.get(self.comando)
        if operacao is None:
            return False
        return await operacao()

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


class Plugin(PluginBase):
    nome = "Música"
    versao = "0.0.1"

    def __init__(self, app):
        super().__init__(app)
        self._encerrando = False
        self._worker = None
        self._atualizar_pendente = False
        self._sessoes = []

        self.page = QWidget(app.pages_container)
        self.page.setGeometry(0, 0, 150, 150)
        self.page.hide()

        self.conteudo = QWidget(self.page)
        layout = QVBoxLayout(self.conteudo)
        layout.setContentsMargins(5, 4, 5, 4)
        layout.setSpacing(2)

        self.combo_sessoes = QComboBox()
        self.combo_sessoes.setFixedHeight(20)
        self.combo_sessoes.currentIndexChanged.connect(self._selecionar_sessao)

        linha_musica = QHBoxLayout()
        linha_musica.setContentsMargins(0, 0, 0, 0)
        linha_musica.setSpacing(5)
        self.capa = QLabel("♪")
        self.capa.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.capa.setFixedSize(42, 42)
        self.capa.setStyleSheet("background: rgba(255, 255, 255, 35); border-radius: 5px;")

        textos = QVBoxLayout()
        textos.setContentsMargins(0, 0, 0, 0)
        textos.setSpacing(1)
        self.titulo = QLabel("Nenhuma mídia encontrada")
        self.titulo.setWordWrap(True)
        self.titulo.setMaximumHeight(30)
        self.artista = QLabel("")
        self.artista.setWordWrap(True)
        self.artista.setMaximumHeight(24)
        textos.addWidget(self.titulo)
        textos.addWidget(self.artista)
        linha_musica.addWidget(self.capa)
        linha_musica.addLayout(textos, 1)

        controles = QHBoxLayout()
        controles.setContentsMargins(0, 0, 0, 0)
        controles.setSpacing(10)
        estilo = QApplication.style()
        self.btn_anterior = self._criar_botao(
            estilo.standardIcon(QStyle.StandardPixmap.SP_MediaSkipBackward),
            "Música anterior", "anterior"
        )
        self.btn_play_pause = self._criar_botao(
            estilo.standardIcon(QStyle.StandardPixmap.SP_MediaPlay),
            "Reproduzir ou pausar", "alternar"
        )
        self.btn_proxima = self._criar_botao(
            estilo.standardIcon(QStyle.StandardPixmap.SP_MediaSkipForward),
            "Próxima música", "proxima"
        )
        controles.addStretch()
        controles.addWidget(self.btn_anterior)
        controles.addWidget(self.btn_play_pause)
        controles.addWidget(self.btn_proxima)
        controles.addStretch()

        self.status = QLabel("Buscando sessões de mídia...")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.combo_sessoes)
        layout.addLayout(linha_musica, 1)
        layout.addLayout(controles)
        layout.addWidget(self.status)

        self.timer_atualizar = QTimer(self.app)
        self.timer_atualizar.setInterval(4000)
        self.timer_atualizar.timeout.connect(self.atualizar_sessoes)
        self.timer_atualizar.start()
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
        for label in (self.titulo, self.artista, self.status):
            label.setStyleSheet(f"color: {cor}; background: transparent;")
        self.combo_sessoes.setStyleSheet(
            f"QComboBox {{ color: {cor}; background: rgba(120, 120, 120, 55); "
            "border: none; border-radius: 4px; padding: 2px; }"
        )

    def encerrar(self):
        self._encerrando = True
        self.timer_atualizar.stop()
        return not (self._worker is not None and self._worker.isRunning())

    def _criar_botao(self, icone, dica, comando):
        botao = QPushButton()
        botao.setFixedSize(26, 26)
        botao.setIcon(icone)
        botao.setIconSize(QSize(18, 18))
        botao.setToolTip(dica)
        botao.clicked.connect(lambda: self._enviar_comando(comando))
        botao.setEnabled(False)
        return botao

    def atualizar_sessoes(self):
        if self._encerrando:
            return
        if self._worker is not None and self._worker.isRunning():
            self._atualizar_pendente = True
            return
        self._iniciar_worker()

    def _iniciar_worker(self, comando=None, chave=None):
        self._worker = WorkerSessoesMedia(comando, chave, self.app)
        self._worker.sessoes_carregadas.connect(self._mostrar_sessoes)
        self._worker.comando_concluido.connect(self._comando_concluido)
        self._worker.erro.connect(self._mostrar_erro)
        self._worker.finished.connect(self._worker_finalizado)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _worker_finalizado(self):
        self._worker = None
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
            self.capa.setPixmap(QPixmap())
            self.capa.setText("♪")
            self.status.setText("Abra uma música em um app ou navegador compatível.")
            for botao in (self.btn_anterior, self.btn_play_pause, self.btn_proxima):
                botao.setEnabled(False)
            return

        self.titulo.setText(sessao["titulo"])
        self.artista.setText(sessao["artista"] or self._nome_fonte(sessao["fonte"]))
        pixmap = QPixmap()
        if sessao["imagem"] and pixmap.loadFromData(sessao["imagem"]):
            self.capa.setText("")
            self.capa.setPixmap(pixmap.scaled(
                42, 42, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))
        else:
            self.capa.setPixmap(QPixmap())
            self.capa.setText("♪")
        self.btn_anterior.setEnabled(sessao["pode_anterior"])
        self.btn_proxima.setEnabled(sessao["pode_proxima"])
        self.btn_play_pause.setEnabled(sessao["pode_alternar"])
        icone = QStyle.StandardPixmap.SP_MediaPause if sessao["tocando"] else QStyle.StandardPixmap.SP_MediaPlay
        self.btn_play_pause.setIcon(QApplication.style().standardIcon(icone))
        self.status.setText("Reproduzindo" if sessao["tocando"] else "Pausado")

    def _enviar_comando(self, comando):
        chave = self.combo_sessoes.currentData()
        if chave is not None and (self._worker is None or not self._worker.isRunning()):
            self._iniciar_worker(comando, chave)

    def _comando_concluido(self, sucesso):
        if not self._encerrando:
            self.atualizar_sessoes()

    def _mostrar_erro(self, mensagem):
        if not self._encerrando:
            self.status.setText("Controle de mídia indisponível")
            self.status.setToolTip(mensagem)

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