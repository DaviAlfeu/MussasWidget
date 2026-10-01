import os
import sys
import time
import webbrowser
from datetime import date, datetime, timedelta

from PyQt6.QtWidgets import QWidget, QLabel, QFrame, QPushButton
from PyQt6.QtCore import Qt, QTimer, QUrl, QPoint, QSize
from PyQt6.QtCore import QPropertyAnimation, QParallelAnimationGroup, QEasingCurve, QAbstractAnimation
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

# Imports do projeto
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"
))
from config import config_app, STATE_FILE, CONFIG_FONTES
from utils import resource_path, external_resource_path, aplicar_css_fonte_base, normalizar_cor_hex, parse_data_jogo_bg
from ui_components import OutlineLabel, ClickableLabel
from workers import WorkerDownload

try:
    from gerenciador_modulos import PluginBase
except ImportError:
    class PluginBase:
        nome = "Plugin"
        versao = "1.0.0"
        def __init__(self, app): self.app = app
        def criar_pagina(self): return None
        def botoes_topo(self): return []
        def ao_aplicar_tema(self): pass
        def ao_baixar_dados(self, *args): pass


class Plugin(PluginBase):
    nome = "Aniversários"
    versao = "1.0.0"

    def __init__(self, app):
        super().__init__(app)

        # Estado interno
        self.dados_planilha = []
        self.dados_jogo = [{"imagem": "", "link": ""}, {"imagem": "", "link": ""}]
        self.data_inicio_jogo = None
        self.data_fim_jogo = None
        self.aniversario_pulado = False
        self.mostrando_parabens = False
        self.aniversario_animacao_pronta = False
        self.aniversario_animacao_executada = False
        self.animacao_parabens = None
        self.calendario_aberto = False
        self.janela_calendario = None

        # Áudio
        self.player = QMediaPlayer(app)
        self.audio_output = QAudioOutput(app)
        self.player.setAudioOutput(self.audio_output)
        for ext in ['.wav', '.mp3', '.ogg']:
            audio_path = external_resource_path("assets/parabens" + ext)
            if os.path.exists(audio_path):
                self.player.setSource(QUrl.fromLocalFile(audio_path))
                break

        # Página de aniversários
        self.page_aniv = QWidget(app.pages_container)
        self.page_aniv.setGeometry(0, 0, 150, 150)
        self.page_aniv.hide()

        self.nome_label = OutlineLabel("Carregando...", self.page_aniv)
        self.nome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.data_label = OutlineLabel("aguarde", self.page_aniv)
        self.data_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.linha_meio = QFrame(self.page_aniv)
        self.linha_meio.setStyleSheet("background-color: rgba(120, 120, 120, 80); border: none;")
        self.icone_label = QLabel(self.page_aniv)
        pix = QPixmap(resource_path("assets/calendar.png"))
        if not pix.isNull():
            self.icone_label.setPixmap(pix.scaled(15, 15, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self.icone_label.setText("📅")
        self.icone_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icone_label.setFixedSize(20, 20)
        self.faltam_label = OutlineLabel("Faltam", self.page_aniv)
        self.faltam_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dias_label = OutlineLabel("...", self.page_aniv)
        self.dias_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Posicionar elementos da página de aniversários
        self.nome_label.setGeometry(10, 16, 130, 21)
        self.data_label.setGeometry(10, 36, 130, 16)
        self.linha_meio.setGeometry(0, 72, 150, 1)
        self.icone_label.move((150 - 20) // 2, 62)
        self.icone_label.raise_()
        self.faltam_label.setGeometry(10, 95, 130, 16)
        self.dias_label.setGeometry(10, 105, 130, 28)

        # Página de jogos
        self.page_jogo = QWidget(app.pages_container)
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

        # Timers
        self.timer_jogo = QTimer(app)
        self.timer_jogo.timeout.connect(self.atualizar_timer_jogo)
        self.timer_jogo.start(1000)

        self.timer_skip = QTimer(app)
        self.timer_skip.setSingleShot(True)
        self.timer_skip.timeout.connect(lambda: (setattr(self, 'aniversario_pulado', True), self.atualizar_interface_aniversario()))

        QTimer.singleShot(3000, self.liberar_animacao_aniversario)

        self.pulse_timer = QTimer(app)
        self.pulse_timer.timeout.connect(self.animar_emoji)
        self.pulse_size = 18
        self.pulse_dir = 1

        self.timer_internet = QTimer(app)
        self.timer_internet.timeout.connect(self.baixar_dados)
        self.timer_internet.start(60 * 60 * 1000)

        self.timer_tela = QTimer(app)
        self.timer_tela.timeout.connect(self.atualizar_interface_aniversario)
        self.timer_tela.start(60 * 1000)

        # Calendário
        from dialogs import JanelaCalendario
        self.janela_calendario = JanelaCalendario(app)
        self.timer_calendario_autoclose = QTimer(app)
        self.timer_calendario_autoclose.setSingleShot(True)
        self.timer_calendario_autoclose.timeout.connect(self._fechar_calendario_inatividade)

        # Referência para o app principal saber que o calendário existe
        app.calendario_aberto = False
        app.janela_calendario = self.janela_calendario

        # Baixar dados na inicialização
        QTimer.singleShot(100, self.baixar_dados)

    def criar_pagina(self):
        # Registramos as 2 páginas manualmente
        # A página de aniversários deve ser a PRIMEIRA (antes dos atalhos)
        idx_aniv = self.app.registrar_pagina(
            self.page_aniv, posicao=0, chave="aniversarios", nome="Aniversários"
        )
        idx_jogo = self.app.registrar_pagina(
            self.page_jogo, posicao=1, chave="jogos", nome="Jogos"
        )
        self._idx_aniv = idx_aniv
        self._idx_jogo = idx_jogo
        return None  # Já registramos manualmente

    def ao_mudar_area_pagina(self, area):
        x, y, largura, altura = area
        margem = 4
        largura_util = max(1, largura - margem * 2)
        self.nome_label.setGeometry(x + margem, y + 3, largura_util, 21)
        self.data_label.setGeometry(x + margem, y + 24, largura_util, 16)
        linha_y = y + int(altura * 0.43)
        self.linha_meio.setGeometry(x + margem, linha_y, largura_util, 1)
        self.icone_label.move(
            x + (largura - self.icone_label.width()) // 2, linha_y - 10
        )
        self.faltam_label.setGeometry(
            x + margem, y + int(altura * 0.62), largura_util, 16
        )
        self.dias_label.setGeometry(
            x + margem, y + int(altura * 0.72), largura_util,
            max(20, altura - int(altura * 0.74))
        )

        largura_coluna = max(1, largura // 2)
        tamanho_botao = min(65, largura_coluna - margem * 2, altura - 34)
        y_botao = y + altura - tamanho_botao - margem
        self.timer_jogo_label.setGeometry(x + margem, y + 2, largura_util, 24)
        self.img_label_jogo1.setGeometry(x, y + 26, largura_coluna, altura - 26)
        self.img_label_jogo2.setGeometry(
            x + largura_coluna, y + 26, largura - largura_coluna, altura - 26
        )
        self.btn_clique_jogo1.setGeometry(
            x + (largura_coluna - tamanho_botao) // 2, y_botao,
            tamanho_botao, tamanho_botao
        )
        coluna_direita = largura - largura_coluna
        self.btn_clique_jogo2.setGeometry(
            x + largura_coluna + (coluna_direita - tamanho_botao) // 2,
            y_botao, tamanho_botao, tamanho_botao
        )

    def botoes_topo(self):
        return [
            {"nome_png": "refresh.png", "texto_fallback": "🔄", "callback": self.baixar_dados, "posicao": 0},
            {"nome_png": "list.png", "texto_fallback": "📅", "callback": self.toggle_calendario, "posicao": 1},
        ]

    def ao_aplicar_tema(self):
        app = self.app
        self.atualizar_interface_aniversario()
        if self.img_label_jogo1.text() == "...":
            self.img_label_jogo1.atualizar_estilo(aplicar_css_fonte_base("nome"), app.cor_texto, app.borda_cor, app.esp_borda)
        if self.img_label_jogo2.text() == "...":
            self.img_label_jogo2.atualizar_estilo(aplicar_css_fonte_base("nome"), app.cor_texto, app.borda_cor, app.esp_borda)
        self.atualizar_timer_jogo()
        if self.calendario_aberto:
            from config import PASTA_WALLPAPERS
            from utils import raio_desfoque
            wp_path = "Nenhum"
            if config_app.wallpaper != "Nenhum":
                caminho_wp = os.path.join(PASTA_WALLPAPERS, config_app.wallpaper)
                if os.path.exists(caminho_wp):
                    wp_path = caminho_wp
            tem_wp = (wp_path != "Nenhum")
            if tem_wp:
                if config_app.modo_claro:
                    overlay = (255, 255, 255, 25)
                    border = (0, 0, 0, 100)
                else:
                    overlay = (0, 0, 0, 25)
                    border = (255, 255, 255, 100)
            else:
                if config_app.modo_claro:
                    overlay = (245, 245, 245, 180)
                    border = (255, 255, 255, 200)
                else:
                    overlay = (25, 25, 25, 175)
                    border = (255, 255, 255, 50)
            self.janela_calendario.atualizar_dados(
                self.dados_planilha, app.cor_texto, overlay, border, wp_path,
                raio_desfoque(config_app.desfoque), borda_cor=app.borda_cor, esp_borda=app.esp_borda, modo_claro=config_app.modo_claro
            )

    def ao_baixar_dados(self, *args):
        pass  # We handle our own download

    # ---- Downloads ----

    def baixar_dados(self):
        if hasattr(self, '_worker') and self._worker.isRunning():
            return
        self._worker = WorkerDownload()
        self._worker.resultado.connect(self._processar_dados)
        self._worker.start()

    def _processar_dados(self, plan, jogo, data_ini, data_fim, img1, img2):
        self.dados_planilha = plan
        self.dados_jogo = jogo
        self.data_inicio_jogo = data_ini
        self.data_fim_jogo = data_fim
        self._carregar_imagem_bytes(img1, self.img_label_jogo1)
        self._carregar_imagem_bytes(img2, self.img_label_jogo2)
        self.atualizar_interface_aniversario()
        if self.calendario_aberto:
            self.ao_aplicar_tema()

    def _carregar_imagem_bytes(self, dados_bytes, label):
        if not dados_bytes:
            label.clear()
            label.setText("...")
            label.atualizar_estilo(aplicar_css_fonte_base("nome"), self.app.cor_texto, self.app.borda_cor, self.app.esp_borda)
            return
        pix = QPixmap()
        pix.loadFromData(dados_bytes)
        label.setPixmap(pix.scaled(65, 65, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    # ---- Timer Jogo ----

    def atualizar_timer_jogo(self):
        if self.data_fim_jogo is None:
            self.timer_jogo_label.setText("")
            return
        agora = datetime.now()
        if self.data_inicio_jogo and agora < self.data_inicio_jogo:
            restante = self.data_inicio_jogo - agora
            texto = "Começa em " + self._formatar_tempo_jogo(restante)
        else:
            restante = self.data_fim_jogo - agora
            if restante.total_seconds() <= 0:
                texto = "Encerrado"
            else:
                texto = self._formatar_tempo_jogo(restante)
        self.timer_jogo_label.setText(texto)
        self.timer_jogo_label.atualizar_estilo(aplicar_css_fonte_base("cal_titulo"), self.app.cor_texto, self.app.borda_cor, self.app.esp_borda)

    def _formatar_tempo_jogo(self, restante):
        total = max(0, int(restante.total_seconds()))
        dias, resto = divmod(total, 86400)
        horas, resto = divmod(resto, 3600)
        minutos, segundos = divmod(resto, 60)
        if dias:
            return f"{dias}d {horas:02d}:{minutos:02d}:{segundos:02d}"
        return f"{horas:02d}:{minutos:02d}:{segundos:02d}"

    def abrir_link_jogo(self, setor_idx):
        link = self.dados_jogo[setor_idx].get("link", "")
        if link:
            webbrowser.open(link)

    # ---- Aniversário ----

    def pular_tela_parabens(self):
        if not self.mostrando_parabens or self.aniversario_pulado:
            return
        self.timer_skip.stop()
        self.aniversario_pulado = True
        self.atualizar_interface_aniversario()

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
        anim_nome = QPropertyAnimation(self.nome_label, b"pos", self.app)
        anim_nome.setDuration(700)
        anim_nome.setStartValue(pos_nome_inicial)
        anim_nome.setEndValue(pos_nome_final)
        anim_nome.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim_data = QPropertyAnimation(self.data_label, b"pos", self.app)
        anim_data.setDuration(700)
        anim_data.setStartValue(pos_data_inicial)
        anim_data.setEndValue(pos_data_final)
        anim_data.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animacao_parabens = QParallelAnimationGroup(self.app)
        self.animacao_parabens.addAnimation(anim_nome)
        self.animacao_parabens.addAnimation(anim_data)
        self.animacao_parabens.start()

    def atualizar_interface_aniversario(self):
        if not self.dados_planilha:
            return
        app = self.app
        hoje = date.today()
        proximo_aniv, menor_diferenca = None, 99999
        for item in self.dados_planilha:
            try:
                nome, data_str = item[0], item[1]
                cor_nome = normalizar_cor_hex(item[2] if len(item) >= 3 else "")
                d, m = map(int, data_str.split('/'))
                aniv = date(hoje.year, m, d)
                if aniv < hoje:
                    aniv = date(hoje.year + 1, m, d)
                dias = (aniv - hoje).days
                if dias == 0 and self.aniversario_pulado:
                    continue
                if dias < menor_diferenca:
                    menor_diferenca, proximo_aniv = dias, (nome, d, m, dias, cor_nome)
            except Exception:
                pass

        if proximo_aniv:
            nome, dia, mes, dias, cor_nome = proximo_aniv
            meses = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                     "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

            if dias == 0:
                self.mostrando_parabens = True
                self.pulse_timer.start(50)
                self.nome_label.setText("Parabéns")
                self.nome_label.atualizar_estilo(aplicar_css_fonte_base("parabens_titulo"), app.cor_texto, app.borda_cor, app.esp_borda)
                self.data_label.setText(f"{nome}!")
                self.data_label.atualizar_estilo(aplicar_css_fonte_base("parabens_nome"), "#d90f0f", app.borda_cor, app.esp_borda)
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
                if not self._ja_tocou_hoje():
                    self.player.play()
                    self._marcar_como_tocado()
                if not self.aniversario_pulado and not self.timer_skip.isActive():
                    self.timer_skip.start(config_app.tempo_parabens * 1000)
            else:
                self.mostrando_parabens = False
                self.pulse_timer.stop()
                if self.animacao_parabens and self.animacao_parabens.state() == QAbstractAnimation.State.Running:
                    self.animacao_parabens.stop()
                self.nome_label.move(10, 16)
                self.data_label.move(10, 36)
                self.nome_label.show()
                self.data_label.show()
                self.nome_label.setText(nome)
                self.nome_label.atualizar_estilo(aplicar_css_fonte_base("nome"), cor_nome, app.borda_cor, app.esp_borda)
                self.data_label.setText(f"{dia} de {meses[mes]}")
                self.data_label.atualizar_estilo(aplicar_css_fonte_base("data"), app.cor_texto, app.borda_cor, app.esp_borda)
                self.faltam_label.setText("Faltam")
                self.faltam_label.atualizar_estilo(aplicar_css_fonte_base("faltam"), app.cor_texto, app.borda_cor, app.esp_borda)
                self.dias_label.setText("1 dia" if dias == 1 else f"{dias} dias")
                self.dias_label.atualizar_estilo(aplicar_css_fonte_base("dias"), app.cor_texto, app.borda_cor, app.esp_borda)

    def _ja_tocou_hoje(self):
        try:
            with open(STATE_FILE, "r") as f:
                return f.read().strip() == date.today().isoformat()
        except Exception:
            return False

    def _marcar_como_tocado(self):
        try:
            with open(STATE_FILE, "w") as f:
                f.write(date.today().isoformat())
        except Exception:
            pass

    def animar_emoji(self):
        self.pulse_size += self.pulse_dir
        if self.pulse_size >= 24:
            self.pulse_dir = -1
        elif self.pulse_size <= 14:
            self.pulse_dir = 1
        css = aplicar_css_fonte_base("dias")
        css = css.replace(f"font-size: {CONFIG_FONTES['dias']['tamanho']}px", f"font-size: {self.pulse_size}px")
        self.dias_label.atualizar_estilo(css, self.app.cor_texto, self.app.borda_cor, self.app.esp_borda)

    # ---- Calendário ----

    def toggle_calendario(self):
        self.calendario_aberto = not self.calendario_aberto
        self.app.calendario_aberto = self.calendario_aberto
        if self.calendario_aberto:
            self.ao_aplicar_tema()
            self.janela_calendario.move(self.app.x() + 24, self.app.y() + self.app.height() + 5)
            self.janela_calendario.stacked.setCurrentIndex(0)
            self.janela_calendario.show()
            self._reiniciar_timer_calendario()
        else:
            self.janela_calendario.hide()
            self.timer_calendario_autoclose.stop()

    def _reiniciar_timer_calendario(self):
        if self.calendario_aberto and self.janela_calendario.isVisible():
            self.timer_calendario_autoclose.start(10000)

    def _fechar_calendario_inatividade(self):
        self.calendario_aberto = False
        self.app.calendario_aberto = False
        self.janela_calendario.hide()
