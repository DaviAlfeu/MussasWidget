import ctypes
import os
from ctypes import wintypes

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QComboBox, QLabel, QPushButton, QVBoxLayout, QWidget,
)

try:
    from gerenciador_modulos import PluginBase
except ImportError:
    class PluginBase:
        nome = "Otimizador Navegador"
        versao = "0.1.0"

        def __init__(self, app):
            self.app = app

        def criar_pagina(self):
            return None

        def botoes_topo(self):
            return []

        def ao_aplicar_tema(self):
            pass

        def ao_mudar_area_pagina(self, area):
            pass

        def encerrar(self):
            return True


_NAVEGADORES = {
    "arc.exe": "Arc",
    "brave.exe": "Brave",
    "chrome.exe": "Chrome",
    "chromium.exe": "Chromium",
    "coowon.exe": "Coowon",
    "floorp.exe": "Floorp",
    "firefox.exe": "Firefox",
    "librewolf.exe": "LibreWolf",
    "maxthon.exe": "Maxthon",
    "msedge.exe": "Edge",
    "opera.exe": "Opera",
    "opera_gx.exe": "Opera GX",
    "palemoon.exe": "Pale Moon",
    "thorium.exe": "Thorium",
    "vivaldi.exe": "Vivaldi",
    "waterfox.exe": "Waterfox",
    "zen.exe": "Zen",
    "zen-browser.exe": "Zen",
    "yandex.exe": "Yandex",
    "360chrome.exe": "360 Browser",
}

_TH32CS_SNAPPROCESS = 0x00000002
_PROCESS_QUERY_INFORMATION = 0x0400
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_SET_INFORMATION = 0x0200
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000
_PROCESS_POWER_THROTTLING = 4
_PROCESS_POWER_THROTTLING_EXECUTION_SPEED = 0x1
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class _PROCESS_POWER_THROTTLING_STATE(ctypes.Structure):
    _fields_ = [
        ("Version", wintypes.DWORD),
        ("ControlMask", wintypes.DWORD),
        ("StateMask", wintypes.DWORD),
    ]


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def _processos():
    if os.name != "nt":
        raise OSError("Este módulo funciona apenas no Windows.")

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)
    ]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)
    ]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    snapshot = kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if snapshot == _INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())

    resultado = {}
    try:
        entrada = _PROCESSENTRY32W()
        entrada.dwSize = ctypes.sizeof(entrada)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entrada)):
            raise ctypes.WinError(ctypes.get_last_error())
        while True:
            resultado[int(entrada.th32ProcessID)] = (
                int(entrada.th32ParentProcessID), entrada.szExeFile.casefold()
            )
            entrada.dwSize = ctypes.sizeof(entrada)
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entrada)):
                erro = ctypes.get_last_error()
                if erro != 18:
                    raise ctypes.WinError(erro)
                break
    finally:
        kernel32.CloseHandle(snapshot)
    return resultado


