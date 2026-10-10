import csv
import ctypes
import glob
import json
import os
import re
import shutil
import subprocess
import threading
import time
from collections import deque
from ctypes import wintypes

from PyQt6.QtCore import QThread, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QStackedWidget, QVBoxLayout, QWidget
)

from config import config_app
from gerenciador_modulos import PluginBase

try:
    import winreg
except ImportError:
    winreg = None

CHAVE_CONFIG = "monitor_pc"
NO_WINDOW = 0x08000000
PASTA_MODULO = os.path.dirname(os.path.abspath(__file__))

LIMITE_TEMP_CPU = 85
LIMITE_TEMP_DISCO = 70
LIMITE_TEMP_GPU = 85

CATEGORIAS = [
    ("cpu", "CPU"),
    ("gpu", "GPU"),
    ("ram", "RAM"),
    ("disco", "DISCO"),
    ("fan", "FAN"),
    ("fps", "FPS"),
]

PADRAO_CONFIG = {
    "linhas": [chave for chave, _ in CATEGORIAS],
    "fps": False,
    "presentmon": "",
    "intervalo": 1.0,
}

COR_ALERTA = "#ff5a5a"
COR_ATENCAO = "#ffb84d"
COR_NOME = "#8a8a8a"


# ---------------------------------------------------------------- Windows API

class _SPPI(ctypes.Structure):
    _fields_ = [
        ("Idle", ctypes.c_int64), ("Kernel", ctypes.c_int64), ("User", ctypes.c_int64),
        ("Dpc", ctypes.c_int64), ("Interrupt", ctypes.c_int64),
        ("IntCount", ctypes.c_ulong), ("Pad", ctypes.c_ulong),
    ]


class _MEMORIA(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


class _PdhValor(ctypes.Structure):
    _fields_ = [("CStatus", ctypes.c_ulong), ("valor", ctypes.c_double)]


class _PdhItem(ctypes.Structure):
    _fields_ = [("nome", ctypes.c_wchar_p), ("fmt", _PdhValor)]


class ConsultaPdh:
    """Contadores de desempenho do Windows (PDH), sem dependências externas."""

    PDH_FMT_DOUBLE = 0x200
    PDH_MORE_DATA = 0x800007D2

    def __init__(self, caminhos):
        self.pdh = ctypes.windll.pdh
        self.pdh.PdhOpenQueryW.argtypes = [ctypes.c_wchar_p, ctypes.c_size_t, ctypes.c_void_p]
        self.pdh.PdhAddEnglishCounterW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_size_t, ctypes.c_void_p]
        self.pdh.PdhCollectQueryData.argtypes = [ctypes.c_void_p]
        self.pdh.PdhCloseQuery.argtypes = [ctypes.c_void_p]
        self.pdh.PdhGetFormattedCounterArrayW.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
        ]
        self.consulta = ctypes.c_void_p()
        self.contadores = {}
        if self.pdh.PdhOpenQueryW(None, 0, ctypes.byref(self.consulta)) != 0:
            self.consulta = None
            return
        for caminho in caminhos:
            contador = ctypes.c_void_p()
            if self.pdh.PdhAddEnglishCounterW(self.consulta, caminho, 0, ctypes.byref(contador)) == 0:
                self.contadores[caminho] = contador
        self.pdh.PdhCollectQueryData(self.consulta)

    def coletar(self):
        if self.consulta:
            self.pdh.PdhCollectQueryData(self.consulta)

    def valores(self, caminho):
        contador = self.contadores.get(caminho)
        if contador is None:
            return {}
        tamanho = ctypes.c_ulong(0)
        quantidade = ctypes.c_ulong(0)
        status = self.pdh.PdhGetFormattedCounterArrayW(
            contador, self.PDH_FMT_DOUBLE, ctypes.byref(tamanho), ctypes.byref(quantidade), None
        )
        if (status & 0xFFFFFFFF) != self.PDH_MORE_DATA:
            return {}
        buffer = ctypes.create_string_buffer(tamanho.value)
        status = self.pdh.PdhGetFormattedCounterArrayW(
            contador, self.PDH_FMT_DOUBLE, ctypes.byref(tamanho), ctypes.byref(quantidade), buffer
        )
        if status != 0:
            return {}
        itens = ctypes.cast(buffer, ctypes.POINTER(_PdhItem))
        resultado = {}
        for i in range(quantidade.value):
            if itens[i].fmt.CStatus in (0, 0x00000001):
                resultado[itens[i].nome] = itens[i].fmt.valor
        return resultado

    def fechar(self):
        if self.consulta:
            self.pdh.PdhCloseQuery(self.consulta)
            self.consulta = None


def _powershell(comando, timeout=20):
    comando = "[Console]::OutputEncoding=[Text.Encoding]::UTF8;" + comando
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", comando],
            capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW,
            encoding="utf-8", errors="replace",
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _json_lista(texto):
    if not texto:
        return []
    try:
        dados = json.loads(texto)
    except ValueError:
        return []
    return dados if isinstance(dados, list) else [dados]


