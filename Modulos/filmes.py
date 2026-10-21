import json
import os
import urllib.error
import urllib.request
import uuid
from urllib.parse import urlsplit

from PyQt6.QtCore import (
    QEvent, QObject, QThread, Qt, QRect, QSize, QTimer, pyqtSignal,
)
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap, QRegion
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QSizePolicy, QSpinBox, QStackedWidget, QTextBrowser, QTextEdit,
    QVBoxLayout, QWidget,
)

from config import APPDATA_DIR, config_app
from gerenciador_modulos import PluginBase
from ui_components import BlurredBackgroundFrame, MarqueeLabel, OutlineLabel
from utils import aplicar_css_fonte_base
from vidro import atualizar_vidro, esconder_vidro


CHAVE_CONFIG = "filmes"
ARQUIVO_FILMES = os.path.join(APPDATA_DIR, "filmes.json")
STATUS_CORES = {
    "nao_assistido": "#ffffff",
    "assistido": "#55d98b",
    "incompleto": "#ff5a5a",
}
STATUS_PROXIMO = {
    "nao_assistido": "assistido",
    "assistido": "incompleto",
    "incompleto": "nao_assistido",
}
MAX_BYTES_IMAGEM = 5 * 1024 * 1024


def _url_imagem_valida(valor):
    if not isinstance(valor, str):
        return False
    try:
        url = urlsplit(valor.strip())
        return (
            url.scheme in ("http", "https")
            and bool(url.hostname)
            and url.username is None
            and url.password is None
        )
    except ValueError:
        return False