def _janelas_navegadores():
    if os.name != "nt":
        raise OSError("Este módulo funciona apenas no Windows.")

    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [
        wintypes.HWND, wintypes.LPWSTR, ctypes.c_int
    ]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND, ctypes.POINTER(wintypes.DWORD)
    ]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetForegroundWindow.restype = wintypes.HWND
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    processos = _processos()
    janelas = []
    def visitar(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        tamanho = user32.GetWindowTextLengthW(hwnd)
        if tamanho <= 0:
            return True
        titulo = ctypes.create_unicode_buffer(tamanho + 1)
        user32.GetWindowTextW(hwnd, titulo, tamanho + 1)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        processo = processos.get(int(pid.value))
        if processo is None:
            return True

        handle = kernel32.OpenProcess(0x1000, False, pid.value)
        exe = processo[1]
        if handle:
            try:
                caminho = ctypes.create_unicode_buffer(32768)
                comprimento = wintypes.DWORD(len(caminho))
                if kernel32.QueryFullProcessImageNameW(
                    handle, 0, caminho, ctypes.byref(comprimento)
                ):
                    exe = os.path.basename(caminho.value).casefold()
            finally:
                kernel32.CloseHandle(handle)

        nome = _NAVEGADORES.get(exe)
        if nome:
            janelas.append((int(pid.value), nome, titulo.value.strip()))
        return True

    callback = callback_type(visitar)
    if not user32.EnumWindows(callback, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    pid_ativo = wintypes.DWORD()
    janela_ativa = user32.GetForegroundWindow()
    if janela_ativa:
        user32.GetWindowThreadProcessId(janela_ativa, ctypes.byref(pid_ativo))
        janelas.sort(key=lambda janela: janela[0] != int(pid_ativo.value))
    return janelas, processos


def _processos_alvo(pid_raiz, processos):
    raiz = processos.get(pid_raiz)
    if raiz is None:
        raise ProcessLookupError("A janela selecionada já foi fechada.")
    exe_raiz = raiz[1]
    filhos = {}
    for pid, (pai, _exe) in processos.items():
        filhos.setdefault(pai, []).append(pid)

    encontrados = []
    visitados = set()
    pendentes = [pid_raiz]
    while pendentes:
        pid = pendentes.pop()
        if pid in visitados:
            continue
        visitados.add(pid)
        processo = processos.get(pid)
        if processo is None:
            continue
        if processo[1] == exe_raiz:
            encontrados.append(pid)
        pendentes.extend(filhos.get(pid, ()))
    return encontrados


def _memoria_processo(pid):
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(_PROCESS_MEMORY_COUNTERS), wintypes.DWORD
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(_PROCESS_QUERY_INFORMATION, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        counters = _PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(
            handle, ctypes.byref(counters), counters.cb
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(counters.WorkingSetSize)
    finally:
        kernel32.CloseHandle(handle)


def _esvaziar_memoria_processo(pid):
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    psapi.EmptyWorkingSet.argtypes = [wintypes.HANDLE]
    psapi.EmptyWorkingSet.restype = wintypes.BOOL

    direitos = _PROCESS_QUERY_INFORMATION | _PROCESS_SET_QUOTA
    handle = kernel32.OpenProcess(direitos, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not psapi.EmptyWorkingSet(handle):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel32.CloseHandle(handle)


def _aplicar_modo_jogo_processo(pid):
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.GetPriorityClass.argtypes = [wintypes.HANDLE]
    kernel32.GetPriorityClass.restype = wintypes.DWORD
    kernel32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.SetPriorityClass.restype = wintypes.BOOL
    kernel32.GetProcessInformation.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD
    ]
    kernel32.GetProcessInformation.restype = wintypes.BOOL
    kernel32.SetProcessInformation.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD
    ]
    kernel32.SetProcessInformation.restype = wintypes.BOOL

    direitos = _PROCESS_QUERY_LIMITED_INFORMATION | _PROCESS_SET_INFORMATION
    handle = kernel32.OpenProcess(direitos, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())

    prioridade_original = kernel32.GetPriorityClass(handle)
    if not prioridade_original:
        erro = ctypes.WinError(ctypes.get_last_error())
        kernel32.CloseHandle(handle)
        raise erro

    if not kernel32.SetPriorityClass(handle, _ABOVE_NORMAL_PRIORITY_CLASS):
        erro = ctypes.WinError(ctypes.get_last_error())
        kernel32.CloseHandle(handle)
        raise erro

    estado_original = _PROCESS_POWER_THROTTLING_STATE()
    estado_original.Version = 1
    power_aplicado = False
    avisos = []
    if kernel32.GetProcessInformation(
        handle, _PROCESS_POWER_THROTTLING,
        ctypes.byref(estado_original), ctypes.sizeof(estado_original)
    ):
        estado_jogo = _PROCESS_POWER_THROTTLING_STATE(
            1,
            estado_original.ControlMask | _PROCESS_POWER_THROTTLING_EXECUTION_SPEED,
            estado_original.StateMask & ~_PROCESS_POWER_THROTTLING_EXECUTION_SPEED,
        )
        power_aplicado = bool(kernel32.SetProcessInformation(
            handle, _PROCESS_POWER_THROTTLING,
            ctypes.byref(estado_jogo), ctypes.sizeof(estado_jogo)
        ))
        if not power_aplicado:
            avisos.append(
                f"PID {pid}: não foi possível desativar economia de energia "
                f"({ctypes.WinError(ctypes.get_last_error())})."
            )
    else:
        avisos.append(
            f"PID {pid}: o Windows não permitiu consultar a economia de energia "
            f"({ctypes.WinError(ctypes.get_last_error())})."
        )

    return {
        "handle": handle,
        "prioridade": int(prioridade_original),
        "estado_energia": (
            int(estado_original.ControlMask), int(estado_original.StateMask)
        ) if power_aplicado else None,
        "avisos": avisos,
    }


def _restaurar_modo_jogo_processo(estado):
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.GetExitCodeProcess.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)
    ]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.SetPriorityClass.restype = wintypes.BOOL
    kernel32.SetProcessInformation.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD
    ]
    kernel32.SetProcessInformation.restype = wintypes.BOOL

    avisos = []
    handle = estado["handle"]
    try:
        codigo_saida = wintypes.DWORD()
        if (
            kernel32.GetExitCodeProcess(handle, ctypes.byref(codigo_saida))
            and codigo_saida.value != 259
        ):
            return avisos
        if not kernel32.SetPriorityClass(handle, estado["prioridade"]):
            avisos.append(
                f"Não foi possível restaurar prioridade: "
                f"{ctypes.WinError(ctypes.get_last_error())}."
            )
        energia = estado["estado_energia"]
        if energia is not None:
            original = _PROCESS_POWER_THROTTLING_STATE(1, *energia)
            if not kernel32.SetProcessInformation(
                handle, _PROCESS_POWER_THROTTLING,
                ctypes.byref(original), ctypes.sizeof(original)
            ):
                avisos.append(
                    f"Não foi possível restaurar economia de energia: "
                    f"{ctypes.WinError(ctypes.get_last_error())}."
                )
    finally:
        kernel32.CloseHandle(handle)
    return avisos


