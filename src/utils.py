import os
import sys
import tempfile
import subprocess
import time
from datetime import datetime
from PyQt6.QtGui import QFontDatabase
from config import CONFIG_FONTES

def parse_data_jogo_bg(valor):
    if not valor: return None
    valor = valor.strip()
    formatos = (
        "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
        "%d/%m/%y %H:%M:%S", "%d/%m/%y %H:%M", "%d/%m/%y"
    )
    for formato in formatos:
        try: return datetime.strptime(valor, formato)
        except ValueError: pass
    try: return datetime.fromisoformat(valor.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception: return None

def raio_desfoque(valor):
    try: valor = float(valor)
    except (TypeError, ValueError): valor = 0
    valor = max(0.0, min(100.0, valor))
    return int(round(valor * 50 / 100))

def alpha_desfoque(valor, alpha_min=30, alpha_max=225):
    try: valor = float(valor)
    except (TypeError, ValueError): valor = 0
    valor = max(0.0, min(100.0, valor))
    return alpha_min + int(round(valor * (alpha_max - alpha_min) / 100))

def get_app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    if os.path.basename(os.path.dirname(os.path.abspath(__file__))).lower() == "src":
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.dirname(os.path.abspath(sys.argv[0]))

def resource_path(filename):
    if getattr(sys, 'frozen', False):
        base = getattr(sys, '_MEIPASS', get_app_dir())
    else:
        base = get_app_dir()
    return os.path.join(base, filename)

def external_resource_path(filename):
    external = os.path.join(get_app_dir(), filename)
    if os.path.exists(external):
        return external
    return resource_path(filename)

def carregar_fontes():
    pastas = [
        os.path.join(get_app_dir(), "Fonts"),
        os.path.join(get_app_dir(), "WidgetAniversario", "Fonts"),
        resource_path("Fonts"),
        resource_path(os.path.join("WidgetAniversario", "Fonts")),
        "Fonts"
    ]
    for pasta in pastas:
        if os.path.exists(pasta):
            for arquivo in os.listdir(pasta):
                if arquivo.lower().endswith(('.ttf', '.otf')):
                    QFontDatabase.addApplicationFont(os.path.abspath(os.path.join(pasta, arquivo)))

def versao_tuple(valor):
    try: return tuple(int(p) for p in str(valor).strip().lstrip("vV").split(".")[:4])
    except Exception: return (0,)

def caminho_executavel_atual():
    if getattr(sys, "frozen", False):
        return os.path.abspath(sys.executable)
    return os.path.abspath(sys.argv[0])


def pasta_temporaria_widget():
    caminho = os.path.join(tempfile.gettempdir(), "MussasWidget")
    os.makedirs(caminho, exist_ok=True)
    return caminho


def limpar_versoes_antigas():
    pasta = os.path.join(tempfile.gettempdir(), "MussasWidget")
    if not os.path.isdir(pasta):
        return 0

    removidos = 0
    for entrada in os.scandir(pasta):
        if not entrada.is_file(follow_symlinks=False) or not entrada.name.lower().endswith(".old"):
            continue
        try:
            os.remove(entrada.path)
            removidos += 1
        except OSError:
            pass
    return removidos


def executar_atualizacao_bat(novo_exe):
    if not getattr(sys, "frozen", False):
        raise RuntimeError("A instalação automática exige o aplicativo compilado.")

    exe_atual = caminho_executavel_atual()
    novo_exe = os.path.abspath(novo_exe)
    if not os.path.isfile(novo_exe):
        raise FileNotFoundError(novo_exe)

    pasta_temporaria = pasta_temporaria_widget()
    caminho_old = os.path.join(
        pasta_temporaria,
        f"{os.path.basename(exe_atual)}.{os.getpid()}.old"
    )
    script_path = os.path.join(
        pasta_temporaria, f"mussas_update_{os.getpid()}_{time.time_ns()}.ps1"
    )
    escapar_powershell = lambda valor: "'" + valor.replace("'", "''") + "'"
    conteudo = f"""$ErrorActionPreference = 'Stop'
$currentPath = {escapar_powershell(exe_atual)}
$stagedPath = {escapar_powershell(novo_exe)}
$backupPath = {escapar_powershell(caminho_old)}
$targetPid = {os.getpid()}

while (Get-Process -Id $targetPid -ErrorAction SilentlyContinue) {{
    Start-Sleep -Milliseconds 200
}}

try {{
    if (Test-Path -LiteralPath $backupPath) {{
        Remove-Item -LiteralPath $backupPath -Force
    }}
    Move-Item -LiteralPath $currentPath -Destination $backupPath -Force
    try {{
        Move-Item -LiteralPath $stagedPath -Destination $currentPath -Force
    }} catch {{
        if (Test-Path -LiteralPath $backupPath) {{
            Move-Item -LiteralPath $backupPath -Destination $currentPath -Force
        }}
        throw
    }}
    Unblock-File -LiteralPath $currentPath -ErrorAction SilentlyContinue
    Start-Process -FilePath $currentPath
}} catch {{
    if (-not (Test-Path -LiteralPath $currentPath) -and (Test-Path -LiteralPath $backupPath)) {{
        Move-Item -LiteralPath $backupPath -Destination $currentPath -Force
    }}
}} finally {{
    Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
}}
"""
    with open(script_path, "w", encoding="utf-8-sig", newline="\r\n") as arquivo:
        arquivo.write(conteudo)

    CREATE_NO_WINDOW = 0x08000000
    try:
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script_path],
            creationflags=CREATE_NO_WINDOW
        )
    except Exception:
        try:
            os.remove(script_path)
        except OSError:
            pass
        raise

def normalizar_cor_hex(valor):
    valor = (valor or "").strip().replace(" ", "")
    if valor.startswith("#"):
        valor = valor[1:]
    if len(valor) not in (3, 4, 6, 8): return "#ffffff"
    try: int(valor, 16)
    except ValueError: return "#ffffff"
    return "#" + valor

def aplicar_css_fonte_base(key):
    f = CONFIG_FONTES.get(key, {"fonte": "Segoe UI", "tamanho": 11, "peso": "normal"})
    peso = "bold" if f["peso"] == "bold" else "normal"
    return f"font-family: '{f['fonte']}', 'Segoe UI'; font-size: {f['tamanho']}px; font-weight: {peso}; background: transparent; border: none;"