def _ler_cpu_por_nucleo():
    n = os.cpu_count() or 1
    buffer = (_SPPI * n)()
    retorno = ctypes.c_ulong(0)
    if ctypes.windll.ntdll.NtQuerySystemInformation(8, buffer, ctypes.sizeof(buffer), ctypes.byref(retorno)) != 0:
        return None
    return [(p.Idle, p.Kernel + p.User) for p in buffer]


def _ler_mhz():
    n = os.cpu_count() or 1
    buffer = (ctypes.c_ulong * (6 * n))()
    if ctypes.windll.powrprof.CallNtPowerInformation(11, None, 0, buffer, ctypes.sizeof(buffer)) != 0:
        return None, None
    return buffer[2], buffer[1]


def _ler_memoria():
    info = _MEMORIA()
    info.dwLength = ctypes.sizeof(info)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(info))
    return info.ullTotalPhys, info.ullAvailPhys


def _nome_cpu():
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as chave:
            return str(winreg.QueryValueEx(chave, "ProcessorNameString")[0]).strip()
    except (OSError, AttributeError):
        return "CPU"


def _info_vram_registro():
    """Maior placa de vídeo registrada: (nome, VRAM em bytes)."""
    melhor = (None, 0)
    if winreg is None:
        return melhor
    base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
    for i in range(16):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{base}\\{i:04d}") as chave:
                try:
                    nome = str(winreg.QueryValueEx(chave, "DriverDesc")[0])
                except OSError:
                    continue
                try:
                    tamanho = winreg.QueryValueEx(chave, "HardwareInformation.qwMemorySize")[0]
                    if isinstance(tamanho, bytes):
                        tamanho = int.from_bytes(tamanho, "little")
                except OSError:
                    tamanho = 0
                if tamanho > melhor[1] or melhor[0] is None:
                    melhor = (nome, int(tamanho))
        except OSError:
            continue
    return melhor


def _discos_fixos():
    mascara = ctypes.windll.kernel32.GetLogicalDrives()
    discos = []
    for i in range(26):
        if not mascara & (1 << i):
            continue
        raiz = f"{chr(65 + i)}:\\"
        if ctypes.windll.kernel32.GetDriveTypeW(raiz) != 3:
            continue
        try:
            uso = shutil.disk_usage(raiz)
        except OSError:
            continue
        discos.append({
            "letra": raiz[:2], "usado": uso.used, "total": uso.total,
            "pct": uso.used / uso.total * 100 if uso.total else 0,
        })
    return discos


def _achar_nvidia_smi():
    candidatos = [
        shutil.which("nvidia-smi"),
        r"C:\Windows\System32\nvidia-smi.exe",
        r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
    ]
    return next((c for c in candidatos if c and os.path.isfile(c)), None)