class Plugin(PluginBase):
    nome = "Otimizador de navegador"
    versao = "1.0.0"

    def __init__(self, app):
        super().__init__(app)
        self._cor_texto = "#ffffff"
        self._alvos = {}
        self._modo_jogo_pid = None
        self._processos_modo_jogo = {}

        self.page = QWidget(app.pages_container)
        self.page.setGeometry(0, 0, 150, 150)
        self.page.hide()
        self.conteudo = QWidget(self.page)
        self.layout = QVBoxLayout(self.conteudo)
        self.layout.setContentsMargins(4, 2, 4, 2)
        self.layout.setSpacing(1)

        self.titulo = QLabel("NAVEGADOR · JOGO")
        self.titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.seletor = QComboBox()
        self.seletor.setFixedHeight(20)
        self.seletor.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.seletor.setMinimumContentsLength(12)
        self.seletor.setToolTip(
            "Escolha uma janela. As otimizações aplicam-se aos processos "
            "da instância inteira do navegador, não somente a uma aba."
        )
        self.seletor.currentIndexChanged.connect(self._ao_selecionar_alvo)

        self.memoria = QLabel("Selecione uma janela")
        self.memoria.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.memoria.setWordWrap(True)
        self.memoria.setToolTip(
            "Memória física residente (working set) da janela selecionada "
            "e dos processos descendentes do mesmo navegador."
        )

        self.botao_modo_jogo = QPushButton("Ativar Modo Jogo")
        self.botao_modo_jogo.setFixedHeight(23)
        self.botao_modo_jogo.setToolTip(
            "Eleva temporariamente a prioridade dos processos do navegador e "
            "desativa a economia de energia do processador para eles. "
            "As configurações anteriores são restauradas ao desligar."
        )
        self.botao_modo_jogo.clicked.connect(self._alternar_modo_jogo)

        self.botao_otimizar = QPushButton("Liberar RAM")
        self.botao_otimizar.setFixedHeight(20)
        self.botao_otimizar.setToolTip(
            "Solicita ao Windows que descarte páginas da memória física "
            "dos processos do navegador selecionado. As páginas podem ser "
            "carregadas novamente conforme forem necessárias."
        )
        self.botao_otimizar.clicked.connect(self._otimizar)

        self.estado = QLabel("Escolha o navegador alvo.")
        self.estado.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.estado.setWordWrap(True)
        self.estado.setMaximumHeight(25)

        self.botao_atualizar = QPushButton("Atualizar lista")
        self.botao_atualizar.setFixedHeight(18)
        self.botao_atualizar.clicked.connect(self._atualizar_alvos)

        self.layout.addWidget(self.titulo)
        self.layout.addWidget(self.seletor)
        self.layout.addWidget(self.memoria)
        self.layout.addWidget(self.botao_modo_jogo)
        self.layout.addWidget(self.botao_otimizar)
        self.layout.addWidget(self.estado, 1)
        self.layout.addWidget(self.botao_atualizar)

        self.timer = QTimer(app)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self._atualizar_estado)
        self.timer.start()
        self._atualizar_alvos()

    def criar_pagina(self):
        self.app.registrar_pagina(self.page, chave="otimizador_navegador", nome="Jogo")
        return None

    def ao_mudar_area_pagina(self, area):
        x, y, largura, altura = area
        self.conteudo.setGeometry(x, y, largura, altura)

    def ao_aplicar_tema(self):
        self._cor_texto = self.app.cor_texto
        estilo_label = (
            f"color: {self._cor_texto}; background: transparent; "
            "font-family: 'Segoe UI'; font-size: 9px;"
        )
        self.titulo.setStyleSheet(
            estilo_label + "font-size: 10px; font-weight: bold;"
        )
        self.memoria.setStyleSheet(
            estilo_label + "font-size: 12px; font-weight: bold;"
        )
        self.estado.setStyleSheet(estilo_label)
        bg, hover = self.app.cores_botoes()
        estilo_botao = (
            f"QPushButton {{ color: {self._cor_texto}; background: {bg}; "
            "border: none; border-radius: 5px; padding: 2px; }"
            f"QPushButton:hover {{ background: {hover}; }}"
        )
        self.botao_otimizar.setStyleSheet(estilo_botao)
        self.botao_modo_jogo.setStyleSheet(estilo_botao)
        self.botao_atualizar.setStyleSheet(estilo_botao)
        self.seletor.setStyleSheet(
            f"QComboBox {{ color: {self._cor_texto}; background: {bg}; "
            "border: none; border-radius: 4px; padding: 2px; }"
        )

    def encerrar(self):
        self.timer.stop()
        self._desativar_modo_jogo()
        return True

    def _ao_selecionar_alvo(self, *_args):
        pid = self.seletor.currentData()
        if self._modo_jogo_pid is not None and pid != self._modo_jogo_pid:
            self._desativar_modo_jogo()
        self._atualizar_memoria()

    def _atualizar_alvos(self):
        anterior = self.seletor.currentData()
        try:
            janelas, _processos_atuais = _janelas_navegadores()
        except OSError as erro:
            self.seletor.clear()
            self._alvos.clear()
            self.memoria.setText("Não foi possível detectar navegadores.")
            self.estado.setText(str(erro))
            self.botao_otimizar.setEnabled(False)
            return

        alvos = {}
        for pid, nome, titulo in janelas:
            if pid not in alvos:
                descricao = titulo or f"Janela sem título (PID {pid})"
                alvos[pid] = (f"{nome}: {descricao[:28]} (PID {pid})", nome)

        self._alvos = alvos
        self.seletor.blockSignals(True)
        self.seletor.clear()
        for pid, (descricao, _nome) in alvos.items():
            self.seletor.addItem(descricao, pid)
        indice = self.seletor.findData(anterior)
        if indice >= 0:
            self.seletor.setCurrentIndex(indice)
        self.seletor.blockSignals(False)
        disponivel = bool(alvos)
        self.botao_otimizar.setEnabled(disponivel)
        if not disponivel:
            self.memoria.setText("Nenhuma janela de navegador detectada.")
            self.estado.setText("Abra um navegador e atualize a lista.")
        else:
            if self._modo_jogo_pid is None:
                self.estado.setText("Modo Jogo desligado.")
            self._atualizar_memoria()

    def _atualizar_estado(self):
        if self._modo_jogo_pid is not None:
            self._aplicar_modo_jogo()
        self._atualizar_memoria()

    def _atualizar_memoria(self, *_args):
        pid = self.seletor.currentData()
        if pid is None:
            return
        try:
            processos = _processos()
            pids = _processos_alvo(int(pid), processos)
        except (OSError, ProcessLookupError) as erro:
            self.memoria.setText("Memória indisponível")
            self.estado.setText(str(erro))
            return
        total = 0
        falhas = []
        for processo in pids:
            try:
                total += _memoria_processo(processo)
            except OSError as erro:
                falhas.append(f"PID {processo}: {erro}")
        self.memoria.setText(f"{total / (1024 ** 2):.0f} MB em uso")
        if falhas:
            if self._modo_jogo_pid is None:
                self.estado.setText(
                    f"Leitura parcial: {len(falhas)} processo(s) sem acesso."
                )
                self.estado.setToolTip("\n".join(falhas))

    def _alternar_modo_jogo(self):
        if self._modo_jogo_pid is not None:
            self._desativar_modo_jogo()
            return
        pid = self.seletor.currentData()
        if pid is None:
            self.estado.setText("Selecione um navegador primeiro.")
            return
        self._modo_jogo_pid = int(pid)
        if not self._aplicar_modo_jogo():
            self._modo_jogo_pid = None
            self.botao_modo_jogo.setText("Ativar Modo Jogo")
            self.botao_modo_jogo.setEnabled(self.seletor.currentData() is not None)

    def _aplicar_modo_jogo(self):
        if self._modo_jogo_pid is None:
            return False
        try:
            processos = _processos()
            pids = _processos_alvo(self._modo_jogo_pid, processos)
        except (OSError, ProcessLookupError) as erro:
            self._desativar_modo_jogo()
            self.estado.setText(f"Modo Jogo encerrado: {erro}")
            return False

        ativos = set(pids)
        encerrados = [
            processo for processo in self._processos_modo_jogo
            if processo not in ativos
        ]
        for processo in encerrados:
            estado = self._processos_modo_jogo.pop(processo)
            avisos = _restaurar_modo_jogo_processo(estado)
            if avisos:
                self.estado.setToolTip("\n".join(avisos))

        falhas = []
        avisos = []
        for processo in pids:
            if processo in self._processos_modo_jogo:
                continue
            try:
                estado = _aplicar_modo_jogo_processo(processo)
                self._processos_modo_jogo[processo] = estado
                avisos.extend(estado["avisos"])
            except OSError as erro:
                falhas.append(f"PID {processo}: {erro}")

        if not self._processos_modo_jogo:
            self.estado.setText("Não foi possível aplicar o Modo Jogo.")
            self.estado.setToolTip("\n".join(falhas))
            self.botao_modo_jogo.setEnabled(False)
            return False

        self.botao_modo_jogo.setEnabled(True)
        self.botao_modo_jogo.setText("Desativar Modo Jogo")
        if falhas or avisos:
            self.estado.setText(
                f"Modo Jogo parcial: {len(self._processos_modo_jogo)} processos."
            )
            self.estado.setToolTip("\n".join(falhas + avisos))
        else:
            self.estado.setText(
                f"Modo Jogo ativo em {len(self._processos_modo_jogo)} processos."
            )
            self.estado.setToolTip(
                "Prioridade acima do normal e economia de energia do processo "
                "desativada. Isso melhora a resposta sob contenção de CPU, "
                "mas não garante mais FPS."
            )
        return True

    def _desativar_modo_jogo(self):
        avisos = []
        for processo, estado in list(self._processos_modo_jogo.items()):
            avisos.extend(
                f"PID {processo}: {aviso}"
                for aviso in _restaurar_modo_jogo_processo(estado)
            )
        self._processos_modo_jogo.clear()
        self._modo_jogo_pid = None
        self.botao_modo_jogo.setText("Ativar Modo Jogo")
        self.botao_modo_jogo.setEnabled(self.seletor.currentData() is not None)
        if avisos:
            self.estado.setText("Modo desligado; algumas opções não restauraram.")
            self.estado.setToolTip("\n".join(avisos))
        elif self.seletor.currentData() is not None:
            self.estado.setText("Modo Jogo desligado; configurações restauradas.")
            self.estado.setToolTip("")

    def _otimizar(self):
        pid = self.seletor.currentData()
        if pid is None:
            self.estado.setText("Selecione uma janela de navegador.")
            return
        try:
            processos = _processos()
            pids = _processos_alvo(int(pid), processos)
        except (OSError, ProcessLookupError) as erro:
            self.estado.setText(str(erro))
            return

        antes = 0
        falhas = []
        otimizados = 0
        for processo in pids:
            try:
                antes += _memoria_processo(processo)
            except OSError as erro:
                falhas.append(f"Leitura PID {processo}: {erro}")
            try:
                _esvaziar_memoria_processo(processo)
                otimizados += 1
            except OSError as erro:
                falhas.append(f"PID {processo}: {erro}")

        depois = 0
        for processo in pids:
            try:
                depois += _memoria_processo(processo)
            except OSError as erro:
                falhas.append(f"Leitura final PID {processo}: {erro}")

        if otimizados == 0:
            self.estado.setText(
                "Falha ao otimizar. Veja os detalhes na dica."
                if falhas else "Nenhum processo acessível para otimizar."
            )
            self.estado.setToolTip("\n".join(falhas))
            return

        liberada = max(0, antes - depois) / (1024 ** 2)
        if falhas:
            self.estado.setText(
                f"{otimizados}/{len(pids)} processos. "
                f"Variação: {liberada:.0f} MB; veja detalhes."
            )
            self.estado.setToolTip("\n".join(falhas))
        else:
            self.estado.setText(
                f"Solicitado ao Windows: {liberada:.0f} MB liberados."
            )
            self.estado.setToolTip(
                "O Windows pode carregar novamente essas páginas conforme "
                "o navegador voltar a usá-las."
            )
        self.memoria.setText(
            f"{depois / (1024 ** 2):.0f} MB em uso após otimização"
        )
