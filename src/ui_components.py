import os
from PyQt6.QtWidgets import QLabel, QFrame, QGraphicsScene, QGraphicsBlurEffect
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QPainterPath, QColor, QImage, QPen, QPixmap

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
        self.border_radius = 18

    def update_background(self, image_path, blur_radius, overlay_color, border_color, border_radius=18, modo_claro=False):
        self.border_color = QColor(*border_color) if isinstance(border_color, tuple) else QColor(border_color)
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
            base_color = QColor(245, 245, 245) if modo_claro else QColor(25, 25, 25)
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