def _ler_nvidia(exe):
    try:
        r = subprocess.run(
            [exe, "--query-gpu=name,utilization.gpu,temperature.gpu,memory.used,memory.total,fan.speed",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=4, creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0 or not r.stdout.strip():
        return None
    partes = [p.strip() for p in r.stdout.strip().splitlines()[0].split(",")]
    if len(partes) < 6:
        return None

    def numero(valor):
        try:
            return float(valor)
        except ValueError:
            return None

    usada, total = numero(partes[3]), numero(partes[4])
    return {
        "nome": partes[0], "uso": numero(partes[1]), "temp": numero(partes[2]),
        "vram_usada": usada * 1024 * 1024 if usada is not None else None,
        "vram_total": total * 1024 * 1024 if total is not None else None,
        "fan_pct": numero(partes[5]),
    }


def _ler_sensores_hw():
    """Sensores do LibreHardwareMonitor / OpenHardwareMonitor (se estiver aberto)."""
    for espaco in ("root/LibreHardwareMonitor", "root/OpenHardwareMonitor"):
        saida = _powershell(
            f"Get-CimInstance -Namespace {espaco} -ClassName Sensor -ErrorAction Stop | "
            "Select-Object Name,SensorType,Value,Min,Max,Identifier | ConvertTo-Json -Compress"
        )
        sensores = _json_lista(saida)
        if sensores:
            return sensores
    return []


def _ler_temp_discos():
    saida = _powershell(
        "Get-PhysicalDisk | ForEach-Object { $c = $_ | Get-StorageReliabilityCounter -ErrorAction SilentlyContinue; "
        "[pscustomobject]@{Nome=$_.FriendlyName;Temp=$c.Temperature} } | ConvertTo-Json -Compress"
    )
    return [d for d in _json_lista(saida) if isinstance(d, dict) and d.get("Temp")]


def _ler_freq_ram():
    saida = _powershell(
        "Get-CimInstance Win32_PhysicalMemory | ForEach-Object { if ($_.ConfiguredClockSpeed) "
        "{ $_.ConfiguredClockSpeed } else { $_.Speed } }"
    )
    valores = [int(v) for v in saida.split() if v.isdigit()]
    return max(valores) if valores else None


class Periodico(threading.Thread):
    """Executa uma leitura lenta em segundo plano e guarda o último resultado."""

    def __init__(self, funcao, intervalo, ativo, intervalo_falha=None):
        super().__init__(daemon=True)
        self.funcao = funcao
        self.intervalo = intervalo
        self.intervalo_falha = intervalo_falha or intervalo
        self.ativo = ativo
        self.valor = None
        self._parar = threading.Event()

    def run(self):
        while not self._parar.is_set():
            if self.ativo():
                try:
                    self.valor = self.funcao()
                except Exception:
                    self.valor = None
            self._parar.wait(self.intervalo if self.valor else self.intervalo_falha)

    def parar(self):
        self._parar.set()


# ------------------------------------------------------------------ FPS

class LeitorFps:
    """Lê quadros/s e frametime pelo PresentMon (se o executável estiver disponível)."""

    ARGUMENTOS = (
        ["--output_stdout", "--stop_existing_session", "--no_console_stats"],
        ["-output_stdout", "-stop_existing_session"],
    )
    IGNORAR = {"dwm.exe", "python.exe", "pythonw.exe", "mussaswidget.exe", "explorer.exe"}

    def __init__(self, exe):
        self.exe = exe
        self.erro = ""
        self.processo = None
        self._amostras = {}
        self._trava = threading.Lock()
        self._parar = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    @staticmethod
    def localizar(configurado=""):
        if configurado and os.path.isfile(configurado):
            return configurado
        pastas = [PASTA_MODULO, os.path.join(PASTA_MODULO, "PresentMon"), os.path.join(os.environ.get("ProgramFiles", ""), "Intel", "PresentMon")]
        for pasta in pastas:
            achados = sorted(glob.glob(os.path.join(pasta, "PresentMon*.exe")))
            if achados:
                return achados[-1]
        return shutil.which("PresentMon")

    def _loop(self):
        for argumentos in self.ARGUMENTOS:
            if self._parar.is_set():
                return
            try:
                self.processo = subprocess.Popen(
                    [self.exe, *argumentos], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, bufsize=1, creationflags=NO_WINDOW,
                )
            except OSError as erro:
                self.erro = str(erro)
                return
            recebeu = False
            idx_app = idx_ms = None
            for linha in self.processo.stdout:
                if self._parar.is_set():
                    return
                if idx_app is None:
                    colunas = [c.strip().lower() for c in next(csv.reader([linha]))]
                    if "application" in colunas:
                        idx_app = colunas.index("application")
                        for nome in ("frametime", "msbetweenpresents"):
                            if nome in colunas:
                                idx_ms = colunas.index(nome)
                                break
                    continue
                try:
                    campos = next(csv.reader([linha]))
                    app, ms = campos[idx_app], float(campos[idx_ms])
                except (ValueError, IndexError, TypeError, StopIteration):
                    continue
                recebeu = True
                if app.lower() in self.IGNORAR:
                    continue
                agora = time.monotonic()
                with self._trava:
                    fila = self._amostras.setdefault(app, deque())
                    fila.append((agora, ms))
                    while fila and agora - fila[0][0] > 2.0:
                        fila.popleft()
            if recebeu:
                self.erro = "PresentMon encerrou"
                return
            try:
                self.erro = (self.processo.stderr.read() or "").strip()[:120] or "PresentMon sem dados (execute como administrador)"
            except (OSError, ValueError):
                self.erro = "PresentMon sem dados"
        return

    def amostra(self):
        agora = time.monotonic()
        melhor = None
        with self._trava:
            for app, fila in self._amostras.items():
                recentes = [ms for t, ms in fila if agora - t <= 1.0]
                if recentes and (melhor is None or len(recentes) > len(melhor[1])):
                    melhor = (app, recentes)
        if melhor is None:
            return {"app": None, "fps": None, "frametime": None, "pior": None, "erro": self.erro}
        app, recentes = melhor
        return {
            "app": app, "fps": float(len(recentes)), "frametime": sum(recentes) / len(recentes),
            "pior": max(recentes), "erro": "",
        }

    def parar(self):
        self._parar.set()
        if self.processo is not None:
            try:
                self.processo.terminate()
            except OSError:
                pass


# ------------------------------------------------------------------ Coleta

class Coletor(QThread):
    dados = pyqtSignal(object)

    CAMINHOS_PDH = [
        r"\Processor Information(*)\% Processor Performance",
        r"\GPU Engine(*)\Utilization Percentage",
        r"\GPU Adapter Memory(*)\Dedicated Usage",
        r"\Thermal Zone Information(*)\Temperature",
    ]

    def __init__(self, configuracao):
        super().__init__()
        self.configuracao = configuracao
        self.visivel = True
        self._parar = threading.Event()
        self._leitor_fps = None
        self._exe_fps = None
        self._min_max = {}

    def parar(self):
        self._parar.set()

    def _ativo(self):
        return self.visivel

    def _acompanhar_min_max(self, chave, valor):
        if valor is None:
            return None, None
        menor, maior = self._min_max.get(chave, (valor, valor))
        self._min_max[chave] = (min(menor, valor), max(maior, valor))
        return self._min_max[chave]

    def run(self):
        nome_cpu = _nome_cpu()
        nome_gpu_reg, vram_total_reg = _info_vram_registro()
        nvidia_exe = _achar_nvidia_smi()
        fontes = [
            Periodico(lambda: _ler_nvidia(nvidia_exe), 2, self._ativo, 6) if nvidia_exe else None,
            Periodico(_ler_sensores_hw, 4, self._ativo, 30),
            Periodico(_ler_temp_discos, 30, self._ativo, 120),
            Periodico(_ler_freq_ram, 3600, lambda: True, 60),
        ]
        nvidia, sensores_hw, temp_discos, freq_ram = fontes
        for fonte in fontes:
            if fonte is not None:
                fonte.start()

        pdh = None
        pdh_criado_em = 0
        anterior_cpu = _ler_cpu_por_nucleo()
        ultimo_gpu_pdh = {}
        ultimo_temp_zona = None
        try:
            while not self._parar.is_set():
                inicio = time.monotonic()
                dados = {"cpu": {"nome": nome_cpu}, "gpu": {}, "ram": {}, "disco": {}, "fan": {}, "fps": {}}

                atual_cpu = _ler_cpu_por_nucleo()
                nucleos = []
                if atual_cpu and anterior_cpu and len(atual_cpu) == len(anterior_cpu):
                    for (i0, t0), (i1, t1) in zip(anterior_cpu, atual_cpu):
                        total = t1 - t0
                        nucleos.append(max(0.0, min(100.0, (1 - (i1 - i0) / total) * 100)) if total > 0 else 0.0)
                anterior_cpu = atual_cpu
                dados["cpu"]["nucleos"] = nucleos
                dados["cpu"]["uso"] = sum(nucleos) / len(nucleos) if nucleos else None

                if pdh is None or inicio - pdh_criado_em > 20:
                    if pdh is not None:
                        pdh.fechar()
                    pdh = ConsultaPdh(self.CAMINHOS_PDH)
                    pdh_criado_em = inicio
                    recem_criado = True
                else:
                    pdh.coletar()
                    recem_criado = False

                _, mhz_max = _ler_mhz()
                dados["cpu"]["freq_max"] = mhz_max
                if not recem_criado:
                    desempenho = pdh.valores(self.CAMINHOS_PDH[0]).get("_Total")
                    if desempenho and mhz_max:
                        dados["cpu"]["freq"] = mhz_max * desempenho / 100
                    ultimo_gpu_pdh = self._ler_gpu_pdh(pdh)
                    zonas = [v - 273.15 for v in pdh.valores(self.CAMINHOS_PDH[3]).values() if 250 < v < 400]
                    ultimo_temp_zona = max(zonas) if zonas else None
                if not dados["cpu"].get("freq"):
                    atual_mhz, _ = _ler_mhz()
                    dados["cpu"]["freq"] = atual_mhz

                sensores = sensores_hw.valor or []
                hw = self._interpretar_sensores(sensores)
                temp_cpu = hw["cpu_temp"]
                dados["cpu"]["fonte_temp"] = "sensor" if temp_cpu is not None else None
                if temp_cpu is None and ultimo_temp_zona is not None:
                    temp_cpu = ultimo_temp_zona
                    dados["cpu"]["fonte_temp"] = "zona térmica"
                dados["cpu"]["temp"] = temp_cpu
                menor, maior = self._acompanhar_min_max("cpu", temp_cpu)
                if hw["cpu_min"] is not None:
                    menor = hw["cpu_min"]
                if hw["cpu_max"] is not None:
                    maior = max(maior or 0, hw["cpu_max"])
                dados["cpu"]["temp_min"], dados["cpu"]["temp_max"] = menor, maior

                gpu = {
                    "nome": nome_gpu_reg, "uso": ultimo_gpu_pdh.get("uso"), "temp": hw["gpu_temp"],
                    "vram_usada": ultimo_gpu_pdh.get("vram_usada"), "vram_total": vram_total_reg or None,
                }
                if nvidia is not None and nvidia.valor:
                    gpu.update({k: v for k, v in nvidia.valor.items() if v is not None and k != "fan_pct"})
                dados["gpu"] = gpu
                dados["gpu"]["temp_min"], dados["gpu"]["temp_max"] = self._acompanhar_min_max("gpu", gpu.get("temp"))

                total, livre = _ler_memoria()
                dados["ram"] = {
                    "total": total, "livre": livre, "usada": total - livre,
                    "pct": (total - livre) / total * 100 if total else None, "freq": freq_ram.valor,
                }

                dados["disco"] = {
                    "unidades": _discos_fixos(),
                    "temps": self._temps_disco(hw["discos"], temp_discos.valor or []),
                }

                fans = list(hw["fans"])
                if nvidia is not None and nvidia.valor and nvidia.valor.get("fan_pct") is not None and not any(
                    "gpu" in f["nome"].lower() for f in fans
                ):
                    fans.append({"nome": "GPU", "valor": nvidia.valor["fan_pct"], "unidade": "%"})
                dados["fan"] = {"fans": fans, "sensor": bool(sensores)}

                dados["fps"] = self._ler_fps()
                dados["hw_ativo"] = bool(sensores)
                self.dados.emit(dados)

                intervalo = max(0.5, float(self.configuracao().get("intervalo", 1.0)))
                if not self.visivel:
                    intervalo = max(intervalo, 3.0)
                self._parar.wait(max(0.2, intervalo - (time.monotonic() - inicio)))
        finally:
            if pdh is not None:
                pdh.fechar()
            for fonte in fontes:
                if fonte is not None:
                    fonte.parar()
            if self._leitor_fps is not None:
                self._leitor_fps.parar()

    @staticmethod
    def _ler_gpu_pdh(pdh):
        uso_por_luid = {}
        for nome, valor in pdh.valores(Coletor.CAMINHOS_PDH[1]).items():
            achado = re.search(r"luid_(0x[0-9a-fA-F]+_0x[0-9a-fA-F]+).*engtype_(\w+)", nome)
            if achado:
                tipos = uso_por_luid.setdefault(achado.group(1), {})
                tipos[achado.group(2)] = tipos.get(achado.group(2), 0.0) + valor
        memoria_por_luid = {}
        for nome, valor in pdh.valores(Coletor.CAMINHOS_PDH[2]).items():
            achado = re.search(r"luid_(0x[0-9a-fA-F]+_0x[0-9a-fA-F]+)", nome)
            if achado:
                memoria_por_luid[achado.group(1)] = memoria_por_luid.get(achado.group(1), 0.0) + valor
        if memoria_por_luid:
            luid = max(memoria_por_luid, key=memoria_por_luid.get)
        elif uso_por_luid:
            luid = max(uso_por_luid, key=lambda k: max(uso_por_luid[k].values()))
        else:
            return {}
        tipos = uso_por_luid.get(luid, {})
        return {
            "uso": min(100.0, max(tipos.values())) if tipos else None,
            "vram_usada": memoria_por_luid.get(luid),
        }

    @staticmethod
    def _interpretar_sensores(sensores):
        resultado = {
            "cpu_temp": None, "cpu_min": None, "cpu_max": None, "gpu_temp": None,
            "fans": [], "discos": [],
        }
        temps_cpu = []
        for s in sensores:
            tipo = str(s.get("SensorType", ""))
            nome = str(s.get("Name", ""))
            ident = str(s.get("Identifier", "")).lower()
            valor = s.get("Value")
            if not isinstance(valor, (int, float)):
                continue
            if tipo == "Temperature":
                if "/cpu" in ident:
                    temps_cpu.append((nome, valor, s.get("Min"), s.get("Max")))
                elif "/gpu" in ident and "core" in nome.lower():
                    resultado["gpu_temp"] = valor
                elif "/gpu" in ident and resultado["gpu_temp"] is None:
                    resultado["gpu_temp"] = valor
                elif any(t in ident for t in ("/nvme/", "/hdd/", "/ssd/", "/storage/")):
                    resultado["discos"].append({"nome": nome, "temp": valor})
            elif tipo == "Fan" and valor > 0:
                resultado["fans"].append({"nome": nome, "valor": valor, "unidade": "rpm"})
        if temps_cpu:
            preferido = next(
                (t for t in temps_cpu if any(k in t[0].lower() for k in ("package", "tctl", "tdie"))), None
            ) or max(temps_cpu, key=lambda t: t[1])
            resultado["cpu_temp"] = preferido[1]
            if isinstance(preferido[2], (int, float)):
                resultado["cpu_min"] = preferido[2]
            if isinstance(preferido[3], (int, float)):
                resultado["cpu_max"] = preferido[3]
        return resultado

    @staticmethod
    def _temps_disco(do_sensor, do_windows):
        if do_sensor:
            return do_sensor
        return [{"nome": d.get("Nome", "Disco"), "temp": float(d["Temp"])} for d in do_windows]

    def _ler_fps(self):
        config = self.configuracao()
        if not config.get("fps"):
            if self._leitor_fps is not None:
                self._leitor_fps.parar()
                self._leitor_fps = None
            return {"ativo": False}
        if self._leitor_fps is None:
            exe = LeitorFps.localizar(config.get("presentmon", ""))
            if not exe:
                return {"ativo": True, "erro": "PresentMon não encontrado"}
            self._leitor_fps = LeitorFps(exe)
        amostra = self._leitor_fps.amostra()
        amostra["ativo"] = True
        return amostra


# ------------------------------------------------------------------ Interface

class BarrasNucleos(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.valores = []
        self.setFixedHeight(30)

    def definir(self, valores):
        self.valores = list(valores)
        self.update()

    def paintEvent(self, evento):
        if not self.valores:
            return
        p = QPainter(self)
        p.setPen(Qt.PenStyle.NoPen)
        n = len(self.valores)
        espaco = 1
        largura = max(1.0, (self.width() - espaco * (n - 1)) / n)
        for i, v in enumerate(self.valores):
            p.setBrush(QColor(120, 120, 120, 70))
            x = i * (largura + espaco)
            p.drawRect(int(x), 0, max(1, int(largura)), self.height())
            altura = int(self.height() * v / 100)
            p.setBrush(QColor(cor_uso(v)))
            p.drawRect(int(x), self.height() - altura, max(1, int(largura)), altura)


class LinhaClicavel(QWidget):
    clicked = pyqtSignal()

    def __init__(self, nome, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.nome = QLabel(nome)
        self.nome.setFixedWidth(36)
        self.valor = QLabel("—")
        self.valor.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.valor.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.nome)
        layout.addWidget(self.valor, 1)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, evento):
        if evento.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class PaginaDetalhe(QWidget):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        self.titulo = QLabel()
        self.titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.barras = BarrasNucleos()
        self.corpo = QLabel()
        self.corpo.setTextFormat(Qt.TextFormat.RichText)
        self.corpo.setWordWrap(True)
        self.corpo.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.titulo)
        layout.addWidget(self.barras)
        layout.addWidget(self.corpo, 1)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, evento):
        if evento.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