class WorkerImagemFilme(QThread):
    concluido = pyqtSignal(object, str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            requisicao = urllib.request.Request(
                self.url, headers={"User-Agent": "MussasWidget"}
            )
            with urllib.request.urlopen(requisicao, timeout=6) as resposta:
                url_final = resposta.geturl()
                if not _url_imagem_valida(url_final):
                    raise ValueError("O endereço redirecionou para uma URL inválida.")
                dados = resposta.read(MAX_BYTES_IMAGEM + 1)
            if len(dados) > MAX_BYTES_IMAGEM:
                raise ValueError("A imagem ultrapassa o limite de 5 MB.")
            imagem = QImage()
            if not imagem.loadFromData(dados):
                raise ValueError("O endereço não retornou uma imagem válida.")
            self.concluido.emit(imagem, "")
        except (OSError, urllib.error.URLError, ValueError) as erro:
            self.concluido.emit(None, str(erro))


class NomeFilmeLabel(MarqueeLabel):
    clicado = pyqtSignal()
    mudar_status = pyqtSignal()

    def __init__(self, texto, parent=None):
        super().__init__(texto, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.setMinimumWidth(0)
        self.setFixedHeight(22)
        self.setAttribute(Qt.WidgetAttribute.WA_NoMousePropagation)
        self._hovered = False
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._timer.stop()

    def resizeEvent(self, evento):
        super().resizeEvent(evento)
        self.setMask(QRegion(self.rect()))

    def _reiniciar(self):
        super()._reiniciar()
        if not self.underMouse():
            self._timer.stop()

    def enterEvent(self, evento):
        super().enterEvent(evento)
        self._hovered = True
        self.update()
        if self._excesso() > 0:
            self._pausa = 10
            self._timer.start()

    def leaveEvent(self, evento):
        self._hovered = False
        self._timer.stop()
        self._offset = 0.0
        self.update()
        super().leaveEvent(evento)

    def paintEvent(self, evento):
        painter = QPainter(self)
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_Clear
        )
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.end()
        painter = QPainter(self)
        opacidade = 255 if self._hovered else 3
        painter.fillRect(self.rect(), QColor(128, 128, 128, opacidade))
        painter.end()
        if self._excesso() <= 0:
            OutlineLabel.paintEvent(self, evento)
        else:
            super().paintEvent(evento)

    def mousePressEvent(self, evento):
        if not self.rect().contains(evento.position().toPoint()):
            evento.ignore()
            return
        if evento.button() == Qt.MouseButton.RightButton:
            self.mudar_status.emit()
            evento.accept()
            return
        if evento.button() == Qt.MouseButton.LeftButton:
            self.clicado.emit()
            evento.accept()
            return
        evento.ignore()

    def wheelEvent(self, evento):
        widget = self.parentWidget()
        while widget is not None and not isinstance(widget, ListaFilmesWidget):
            widget = widget.parentWidget()
        if widget is not None:
            widget.wheelEvent(evento)
            return
        evento.ignore()


class ImagemFilmeLabel(QLabel):
    clicado = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(118, 118)
        self.setStyleSheet("background: transparent; border: none;")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def receber_resultado(self, dados, erro):
        if isinstance(dados, QImage) and not dados.isNull():
            pixmap = QPixmap.fromImage(dados).scaled(
                self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (pixmap.width() - self.width()) // 2
            y = (pixmap.height() - self.height()) // 2
            self.setPixmap(
                pixmap.copy(QRect(x, y, self.width(), self.height()))
            )
            self.setToolTip("")
        else:
            self.clear()
            self.setToolTip(f"Imagem indisponível: {erro}")

    def mousePressEvent(self, evento):
        if evento.button() == Qt.MouseButton.LeftButton:
            self.clicado.emit()
            evento.accept()
            return
        super().mousePressEvent(evento)


class DescricaoFilmeLabel(QTextBrowser):
    clicado = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QTextBrowser.Shape.NoFrame)
        self.setReadOnly(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

    def wheelEvent(self, evento):
        deslocamento = evento.pixelDelta().y()
        if deslocamento == 0:
            delta = evento.angleDelta().y()
            if delta == 0:
                evento.ignore()
                return
            deslocamento = round(
                delta / 120 * self.verticalScrollBar().singleStep() * 3
            )
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().value() - deslocamento
        )
        evento.accept()

    def mousePressEvent(self, evento):
        if evento.button() == Qt.MouseButton.LeftButton:
            self.clicado.emit()
            evento.accept()
            return
        super().mousePressEvent(evento)


class FiltroJanelaFilmes(QObject):
    def __init__(self, plugin):
        super().__init__(plugin.app)
        self.plugin = plugin

    def eventFilter(self, observado, evento):
        if observado is self.plugin.app and evento.type() in (
            QEvent.Type.Move, QEvent.Type.Resize
        ):
            self.plugin._posicionar_painel()
        elif observado in (self.plugin.app, self.plugin.painel_filme) and (
            evento.type() == QEvent.Type.WindowActivate
        ):
            QTimer.singleShot(0, self.plugin._restaurar_painel_ativo)
        elif observado is self.plugin.app and evento.type() == QEvent.Type.Hide:
            self.plugin._esconder_painel()
        elif observado is self.plugin.page and evento.type() == QEvent.Type.Hide:
            self.plugin._esconder_painel()
        return False


class PaginaFilmes(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoMousePropagation)

    def mousePressEvent(self, evento):
        evento.accept()


class PainelFilmesFrame(BlurredBackgroundFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoMousePropagation)

    def mousePressEvent(self, evento):
        evento.accept()

    def resizeEvent(self, evento):
        super().resizeEvent(evento)
        self.setMask(QRegion(self.rect()))

    def paintEvent(self, evento):
        painter = QPainter(self)
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_Source
        )
        painter.fillRect(self.rect(), QColor(0, 0, 0, 1))
        painter.end()
        super().paintEvent(evento)


class ListaFilmesWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.viewport().installEventFilter(self)

    def eventFilter(self, observado, evento):
        if (
            observado is self.viewport()
            and evento.type() == QEvent.Type.Wheel
        ):
            self.wheelEvent(evento)
            return True
        return super().eventFilter(observado, evento)

    def wheelEvent(self, evento):
        deslocamento = evento.pixelDelta().y()
        if deslocamento == 0:
            delta = evento.angleDelta().y()
            if delta == 0:
                evento.ignore()
                return
            deslocamento = round(
                delta / 120 * self.verticalScrollBar().singleStep() * 3
            )
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().value() - deslocamento
        )
        evento.accept()


