import sys
import signal
import crashlog
from updater import tratar_argumentos_de_atualizacao, limpar_updates_antigos
from PyQt6.QtWidgets import QApplication, QStyleFactory
from PyQt6.QtCore import QSharedMemory
from app_widget import WidgetFrutigerAero

if __name__ == '__main__':
    codigo_update = tratar_argumentos_de_atualizacao(sys.argv)
    if codigo_update is not None:
        sys.exit(codigo_update)

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    crashlog.instalar()
    
    app = QApplication(sys.argv)

    # No Windows 10 o Qt usa o estilo "windowsvista" (cantos retos); força o visual arredondado do Windows 11
    if sys.platform == "win32" and sys.getwindowsversion().build < 22000:
        estilos = {nome.lower(): nome for nome in QStyleFactory.keys()}
        estilo = estilos.get("windows11") or estilos.get("fusion")
        if estilo:
            app.setStyle(estilo)
    
    from PyQt6.QtGui import QIcon
    from utils import external_resource_path, limpar_versoes_antigas
    app.setWindowIcon(QIcon(external_resource_path("assets/icone.ico")))
    
    shared_memory = QSharedMemory("MussasWidget_SingleInstance")
    if shared_memory.attach():
        sys.exit(0)
    shared_memory.create(1)
    limpar_versoes_antigas()
    limpar_updates_antigos()
    
    QApplication.setQuitOnLastWindowClosed(False) 
    
    widget = WidgetFrutigerAero()
    widget.show()
    
    sys.exit(app.exec())