def cor_uso(valor):
    if valor >= 90:
        return COR_ALERTA
    if valor >= 70:
        return COR_ATENCAO
    return "#55d98b"


def _fmt(valor, formato="{:.0f}", sufixo="", padrao="—"):
    return padrao if valor is None else formato.format(valor) + sufixo


def _gb(bytes_):
    return None if bytes_ is None else bytes_ / (1024 ** 3)


class Plugin(PluginBase):
    nome = "Monitor do PC"
    versao = "0.1.0"

    def __init__(self, app):
        super().__init__(app)
        self._dados = {}
        self._categoria_detalhe = None
        self._cor_texto = "#ffffff"
        self._config = self._carregar_config()

        self.page = QWidget(app.pages_container)
        self.page.setGeometry(0, 0, 150, 150)
        self.page.hide()
        self.conteudo = QWidget(self.page)
        layout = QVBoxLayout(self.conteudo)
        layout.setContentsMargins(0, 0, 0, 0)
        self.pilha = QStackedWidget()
        layout.addWidget(self.pilha)

        self.resumo = QWidget()
        layout_resumo = QVBoxLayout(self.resumo)
        layout_resumo.setContentsMargins(0, 0, 0, 0)
        layout_resumo.setSpacing(0)
        self.linhas = {}
        for chave, nome in CATEGORIAS:
            linha = LinhaClicavel(nome)
            linha.clicked.connect(lambda c=chave: self._abrir_detalhe(c))
            self.linhas[chave] = linha
            layout_resumo.addWidget(linha)
        self.pilha.addWidget(self.resumo)

        self.detalhe = PaginaDetalhe()
        self.detalhe.clicked.connect(self._voltar_resumo)
        self.pilha.addWidget(self.detalhe)

        self._aplicar_linhas_visiveis()
        self.coletor = Coletor(lambda: self._config)
        self.coletor.dados.connect(self._receber_dados)
        self.coletor.start()

    # --- integração com o app

    def criar_pagina(self):
        self.app.registrar_pagina(self.page, chave="monitor_pc", nome="Monitor")
        return None

    def ao_mudar_area_pagina(self, area):
        x, y, largura, altura = area
        self.conteudo.setGeometry(x, y, largura, altura)

    def ao_aplicar_tema(self):
        self._cor_texto = self.app.cor_texto
        estilo_nome = f"color: {COR_NOME}; font-family: 'Segoe UI'; font-size: 10px; font-weight: bold; background: transparent;"
        estilo_valor = f"color: {self._cor_texto}; font-family: 'Segoe UI'; font-size: 10px; background: transparent;"
        for linha in self.linhas.values():
            linha.nome.setStyleSheet(estilo_nome)
            linha.valor.setStyleSheet(estilo_valor)
        self.detalhe.titulo.setStyleSheet(
            f"color: {self._cor_texto}; font-family: 'Segoe UI'; font-size: 11px; font-weight: bold; background: transparent;"
        )
        self.detalhe.corpo.setStyleSheet(
            f"color: {self._cor_texto}; font-family: 'Segoe UI'; font-size: 10px; background: transparent;"
        )
        self._atualizar_interface()

    def encerrar(self):
        self.coletor.parar()
        self.coletor.wait(4000)
        return not self.coletor.isRunning()

    # --- configuração

    @staticmethod
    def _carregar_config():
        salvo = config_app.config_modulos.get(CHAVE_CONFIG, {})
        config = dict(PADRAO_CONFIG)
        if isinstance(salvo, dict):
            config.update(salvo)
        return config

    def abrir_configuracoes(self, parent=None):
        dialogo = QDialog(parent or self.app)
        dialogo.setWindowTitle("Configurações do Monitor do PC")
        layout = QVBoxLayout(dialogo)
        layout.addWidget(QLabel("Informações exibidas:"))
        checks = {}
        for chave, nome in CATEGORIAS:
            check = QCheckBox(nome)
            check.setChecked(chave in self._config["linhas"])
            checks[chave] = check
            layout.addWidget(check)

        linha_intervalo = QHBoxLayout()
        linha_intervalo.addWidget(QLabel("Atualizar a cada:"))
        combo = QComboBox()
        for segundos in (0.5, 1, 2, 5):
            combo.addItem(f"{segundos:g} s", float(segundos))
        indice = combo.findData(float(self._config["intervalo"]))
        combo.setCurrentIndex(indice if indice >= 0 else 1)
        linha_intervalo.addWidget(combo)
        layout.addLayout(linha_intervalo)

        check_fps = QCheckBox("Medir FPS e frametime (requer PresentMon)")
        check_fps.setChecked(bool(self._config["fps"]))
        layout.addWidget(check_fps)
        linha_exe = QHBoxLayout()
        campo_exe = QLineEdit(self._config["presentmon"])
        campo_exe.setPlaceholderText("Caminho do PresentMon.exe (opcional)")
        botao_exe = QPushButton("...")
        botao_exe.setFixedWidth(28)
        botao_exe.clicked.connect(lambda: campo_exe.setText(
            QFileDialog.getOpenFileName(dialogo, "PresentMon", "", "PresentMon (*.exe)")[0] or campo_exe.text()
        ))
        linha_exe.addWidget(campo_exe)
        linha_exe.addWidget(botao_exe)
        layout.addLayout(linha_exe)

        dica = QLabel(
            "Temperaturas de CPU/discos e RPM dos ventiladores exigem o LibreHardwareMonitor "
            "aberto (como administrador). Sem ele, o módulo usa as leituras do próprio Windows."
        )
        dica.setWordWrap(True)
        dica.setMaximumWidth(340)
        layout.addWidget(dica)

        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botoes.accepted.connect(dialogo.accept)
        botoes.rejected.connect(dialogo.reject)
        layout.addWidget(botoes)

        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return True

        novo = {
            "linhas": [c for c, check in checks.items() if check.isChecked()] or ["cpu"],
            "fps": check_fps.isChecked(),
            "presentmon": campo_exe.text().strip(),
            "intervalo": combo.currentData(),
        }
        self._config = {**PADRAO_CONFIG, **novo}
        modulos = dict(config_app.config_modulos)
        modulos[CHAVE_CONFIG] = novo
        config_app.config_modulos = modulos
        config_app.salvar()
        self._aplicar_linhas_visiveis()
        self._atualizar_interface()
        return True

    def _aplicar_linhas_visiveis(self):
        for chave, linha in self.linhas.items():
            linha.setVisible(chave in self._config["linhas"])

    # --- navegação

    def _reiniciar_inatividade(self):
        timer = getattr(self.app, "timer_inatividade", None)
        if timer is not None and timer.isActive():
            timer.start(15000)

    def _abrir_detalhe(self, chave):
        self._reiniciar_inatividade()
        self._categoria_detalhe = chave
        self.pilha.setCurrentIndex(1)
        self._atualizar_interface()

    def _voltar_resumo(self):
        self._reiniciar_inatividade()
        self._categoria_detalhe = None
        self.pilha.setCurrentIndex(0)

    # --- dados

    def _receber_dados(self, dados):
        self._dados = dados
        self.coletor.visivel = self.page.isVisible()
        self._atualizar_interface()

    def _cor_temp(self, temp, limite):
        if temp is None:
            return self._cor_texto
        if temp >= limite:
            return COR_ALERTA
        if temp >= limite - 10:
            return COR_ATENCAO
        return self._cor_texto

    def _temp_html(self, temp, limite):
        if temp is None:
            return ""
        return f"<span style='color:{self._cor_temp(temp, limite)}'>{temp:.0f}°C</span>"

    def _atualizar_interface(self):
        d = self._dados
        if not d:
            return
        resumos = self._resumos(d)
        for chave, linha in self.linhas.items():
            linha.valor.setText(resumos.get(chave, "—"))
        if self._categoria_detalhe:
            self._montar_detalhe(self._categoria_detalhe, d)

    def _resumos(self, d):
        cpu, gpu, ram, disco, fan, fps = d["cpu"], d["gpu"], d["ram"], d["disco"], d["fan"], d["fps"]
        sep = " · "
        partes = [_fmt(cpu.get("uso"), "{:.0f}%")]
        if cpu.get("temp") is not None:
            partes.append(self._temp_html(cpu["temp"], LIMITE_TEMP_CPU))
        if cpu.get("freq"):
            partes.append(f"{cpu['freq'] / 1000:.1f}G")
        resumos = {"cpu": sep.join(partes)}

        partes = [_fmt(gpu.get("uso"), "{:.0f}%")]
        if gpu.get("temp") is not None:
            partes.append(self._temp_html(gpu["temp"], LIMITE_TEMP_GPU))
        if gpu.get("vram_usada") is not None:
            total = f"/{_gb(gpu['vram_total']):.0f}" if gpu.get("vram_total") else ""
            partes.append(f"{_gb(gpu['vram_usada']):.1f}{total}G")
        resumos["gpu"] = sep.join(partes)

        resumos["ram"] = (
            f"{_gb(ram['usada']):.1f}/{_gb(ram['total']):.0f}G"
            + (f"{sep}{ram['freq']}" if ram.get("freq") else "")
        ) if ram.get("total") else "—"

        unidades = disco.get("unidades") or []
        if unidades:
            principal = max(unidades, key=lambda u: u["pct"])
            texto = f"{principal['letra']} {principal['pct']:.0f}%"
            temps = disco.get("temps") or []
            if temps:
                texto += sep + self._temp_html(max(t["temp"] for t in temps), LIMITE_TEMP_DISCO)
            resumos["disco"] = texto
        else:
            resumos["disco"] = "—"

        fans = fan.get("fans") or []
        rpm = [f for f in fans if f["unidade"] == "rpm"]
        if rpm:
            resumos["fan"] = sep.join(f"{f['valor']:.0f}" for f in rpm[:2]) + " rpm"
        elif fans:
            resumos["fan"] = sep.join(f"{f['valor']:.0f}%" for f in fans[:2])
        else:
            resumos["fan"] = "sem sensor"

        if not fps.get("ativo"):
            resumos["fps"] = "desativado"
        elif fps.get("fps") is not None:
            resumos["fps"] = f"{fps['fps']:.0f}{sep}{fps['frametime']:.1f}ms"
        else:
            resumos["fps"] = "sem jogo" if not fps.get("erro") else "indisponível"
        return resumos

    def _montar_detalhe(self, chave, d):
        det = self.detalhe
        nomes = dict(CATEGORIAS)
        det.titulo.setText(nomes.get(chave, chave))
        det.barras.setVisible(chave == "cpu")
        linhas = []

        def item(nome, valor):
            linhas.append(f"<span style='color:{COR_NOME}'>{nome}</span> {valor}")

        if chave == "cpu":
            cpu = d["cpu"]
            det.barras.definir(cpu.get("nucleos") or [])
            item("Package", _fmt(cpu.get("uso"), "{:.0f}%") + f" ({len(cpu.get('nucleos') or [])} núcleos)")
            if cpu.get("freq"):
                item("Clock", f"{cpu['freq'] / 1000:.2f} GHz")
            if cpu.get("temp") is not None:
                item("Temp", self._temp_html(cpu["temp"], LIMITE_TEMP_CPU)
                     + f" <span style='color:{COR_NOME}'>mín {_fmt(cpu.get('temp_min'))} máx {_fmt(cpu.get('temp_max'))}</span>")
            else:
                item("Temp", "sem sensor")
        elif chave == "gpu":
            gpu = d["gpu"]
            item("Uso", _fmt(gpu.get("uso"), "{:.0f}%"))
            item("Temp", self._temp_html(gpu["temp"], LIMITE_TEMP_GPU) if gpu.get("temp") is not None else "sem sensor")
            if gpu.get("vram_usada") is not None:
                total = f" / {_gb(gpu['vram_total']):.1f} GB" if gpu.get("vram_total") else ""
                item("VRAM", f"{_gb(gpu['vram_usada']):.1f}{total}")
            if gpu.get("nome"):
                item("", gpu["nome"])
        elif chave == "ram":
            ram = d["ram"]
            item("Em uso", f"{_gb(ram['usada']):.1f} GB ({_fmt(ram.get('pct'), '{:.0f}%')})")
            item("Livre", f"{_gb(ram['livre']):.1f} GB")
            item("Total", f"{_gb(ram['total']):.0f} GB")
            item("Freq.", f"{ram['freq']} MHz" if ram.get("freq") else "—")
        elif chave == "disco":
            for u in d["disco"].get("unidades") or []:
                item(u["letra"], f"{_gb(u['usado']):.0f}/{_gb(u['total']):.0f} GB ({u['pct']:.0f}%)")
            for t in d["disco"].get("temps") or []:
                item(t["nome"][:14], self._temp_html(t["temp"], LIMITE_TEMP_DISCO))
            if not d["disco"].get("temps"):
                item("Temp", "sem sensor")
        elif chave == "fan":
            fans = d["fan"].get("fans") or []
            for f in fans:
                item(f["nome"][:16], f"{f['valor']:.0f} {f['unidade']}")
            if not fans:
                linhas.append("Sem leitura. Abra o LibreHardwareMonitor.")
        elif chave == "fps":
            fps = d["fps"]
            if not fps.get("ativo"):
                linhas.append("Ative em Configurações do módulo.")
            elif fps.get("fps") is None:
                linhas.append(fps.get("erro") or "Aguardando um jogo...")
            else:
                item("Jogo", str(fps["app"])[:16])
                item("FPS", f"{fps['fps']:.0f}")
                item("Frametime", f"{fps['frametime']:.1f} ms")
                item("Pior", f"{fps['pior']:.1f} ms")
        det.corpo.setText("<br>".join(linhas))
