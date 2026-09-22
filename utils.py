import os
import sys
import tempfile
import subprocess
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

def executar_atualizacao_bat(novo_exe):
    exe_atual = caminho_executavel_atual()
    caminho_old = exe_atual + ".old"
    bat_path = os.path.join(tempfile.gettempdir(), f"mussas_update_{os.getpid()}.bat")
    conteudo = f"""@echo off
ping 127.0.0.1 -n 4 > NUL
taskkill /F /PID {os.getpid()} > NUL 2>&1
ping 127.0.0.1 -n 8 > NUL
del /q "{caminho_old}" > NUL 2>&1
move /Y "{exe_atual}" "{caminho_old}" > NUL 2>&1
move /Y "{novo_exe}" "{exe_atual}" > NUL 2>&1
powershell -windowstyle hidden -Command "Unblock-File -LiteralPath '{exe_atual}'" > NUL 2>&1
ping 127.0.0.1 -n 4 > NUL
start "" "{exe_atual}"
del "%~f0" > NUL 2>&1
"""
    with open(bat_path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(conteudo)
    CREATE_NO_WINDOW = 0x08000000
    subprocess.Popen([bat_path], creationflags=CREATE_NO_WINDOW)

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
