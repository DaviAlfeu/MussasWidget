import os
from PyQt6.QtWidgets import QLabel, QFrame, QGraphicsScene, QGraphicsBlurEffect
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QPainter, QPainterPath, QColor, QImage, QPen, QPixmap, QFontMetrics, QFont

COR_BASE_CLARO = "#f5f5f5"
COR_BASE_ESCURO = "#191919"


class OutlineLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.borda_cor = None
        self.espessura = 0.0
        self.cor_texto = "#ffffff"

    def atualizar_estilo(self, css_base, cor_texto, borda_cor, espessura):
        self.setStyleSheet(css_base + f" color: {cor_texto};")
        self.cor_texto = cor_texto
        self.borda_cor = borda_cor
        try: self.espessura = float(espessura)
        except (TypeError, ValueError): self.espessura = 0.0
        self.update()

    def paintEvent(self, event):
        if not self.borda_cor or self.espessura <= 0:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = self.font(); painter.setFont(font)
        rect = self.rect(); text = self.text(); align = self.alignment()
        metrics = painter.fontMetrics(); text_width = metrics.horizontalAdvance(text)
        if align & Qt.AlignmentFlag.AlignHCenter: x = rect.x() + (rect.width() - text_width) / 2.0
        elif align & Qt.AlignmentFlag.AlignRight: x = rect.right() - text_width
        else: x = rect.x()
        y = rect.y() + (rect.height() + metrics.ascent() - metrics.descent()) / 2.0
        path = QPainterPath(); path.addText(x, y, font, text)
        pen = QPen(QColor(self.borda_cor)); pen.setWidthF(self.espessura); pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.strokePath(path, pen)
        painter.setPen(QColor(self.cor_texto))
        flags = int(align.value) if hasattr(align, 'value') else int(align)
        if self.wordWrap(): flags |= Qt.TextFlag.TextWordWrap.value
        painter.drawText(rect, flags, text)
        painter.end()

class BlurredBackgroundFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.bg_pixmap = None
        self.overlay_color = QColor(25, 25, 25, 175)
        self.border_color = QColor(255, 255, 255, 50)
        self.border_radius = 12

    def update_background(self, image_path, blur_radius, overlay_color, border_color, border_radius=12, modo_claro=False, cor_base=None):
        self.border_color = QColor(0, 0, 0, 0)
        self.border_radius = border_radius
        w, h = max(self.width(), 100), max(self.height(), 100)
        
        tem_wp = image_path and os.path.exists(image_path) and image_path != "Nenhum"

        if tem_wp:
            self.overlay_color = QColor(*overlay_color) if isinstance(overlay_color, tuple) else QColor(overlay_color)
            pix = QPixmap(image_path)
            if not pix.isNull():
                pix = pix.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                if blur_radius > 0:
                    scene = QGraphicsScene()
                    item = scene.addPixmap(pix)
                    blur = QGraphicsBlurEffect()
                    blur.setBlurRadius(blur_radius)
                    item.setGraphicsEffect(blur)
                    
                    img = QImage(pix.size(), QImage.Format.Format_ARGB32_Premultiplied)
                    img.fill(Qt.GlobalColor.transparent)
                    p = QPainter(img)
                    scene.render(p)
                    p.end()
                    self.bg_pixmap = QPixmap.fromImage(img)
                else:
                    self.bg_pixmap = pix
        else:
            self.bg_pixmap = None
            base_color = QColor(cor_base or (COR_BASE_CLARO if modo_claro else COR_BASE_ESCURO))
            alpha = 30 + int((blur_radius / 50.0) * 225)
            base_color.setAlpha(alpha)
            self.overlay_color = base_color

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), self.border_radius, self.border_radius)
        painter.setClipPath(path)
        
        if self.bg_pixmap:
            x, y = (self.width() - self.bg_pixmap.width()) // 2, (self.height() - self.bg_pixmap.height()) // 2
            painter.drawPixmap(x, y, self.bg_pixmap)
            
        painter.fillPath(path, self.overlay_color)
        if self.border_color.alpha() > 0:
            pen = QPen(self.border_color)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawPath(path)

class ClickableLabel(OutlineLabel):
    clicked = pyqtSignal()
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

class ClickableMes(OutlineLabel):
    clicked = pyqtSignal(int)
    def __init__(self, text, index):
        super().__init__(text)
        self.index = index
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.index)


def _desenhar_texto_contorno(painter, font, x, y, texto, cor_texto, borda_cor, espessura):
    if borda_cor and espessura > 0:
        path = QPainterPath()
        path.addText(x, y, font, texto)
        pen = QPen(QColor(borda_cor))
        pen.setWidthF(espessura)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.strokePath(path, pen)
    painter.setPen(QColor(cor_texto))
    painter.setFont(font)
    painter.drawText(int(x), int(y), texto)