class Plugin(PluginBase):
    nome = "Filmes"
    versao = "1.0.0"

    def __init__(self, app):
        super().__init__(app)
        self._erro_arquivo = ""
        self._filmes = self._carregar_filmes()
        self._config = config_app.config_modulos.setdefault(CHAVE_CONFIG, {})
        if not isinstance(self._config, dict):
            self._config = {}
            config_app.config_modulos[CHAVE_CONFIG] = self._config
        if self._config.get("ordem") not in (
            "alfabetica", "cronologica", "status"
        ):
            self._config["ordem"] = "alfabetica"
        self._workers_imagem = []

        self.page = PaginaFilmes(app.pages_container)
        self.page.setGeometry(0, 0, 150, 150)
        self.page.setProperty("mussas_full_page_hit_area", True)
        self.page.setAutoFillBackground(False)
        self.page.setStyleSheet("background: transparent;")
        self.conteudo = QWidget(self.page)
        self.conteudo.setGeometry(14, 14, 122, 122)
        self.conteudo.setAutoFillBackground(False)
        self.conteudo.setAttribute(Qt.WidgetAttribute.WA_NoMousePropagation)
        self.conteudo.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self.conteudo)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        barra_busca = QHBoxLayout()
        barra_busca.setContentsMargins(0, 0, 0, 0)
        barra_busca.setSpacing(2)
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Buscar filme")
        self.busca.setClearButtonEnabled(False)
        self.busca.setFixedHeight(20)
        self.busca.textChanged.connect(self._atualizar_botao_limpar_busca)
        self.busca.textChanged.connect(self._atualizar_lista)
        self.botao_adicionar = QPushButton("+")
        self.botao_adicionar.setFixedSize(20, 20)
        self.botao_adicionar.setToolTip("Adicionar filme")
        self.botao_adicionar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.botao_adicionar.clicked.connect(self._abrir_adicao)
        barra_busca.addWidget(
            self.busca, 1, Qt.AlignmentFlag.AlignVCenter
        )
        barra_busca.addWidget(
            self.botao_adicionar, 0, Qt.AlignmentFlag.AlignVCenter
        )
        layout.addLayout(barra_busca)
        layout.addSpacing(1)

        self.lista = ListaFilmesWidget()
        self.lista.setFrameShape(QListWidget.Shape.NoFrame)
        self.lista.setAutoFillBackground(False)
        self.lista.setAttribute(Qt.WidgetAttribute.WA_NoMousePropagation)
        self.lista.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.lista.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.lista.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.lista.setStyleSheet(
            "QListWidget { background: transparent; border: none; }"
            "QListWidget::item { background: transparent; border: none; }"
        )
        self.lista.viewport().setAutoFillBackground(False)
        self.lista.viewport().setAttribute(
            Qt.WidgetAttribute.WA_NoMousePropagation
        )
        self.lista.viewport().setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground
        )
        self.lista.viewport().setStyleSheet("background: transparent;")
        self.lista.hide()
        self.lista.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        layout.addWidget(self.lista)

        self.estado = QLabel()
        self.estado.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        self.estado.setWordWrap(True)
        self.estado.setStyleSheet("background: transparent;")
        layout.addWidget(self.estado)
        layout.addStretch(2)
        self._atualizar_lista()

        flags = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
        self.painel_filme = PainelFilmesFrame(app)
        self.painel_filme.setWindowFlags(flags)
        self.painel_filme.setObjectName("painelDetalheFilme")
        self.painel_filme.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.painel_filme.setFixedSize(150, 195)
        painel_layout = QVBoxLayout(self.painel_filme)
        painel_layout.setContentsMargins(8, 5, 8, 5)
        painel_layout.setSpacing(0)

        cabecalho = QWidget(self.painel_filme)
        cabecalho.setFixedHeight(41)
        cabecalho_layout = QVBoxLayout(cabecalho)
        cabecalho_layout.setContentsMargins(0, 0, 0, 0)
        cabecalho_layout.setSpacing(1)
        self.titulo_painel = MarqueeLabel("")
        self.titulo_painel.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        self.titulo_painel.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self.titulo_painel.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        self.titulo_painel.setFixedHeight(18)
        self.botao_editar = QPushButton("✏️ Editar")
        self.botao_editar.setFixedHeight(20)
        self.botao_editar.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.botao_editar.setToolTip("Editar filme")
        self.botao_editar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.botao_editar.clicked.connect(self._editar_filme_atual)
        self.botao_fechar = QPushButton("×")
        self.botao_fechar.setFixedSize(20, 20)
        self.botao_fechar.setToolTip("Fechar")
        self.botao_fechar.clicked.connect(self._esconder_painel)
        controles_layout = QHBoxLayout()
        controles_layout.setContentsMargins(0, 0, 0, 0)
        controles_layout.setSpacing(3)
        controles_layout.addWidget(self.botao_editar)
        controles_layout.addWidget(self.botao_fechar)
        cabecalho_layout.addLayout(controles_layout)
        cabecalho_layout.addWidget(self.titulo_painel)
        painel_layout.addWidget(cabecalho)

        self.conteudo_detalhe = QWidget()
        self.conteudo_detalhe.setFixedSize(118, 136)
        self.pilha_detalhes = QStackedWidget(self.conteudo_detalhe)
        self.pilha_detalhes.setGeometry(0, 0, 118, 118)
        self.imagem_filme = ImagemFilmeLabel()
        self.imagem_filme.clicado.connect(self._alternar_descricao)
        self.descricao_filme = DescricaoFilmeLabel()
        self.descricao_filme.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self.descricao_filme.setLineWrapMode(
            QTextEdit.LineWrapMode.WidgetWidth
        )
        self.descricao_filme.setFixedSize(118, 118)
        self.descricao_filme.setCursor(Qt.CursorShape.PointingHandCursor)
        self.descricao_filme.setToolTip("Clique para voltar à imagem")
        self.descricao_filme.setStyleSheet("background: transparent; border: none;")
        self.descricao_filme.clicado.connect(self._alternar_descricao)
        self.pilha_detalhes.addWidget(self.imagem_filme)
        self.pilha_detalhes.addWidget(self.descricao_filme)

        self.ano_filme = QLabel(self.conteudo_detalhe)
        self.ano_filme.setGeometry(0, 118, 118, 18)
        self.ano_filme.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        painel_layout.addWidget(
            self.conteudo_detalhe, 0, Qt.AlignmentFlag.AlignHCenter
        )

        self._filme_atual_id = None
        self._filtro_janela = FiltroJanelaFilmes(self)
        self.app.installEventFilter(self._filtro_janela)
        self.painel_filme.installEventFilter(self._filtro_janela)
        self.page.installEventFilter(self._filtro_janela)

    def criar_pagina(self):
        self.app.registrar_pagina(self.page, chave="filmes", nome="Filmes")
        return None

    def ao_mudar_area_pagina(self, area):
        x, y, largura, altura = area
        self.conteudo.setGeometry(x, y, largura, altura)

    def ao_aplicar_tema(self):
        cor = self.app.cor_texto
        self.busca.setStyleSheet(
            aplicar_css_fonte_base("data")
            + f"color: {cor}; background: rgba(35, 35, 35, 210); "
            "border: 1px solid rgba(180, 180, 180, 170); "
            "border-radius: 5px; padding: 0;"
        )
        self.botao_adicionar.setStyleSheet(
            "QPushButton { background: rgba(120, 120, 120, 80); border: none; "
            "border-radius: 6px; }"
            "QPushButton:hover { background: rgba(120, 120, 120, 150); }"
        )
        self.estado.setStyleSheet(
            aplicar_css_fonte_base("cal_lista")
            + f"color: {cor}; background: transparent; font-size: 10px;"
        )
        self.titulo_painel.setStyleSheet(
            aplicar_css_fonte_base("cal_titulo") + f"color: {cor};"
        )
        self.ano_filme.setStyleSheet(
            aplicar_css_fonte_base("cal_titulo") + f"color: {cor};"
        )
        self.descricao_filme.setStyleSheet(
            aplicar_css_fonte_base("data") + f"color: {cor};"
        )
        estilo_botao = (
            "QPushButton { background: rgba(120, 120, 120, 80); "
            f"border: none; border-radius: 6px; color: {cor}; }}"
            "QPushButton:hover { background: rgba(120, 120, 120, 150); }"
        )
        self.botao_editar.setStyleSheet(estilo_botao)
        self.botao_fechar.setStyleSheet(estilo_botao)
        self._sincronizar_fundo_painel()
        self._atualizar_lista()

    def abrir_configuracoes(self, parent=None):
        dialogo = QDialog(parent or self.app)
        dialogo.setWindowTitle("Configurações de Filmes")
        layout = QVBoxLayout(dialogo)
        formulario = QFormLayout()
        ordem = QComboBox()
        ordem.addItem("Ordem alfabética", "alfabetica")
        ordem.addItem("Ordem cronológica (ano)", "cronologica")
        ordem.addItem(
            "Por status (assistido, incompleto, não assistido)", "status"
        )
        indice = ordem.findData(self._config["ordem"])
        ordem.setCurrentIndex(max(0, indice))
        formulario.addRow("Ordenar lista:", ordem)
        layout.addLayout(formulario)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.accepted.connect(dialogo.accept)
        botoes.rejected.connect(dialogo.reject)
        layout.addWidget(botoes)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return False

        self._config["ordem"] = ordem.currentData()
        config_app.salvar()
        self._atualizar_lista()
        return True

    def _carregar_filmes(self):
        try:
            with open(ARQUIVO_FILMES, "r", encoding="utf-8") as arquivo:
                dados = json.load(arquivo)
        except FileNotFoundError:
            return []
        except (OSError, json.JSONDecodeError) as erro:
            self._erro_arquivo = f"Não foi possível ler a lista de filmes: {erro}"
            return []

        if not isinstance(dados, dict) or not isinstance(dados.get("filmes"), list):
            self._erro_arquivo = "O arquivo da lista de filmes está em formato inválido."
            return []

        filmes = []
        ids = set()
        for filme in dados["filmes"]:
            if not isinstance(filme, dict):
                self._erro_arquivo = "A lista contém um registro de filme inválido."
                return []
            nome = filme.get("nome")
            identificador = filme.get("id")
            if (
                not isinstance(nome, str)
                or not nome.strip()
                or not isinstance(identificador, str)
                or not identificador
                or identificador in ids
            ):
                self._erro_arquivo = "A lista contém um filme sem nome ou identificador válido."
                return []
            ano = filme.get("ano")
            if not isinstance(ano, int) or isinstance(ano, bool) or ano < 1:
                ano = None
            status = filme.get("status")
            if status not in STATUS_CORES:
                status = "nao_assistido"
            url_imagem = filme.get("imagem_url", "")
            descricao = filme.get("descricao", "")
            filmes.append({
                "id": identificador,
                "nome": nome.strip()[:200],
                "imagem_url": (
                    url_imagem.strip()[:2048]
                    if _url_imagem_valida(url_imagem) else ""
                ),
                "descricao": (
                    descricao.strip()[:5000] if isinstance(descricao, str) else ""
                ),
                "ano": ano,
                "status": status,
            })
            ids.add(identificador)
        return filmes

    def _salvar_filmes(self, filmes):
        if self._erro_arquivo:
            QMessageBox.warning(self.app, "Filmes", self._erro_arquivo)
            return False
        temporario = ARQUIVO_FILMES + ".tmp"
        try:
            os.makedirs(APPDATA_DIR, exist_ok=True)
            with open(temporario, "w", encoding="utf-8") as arquivo:
                json.dump({"filmes": filmes}, arquivo, ensure_ascii=False, indent=2)
            os.replace(temporario, ARQUIVO_FILMES)
        except OSError as erro:
            try:
                if os.path.exists(temporario):
                    os.remove(temporario)
            except OSError:
                pass
            QMessageBox.warning(
                self.app, "Filmes",
                f"Não foi possível salvar a lista de filmes:\n{erro}",
            )
            return False
        self._filmes = filmes
        return True

    def _filmes_ordenados(self):
        if self._config["ordem"] == "status":
            prioridade_status = {
                "assistido": 0,
                "incompleto": 1,
                "nao_assistido": 2,
            }
            return sorted(
                self._filmes,
                key=lambda filme: (
                    prioridade_status[filme["status"]],
                    filme["nome"].casefold(),
                ),
            )
        if self._config["ordem"] == "cronologica":
            return sorted(
                self._filmes,
                key=lambda filme: (
                    filme["ano"] is None,
                    filme["ano"] if filme["ano"] is not None else 0,
                    filme["nome"].casefold(),
                ),
            )
        return sorted(self._filmes, key=lambda filme: filme["nome"].casefold())

    def _atualizar_lista(self, texto=None):
        consulta = (
            texto if texto is not None else self.busca.text()
        ).strip().casefold()
        filmes = [
            filme for filme in self._filmes_ordenados()
            if consulta in filme["nome"].casefold()
        ]
        self.lista.clear()
        for filme in filmes:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, filme["id"])
            item.setSizeHint(QSize(122, 22))
            self.lista.addItem(item)
            linha = NomeFilmeLabel(filme["nome"], self.lista)
            linha.atualizar_estilo(
                aplicar_css_fonte_base("cal_lista"),
                STATUS_CORES[filme["status"]],
                getattr(self.app, "borda_cor", None),
                getattr(self.app, "esp_borda", 0),
            )
            linha.clicado.connect(
                lambda identificador=filme["id"]: self._abrir_filme(identificador)
            )
            linha.mudar_status.connect(
                lambda identificador=filme["id"]: self._alternar_status(identificador)
            )
            linha.setToolTip(
                "Clique para ver detalhes · botão direito para alterar o status"
                "\nBranco: nunca assistido · verde: assistido"
                " · vermelho: não terminou"
            )
            self.lista.setItemWidget(item, linha)
        if filmes:
            self.lista.setFixedHeight(min(len(filmes), 4) * 22)
        else:
            self.lista.setFixedHeight(0)
        self.lista.setVisible(bool(filmes))

        if self._erro_arquivo:
            mensagem = "Erro na lista de filmes; o arquivo não foi alterado."
        elif filmes:
            mensagem = ""
        elif consulta:
            mensagem = "Filme não anotado. Use + para adicionar."
        else:
            mensagem = "Nenhum filme anotado."
        self.estado.setText(mensagem)
        self.estado.setVisible(bool(mensagem))
        self.botao_adicionar.setEnabled(not bool(self._erro_arquivo))

    def _atualizar_botao_limpar_busca(self, texto):
        self.busca.setClearButtonEnabled(bool(texto))

    def _abrir_adicao(self):
        dialogo = QDialog(self.app)
        dialogo.setWindowTitle("Adicionar filme")
        layout = QVBoxLayout(dialogo)
        formulario = QFormLayout()

        nome = QLineEdit(self.busca.text().strip())
        nome.setMaxLength(200)
        imagem_url = QLineEdit()
        imagem_url.setPlaceholderText("https://...")
        imagem_url.setMaxLength(2048)
        descricao = QTextEdit()
        descricao.setPlaceholderText("Descrição (opcional)")
        descricao.setMaximumHeight(100)
        ano = QSpinBox()
        ano.setRange(0, 9999)
        ano.setSpecialValueText("Sem ano")
        formulario.addRow("Nome:", nome)
        formulario.addRow("URL da imagem:", imagem_url)
        formulario.addRow("Descrição:", descricao)
        formulario.addRow("Ano:", ano)
        layout.addLayout(formulario)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        botao_excluir = botoes.addButton(
            "Excluir filme", QDialogButtonBox.ButtonRole.DestructiveRole
        )
        filme_excluido = False

        def excluir():
            resposta = QMessageBox.question(
                dialogo,
                "Excluir filme",
                f'Tem certeza que deseja excluir "{filme["nome"]}"?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if resposta != QMessageBox.StandardButton.Yes:
                return
            filmes = [
                dict(item) for item in self._filmes
                if item["id"] != identificador
            ]
            if not self._salvar_filmes(filmes):
                return
            nonlocal filme_excluido
            filme_excluido = True
            self._filme_atual_id = None
            self._atualizar_lista()
            self._esconder_painel()
            dialogo.accept()

        def confirmar():
            nome_final = nome.text().strip()
            url_final = imagem_url.text().strip()
            if not nome_final:
                QMessageBox.warning(
                    dialogo, "Adicionar filme", "Informe o nome do filme."
                )
                return
            if url_final and not _url_imagem_valida(url_final):
                QMessageBox.warning(
                    dialogo, "Adicionar filme",
                    "Informe uma URL de imagem HTTP ou HTTPS válida.",
                )
                return
            if any(
                filme["nome"].casefold() == nome_final.casefold()
                for filme in self._filmes
            ):
                QMessageBox.information(
                    dialogo, "Filme já anotado",
                    "Esse filme já está na lista. Pesquise pelo nome para abri-lo.",
                )
                return
            dialogo.accept()

        botoes.accepted.connect(confirmar)
        botoes.rejected.connect(dialogo.reject)
        layout.addWidget(botoes)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return

        nome_final = nome.text().strip()
        url_final = imagem_url.text().strip()

        novo_filme = {
            "id": uuid.uuid4().hex,
            "nome": nome_final[:200],
            "imagem_url": url_final[:2048],
            "descricao": descricao.toPlainText().strip()[:5000],
            "ano": ano.value() or None,
            "status": "nao_assistido",
        }
        if self._salvar_filmes(self._filmes + [novo_filme]):
            self.busca.setText(novo_filme["nome"])
            self._atualizar_lista()

    def _alternar_status(self, identificador):
        filmes = [dict(filme) for filme in self._filmes]
        filme = next(
            (item for item in filmes if item["id"] == identificador), None
        )
        if filme is None:
            return
        filme["status"] = STATUS_PROXIMO[filme["status"]]
        if not self._salvar_filmes(filmes):
            return
        for indice in range(self.lista.count()):
            item = self.lista.item(indice)
            if item.data(Qt.ItemDataRole.UserRole) != identificador:
                continue
            linha = self.lista.itemWidget(item)
            if linha is not None:
                linha.atualizar_estilo(
                    aplicar_css_fonte_base("cal_lista"),
                    STATUS_CORES[filme["status"]],
                    getattr(self.app, "borda_cor", None),
                    getattr(self.app, "esp_borda", 0),
                )
            break

    def _abrir_filme(self, identificador):
        filme = next(
            (item for item in self._filmes if item["id"] == identificador), None
        )
        if filme is None:
            return

        self._filme_atual_id = identificador
        possui_detalhes = bool(
            filme["imagem_url"] or filme["descricao"] or filme["ano"]
        )
        self.painel_filme.setFixedSize(150, 195 if possui_detalhes else 62)
        self.conteudo_detalhe.setVisible(possui_detalhes)
        self.pilha_detalhes.show()
        self.ano_filme.setVisible(filme["ano"] is not None)
        self.titulo_painel.setText(filme["nome"])
        self.ano_filme.setText(str(filme["ano"]) if filme["ano"] is not None else "")
        self.descricao_filme.setPlainText(
            filme["descricao"] or "Nenhuma descrição cadastrada."
        )
        self.pilha_detalhes.setCurrentWidget(self.imagem_filme)
        self.imagem_filme.clear()
        self.imagem_filme.setToolTip(
            "Clique para ver a descrição"
            if filme["descricao"] else
            "Nenhuma descrição cadastrada. Clique para voltar à imagem."
        )
        self._posicionar_painel()
        self._sincronizar_fundo_painel()
        self.painel_filme.show()
        self.painel_filme.raise_()
        self.painel_filme.layout().activate()
        self.pilha_detalhes.layout().activate()

        if possui_detalhes and filme["imagem_url"]:
            worker = WorkerImagemFilme(filme["imagem_url"])
            worker.concluido.connect(self.imagem_filme.receber_resultado)
            worker.finished.connect(
                lambda atual=worker: self._remover_worker_imagem(atual)
            )
            self._workers_imagem.append(worker)
            worker.start()

    def _alternar_descricao(self):
        if self._filme_atual_id is None:
            return
        if self.pilha_detalhes.currentWidget() is self.imagem_filme:
            self.pilha_detalhes.setCurrentWidget(self.descricao_filme)
        else:
            self.pilha_detalhes.setCurrentWidget(self.imagem_filme)

    def _editar_filme_atual(self):
        identificador = self._filme_atual_id
        filme = next(
            (item for item in self._filmes if item["id"] == identificador), None
        )
        if filme is None:
            return

        dialogo = QDialog(self.app)
        dialogo.setWindowTitle("Editar filme")
        layout = QVBoxLayout(dialogo)
        formulario = QFormLayout()
        nome = QLineEdit(filme["nome"])
        nome.setMaxLength(200)
        imagem_url = QLineEdit(filme["imagem_url"])
        imagem_url.setMaxLength(2048)
        descricao = QTextEdit()
        descricao.setPlainText(filme["descricao"])
        descricao.setMaximumHeight(100)
        ano = QSpinBox()
        ano.setRange(0, 9999)
        ano.setSpecialValueText("Sem ano")
        ano.setValue(filme["ano"] or 0)
        formulario.addRow("Nome:", nome)
        formulario.addRow("URL da imagem:", imagem_url)
        formulario.addRow("Descrição:", descricao)
        formulario.addRow("Ano:", ano)
        layout.addLayout(formulario)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        botao_excluir = botoes.addButton(
            "Excluir filme", QDialogButtonBox.ButtonRole.DestructiveRole
        )
        filme_excluido = False

        def excluir():
            resposta = QMessageBox.question(
                dialogo,
                "Excluir filme",
                f'Tem certeza que deseja excluir "{filme["nome"]}"?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if resposta != QMessageBox.StandardButton.Yes:
                return
            filmes = [
                dict(item) for item in self._filmes
                if item["id"] != identificador
            ]
            if not self._salvar_filmes(filmes):
                return
            nonlocal filme_excluido
            filme_excluido = True
            self._filme_atual_id = None
            self._atualizar_lista()
            self._esconder_painel()
            dialogo.accept()

        def confirmar():
            nome_final = nome.text().strip()
            url_final = imagem_url.text().strip()
            if not nome_final:
                QMessageBox.warning(
                    dialogo, "Editar filme", "Informe o nome do filme."
                )
                return
            if url_final and not _url_imagem_valida(url_final):
                QMessageBox.warning(
                    dialogo, "Editar filme",
                    "Informe uma URL de imagem HTTP ou HTTPS válida.",
                )
                return
            if any(
                outro["id"] != identificador
                and outro["nome"].casefold() == nome_final.casefold()
                for outro in self._filmes
            ):
                QMessageBox.information(
                    dialogo, "Filme já anotado",
                    "Já existe outro filme com esse nome.",
                )
                return
            dialogo.accept()

        botoes.accepted.connect(confirmar)
        botoes.rejected.connect(dialogo.reject)
        botao_excluir.clicked.connect(excluir)
        layout.addWidget(botoes)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        if filme_excluido:
            return

        filmes = [dict(item) for item in self._filmes]
        filme_atualizado = next(
            item for item in filmes if item["id"] == identificador
        )
        filme_atualizado.update({
            "nome": nome.text().strip()[:200],
            "imagem_url": imagem_url.text().strip()[:2048],
            "descricao": descricao.toPlainText().strip()[:5000],
            "ano": ano.value() or None,
        })
        if self._salvar_filmes(filmes):
            self._atualizar_lista()
            self._abrir_filme(identificador)

    def _posicionar_painel(self):
        area = self.app.container.geometry()
        posicao = self.app.mapToGlobal(area.topLeft())
        x = posicao.x() + (area.width() - self.painel_filme.width()) // 2
        y = posicao.y() - self.painel_filme.height() - 10
        self.painel_filme.move(x, y)
        if self.painel_filme.isVisible():
            self._atualizar_vidro_painel()

    def _sincronizar_fundo_painel(self):
        self.painel_filme.overlay_color = self.app.container.overlay_color
        self.painel_filme.border_color = self.app.container.border_color
        self.painel_filme.border_radius = self.app.container.border_radius
        self.painel_filme.bg_pixmap = self.app.container.bg_pixmap
        self.painel_filme.update()
        if self.painel_filme.isVisible():
            self._atualizar_vidro_painel()

    def _atualizar_vidro_painel(self):
        atualizar_vidro(self.painel_filme, self.painel_filme)

    def _restaurar_painel_ativo(self):
        if not self.painel_filme.isVisible() or not (
            self.app.isActiveWindow() or self.painel_filme.isActiveWindow()
        ):
            return
        self._sincronizar_fundo_painel()
        self.painel_filme.raise_()
        atualizar_vidro(self.painel_filme, self.painel_filme, forcar_blur=True)

    def _esconder_painel(self):
        self.painel_filme.hide()
        esconder_vidro(self.painel_filme)

    def _remover_worker_imagem(self, worker):
        if worker in self._workers_imagem:
            self._workers_imagem.remove(worker)
        worker.deleteLater()

    def encerrar(self):
        self.app.removeEventFilter(self._filtro_janela)
        self.painel_filme.removeEventFilter(self._filtro_janela)
        self.page.removeEventFilter(self._filtro_janela)
        self._esconder_painel()
        self.painel_filme.deleteLater()
        self._filtro_janela.deleteLater()
        for worker in self._workers_imagem:
            if worker.isRunning():
                worker.wait(7000)
        return not any(worker.isRunning() for worker in self._workers_imagem)
