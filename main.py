import sys
import signal
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSharedMemory
from app_widget import WidgetFrutigerAero

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    import ctypes
    try:
        myappid = 'davialfeu.mussaswidget.app.1.0'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except:
        pass

    app = QApplication(sys.argv)
    
    from PyQt6.QtGui import QIcon
    from utils import external_resource_path
    app.setWindowIcon(QIcon(external_resource_path("assets/icone.ico")))
    
    shared_memory = QSharedMemory("MussasWidget_SingleInstance")
    if shared_memory.attach():
        sys.exit(0)
    shared_memory.create(1)
    
    QApplication.setQuitOnLastWindowClosed(False) 
    
    widget = WidgetFrutigerAero()
    widget.show()
    
    sys.exit(app.exec())
