import os
import sys
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QCheckBox, QLabel, QSlider, QHBoxLayout, 
    QPushButton, QComboBox, QWidget, QStackedWidget, QGridLayout, QScrollArea, QApplication, QMessageBox, QInputDialog
)
from PyQt6.QtCore import Qt, QEvent

from config import (
    config_app, APP_VERSION, PASTA_WALLPAPERS, 
    NIVEIS_DESFOQUE, NIVEIS_ESPESSURA, indice_desfoque, indice_espessura
)
from utils import (
    raio_desfoque, normalizar_cor_hex, aplicar_css_fonte_base, alpha_desfoque
)
from ui_components import BlurredBackgroundFrame, OutlineLabel, ClickableMes, ClickableLabel

class JanelaConfiguracoes(QDialog):
    def __init__(self, parent_widget):
        super().__init__(parent_widget)
        self.parent_widget = parent_widget
        self.setWindowTitle("Configurações")
        self.setFixedWidth(300)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        
        layout = QVBoxLayout(self)
        
        self.check_tema = QCheckBox("Modo Claro")
        self.check_tema.setChecked(config_app.modo_claro)
        
        self.check_windows = QCheckBox("Iniciar junto com o Windows")
        self.check_windows.setChecked(config_app.iniciar_com_windows)
        
        self.check_plano = QCheckBox("Ao fechar, manter em 2º plano")
        self.check_plano.setChecked(config_app.segundo_plano)
        
        self.check_topo = QCheckBox("Sempre no topo")
        self.check_topo.setChecked(config_app.sempre_no_topo)

        self.check_tempo_atalhos = QCheckBox("Contabilizar tempo dos atalhos")
        self.check_tempo_atalhos.setChecked(config_app.monitorar_tempo_atalhos)

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
        
        self.lbl_versao = QLabel(f"Versão atual: {APP_VERSION}")
        self.lbl_versao.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_update = QPushButton("Verificar Atualizações")
        self.btn_update.clicked.connect(lambda: self.parent_widget.verificar_atualizacoes(manual=True))
        
        layout.addWidget(self.check_tema)
        layout.addWidget(self.check_windows)
        layout.addWidget(self.check_plano)
        layout.addWidget(self.check_topo)
        layout.addWidget(self.check_tempo_atalhos)
        layout.addWidget(self.lbl_tempo_parabens)
        layout.addWidget(self.slider_tempo_parabens)
        layout.addSpacing(10)
        layout.addLayout(layout_wp_top)
        layout.addWidget(self.combo_wp)
        layout.addWidget(self.lbl_blur)
        layout.addWidget(self.slider_blur)
        layout.addWidget(self.lbl_espessura)
        layout.addWidget(self.slider_esp)
        layout.addSpacing(5)
        layout.addWidget(self.preview_frame, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
        layout.addWidget(self.lbl_versao)
        layout.addWidget(self.btn_update)
        
        self.check_tema.toggled.connect(self.atualizar_preview)
        self.combo_wp.currentTextChanged.connect(self.atualizar_preview)
        self.slider_blur.valueChanged.connect(self.atualizar_preview)
        self.slider_esp.valueChanged.connect(self.atualizar_preview)
        
        self.atualizar_preview()

    def atualizar_label_tempo_parabens(self):
        self.lbl_tempo_parabens.setText(f"Duração da tela de Parabéns: {self.slider_tempo_parabens.value()}s")

    def atualizar_preview(self):
        claro = self.check_tema.isChecked()
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
            overlay = (245, 245, 245, 180) if claro else (25, 25, 25, 175)
            border = (255, 255, 255, 200) if claro else (255, 255, 255, 50)
        self.preview_frame.update_background(wp_path, raio_desfoque(blur_percent), overlay, border, 12, modo_claro=claro)

    def closeEvent(self, event):
        config_app.modo_claro = self.check_tema.isChecked()
        config_app.iniciar_com_windows = self.check_windows.isChecked()
        config_app.segundo_plano = self.check_plano.isChecked()
        config_app.sempre_no_topo = self.check_topo.isChecked()
        config_app.monitorar_tempo_atalhos = self.check_tempo_atalhos.isChecked()
        config_app.tempo_parabens = self.slider_tempo_parabens.value()
        config_app.wallpaper = self.combo_wp.currentText()
        config_app.desfoque = NIVEIS_DESFOQUE[self.slider_blur.value()]
        config_app.espessura_borda = NIVEIS_ESPESSURA[self.slider_esp.value()]
        config_app.salvar()
        config_app.aplicar_registro_windows()

        self.parent_widget.aplicar_sempre_no_topo()
        self.parent_widget.aplicar_tema()


class JanelaCalendario(QWidget):
    def __init__(self, main_app):
        super().__init__()
        self.main_app = main_app
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(150)
        
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
        self.lbl_titulo_mes = OutlineLabel("Mês")
        self.lbl_titulo_mes.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_list.addWidget(self.lbl_titulo_mes)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background: transparent; border: none;")
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent;")
        self.layout_nomes = QVBoxLayout(self.scroll_content)
        self.layout_nomes.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.scroll_content)

        for widget in (self.page_grid, self.page_list, self.lbl_titulo_mes, self.scroll, self.scroll.viewport(), self.scroll_content):
            widget.installEventFilter(self)
        for lbl in self.labels_meses:
            lbl.installEventFilter(self)
        
        layout_list.addLayout(top_list)
        layout_list.addWidget(self.scroll)
        
        self.stacked.addWidget(self.page_grid)
        self.stacked.addWidget(self.page_list)
        self.resize(150, 140)

        self.dados = []
        self.cor_texto = "#ffffff"
        self.borda_cor = None
        self.esp_borda = 0

    def abrir_mes(self, mes_num):
        for i in reversed(range(self.layout_nomes.count())): 
            w = self.layout_nomes.itemAt(i).widget()
            if w: w.setParent(None)
            
        aniversariantes = []
        for item in self.dados:
            try:
                nome, data_str = item[0], item[1]
                cor_nome = item[2] if len(item) >= 3 else "#ffffff"
                d, m = map(int, data_str.split('/'))
                if m == mes_num:
                    aniversariantes.append((nome, d, normalizar_cor_hex(cor_nome)))
            except Exception:
                pass
            
        aniversariantes.sort(key=lambda x: x[1])
        self.lbl_titulo_mes.setText(f"{self.meses_nomes[mes_num-1]}")
        self.lbl_titulo_mes.atualizar_estilo(aplicar_css_fonte_base("cal_titulo"), self.cor_texto, self.borda_cor, self.esp_borda)
        
        if not aniversariantes:
            vazio = OutlineLabel("Sem aniversários")
            vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vazio.atualizar_estilo(aplicar_css_fonte_base("cal_lista"), self.cor_texto, self.borda_cor, self.esp_borda)
            self.layout_nomes.addWidget(vazio)
            vazio.installEventFilter(self)
        else:
            for nome, dia, cor in aniversariantes:
                lbl = OutlineLabel(f"{nome} - {dia}")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.atualizar_estilo(aplicar_css_fonte_base("cal_lista"), cor, self.borda_cor, self.esp_borda)
                self.layout_nomes.addWidget(lbl)
                lbl.installEventFilter(self)
                
        self.stacked.setCurrentIndex(1)
        self.main_app.reiniciar_timer_calendario()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self.main_app.reiniciar_timer_calendario()
            if self.stacked.currentIndex() == 1:
                self.stacked.setCurrentIndex(0)
                return True
        return super().eventFilter(obj, event)

    def atualizar_dados(self, dados, cor_texto, overlay_color, border_color, wp_path, blur, borda_cor=None, esp_borda=0, modo_claro=False):
        self.dados = dados
        self.cor_texto = cor_texto
        self.borda_cor = borda_cor
        self.esp_borda = esp_borda
        self.container.update_background(wp_path, blur, overlay_color, border_color, 12, modo_claro=modo_claro)
        
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