class MarqueeLabel(OutlineLabel):
    """Texto de largura fixa que rola de lado quando não cabe."""
    clicked = pyqtSignal()

    def __init__(self, text="", parent=None, clicavel=False):
        super().__init__(text, parent)
        self._clicavel = clicavel
        self._offset = 0.0
        self._pausa = 0
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._passo)

    def setText(self, texto):
        super().setText(texto)
        self._reiniciar()

    def atualizar_estilo(self, css_base, cor_texto, borda_cor, espessura):
        super().atualizar_estilo(css_base, cor_texto, borda_cor, espessura)
        self._reiniciar()

    def _largura_texto(self):
        return self.fontMetrics().horizontalAdvance(self.text())

    def _excesso(self):
        return self._largura_texto() - self.width() + 6

    def _reiniciar(self):
        self._offset = 0.0
        self._pausa = 35
        if self._excesso() > 0 and self.isVisible():
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self._reiniciar()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reiniciar()

    def _passo(self):
        excesso = self._excesso()
        if excesso <= 0:
            self._timer.stop()
            return
        if self._pausa > 0:
            self._pausa -= 1
            if self._pausa == 0 and self._offset >= excesso:
                self._offset = 0.0
                self._pausa = 35
        else:
            self._offset += 1.0
            if self._offset >= excesso:
                self._offset = float(excesso)
                self._pausa = 35
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = self.font()
        painter.setFont(font)
        metrics = painter.fontMetrics()
        largura = self._largura_texto()
        if self._excesso() > 0:
            x = 3 - self._offset
        else:
            x = (self.width() - largura) / 2.0
        y = (self.height() + metrics.ascent() - metrics.descent()) / 2.0
        _desenhar_texto_contorno(
            painter, font, x, y, self.text(), self.cor_texto, self.borda_cor, self.espessura
        )
        painter.end()

    def mousePressEvent(self, event):
        if self._clicavel and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        else:
            super().mousePressEvent(event)


class WrapLabel(OutlineLabel):
    """Texto centralizado que quebra em linhas, encolhe se preciso e ajusta a própria altura."""
    clicked = pyqtSignal()

    def __init__(self, text="", parent=None, clicavel=False):
        super().__init__(text, parent)
        self._clicavel = clicavel
        self._escala = 1.0

    def _fonte_efetiva(self):
        fonte = QFont(self.font())
        if self._escala != 1.0:
            if fonte.pixelSize() > 0:
                fonte.setPixelSize(max(6, round(fonte.pixelSize() * self._escala)))
            else:
                fonte.setPointSizeF(max(5.0, fonte.pointSizeF() * self._escala))
        return fonte

    def _linhas(self, largura):
        metrics = QFontMetrics(self._fonte_efetiva())
        linhas, atual = [], ""
        for palavra in self.text().split():
            while metrics.horizontalAdvance(palavra) > largura:
                corte = len(palavra)
                while corte > 1 and metrics.horizontalAdvance(palavra[:corte]) > largura:
                    corte -= 1
                if atual:
                    linhas.append(atual)
                    atual = ""
                linhas.append(palavra[:corte])
                palavra = palavra[corte:]
            tentativa = f"{atual} {palavra}".strip()
            if atual and metrics.horizontalAdvance(tentativa) > largura:
                linhas.append(atual)
                atual = palavra
            else:
                atual = tentativa
        if atual:
            linhas.append(atual)
        return linhas or [""]

    def ajustar_para_largura(self, largura, max_linhas=None):
        self._escala = 1.0
        if max_linhas:
            while len(self._linhas(largura)) > max_linhas and self._escala > 0.55:
                self._escala -= 0.08
        self.setFixedWidth(largura)
        altura_linha = QFontMetrics(self._fonte_efetiva()).lineSpacing()
        self.setFixedHeight(len(self._linhas(largura)) * altura_linha + 4)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = self._fonte_efetiva()
        painter.setFont(font)
        metrics = painter.fontMetrics()
        y = 2 + metrics.ascent()
        for linha in self._linhas(self.width()):
            x = (self.width() - metrics.horizontalAdvance(linha)) / 2.0
            _desenhar_texto_contorno(
                painter, font, x, y, linha, self.cor_texto, self.borda_cor, self.espessura
            )
            y += metrics.lineSpacing()
        painter.end()

    def mousePressEvent(self, event):
        if self._clicavel and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        else:
            super().mousePressEvent(event)
