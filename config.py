import os
import sys
import json
import winreg

APP_VERSION = "1.1.2"
URL_UPDATE_CHECK = "https://raw.githubusercontent.com/DaviAlfeu/MussasWidget/main/version.json"
URL_DOWNLOAD_EXE = "https://github.com/DaviAlfeu/MussasWidget/raw/main/WidgetAniversarios.exe"
URL_CSV_ANIVERSARIOS = "https://docs.google.com/spreadsheets/d/1W1cX9dCAFnLPjDImSB6rjSSC0GhvOX0rp_HiaHeHAGI/export?format=csv&gid=0"
URL_CSV_JOGO = "https://docs.google.com/spreadsheets/d/1W1cX9dCAFnLPjDImSB6rjSSC0GhvOX0rp_HiaHeHAGI/export?format=csv&gid=36262169"

CONFIG_FONTES = {
    "nome": {"fonte": "Lemon Milk", "tamanho": 16, "peso": "bold"},
    "data": {"fonte": "Roboto", "tamanho": 12, "peso": "light"},
    "faltam": {"fonte": "Roboto", "tamanho": 12, "peso": "light"},
    "dias": {"fonte": "Lemon Milk", "tamanho": 16, "peso": "bold"},
    "parabens_titulo": {"fonte": "Lemon Milk", "tamanho": 14, "peso": "bold"},
    "parabens_nome": {"fonte": "Lemon Milk", "tamanho": 15, "peso": "bold"},
    "lista": {"fonte": "Lemon Milk", "tamanho": 11, "peso": "bold"},
    "cal_meses": {"fonte": "Roboto", "tamanho": 11, "peso": "light"},
    "cal_titulo": {"fonte": "Lemon Milk", "tamanho": 13, "peso": "bold"},
    "cal_lista": {"fonte": "Lemon Milk", "tamanho": 11, "peso": "bold"}
}

APPDATA_DIR = os.path.join(os.getenv('APPDATA', os.path.expanduser('~')), "MussasWidget")
os.makedirs(APPDATA_DIR, exist_ok=True)

PASTA_WALLPAPERS = os.path.join(APPDATA_DIR, "Wallpapers")
os.makedirs(PASTA_WALLPAPERS, exist_ok=True)

STATE_FILE = os.path.join(APPDATA_DIR, "parabens_played.txt")
CONFIG_FILE = os.path.join(APPDATA_DIR, "config.json")

NIVEIS_DESFOQUE = [0, 20, 40, 60, 80, 100]
NIVEIS_ESPESSURA = [0.0, 0.5, 1.0, 1.5, 2.0]

def indice_desfoque(valor):
    try: valor = float(valor)
    except (TypeError, ValueError): valor = 0
    return min(range(len(NIVEIS_DESFOQUE)), key=lambda i: abs(NIVEIS_DESFOQUE[i] - valor))

def indice_espessura(valor):
    try: valor = float(valor)
    except (TypeError, ValueError): valor = 0
    return min(range(len(NIVEIS_ESPESSURA)), key=lambda i: abs(NIVEIS_ESPESSURA[i] - valor))

class Configuracoes:
    def __init__(self):
        self.iniciar_com_windows = False
        self.segundo_plano = False
        self.sempre_no_topo = False
        self.modo_claro = False
        self.wallpaper = "Nenhum"
        self.desfoque = 20
        self.espessura_borda = 1.0
        self.pos_x = None
        self.pos_y = None
        self.atalhos = []
        self.tempos_uso = {}
        self.nomes_atalhos = {}
        self.monitorar_tempo_atalhos = True
        self.tempo_parabens = 10
        self.carregar()

    def carregar(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    d = json.load(f)
                    self.iniciar_com_windows = d.get("iniciar_com_windows", False)
                    self.segundo_plano = d.get("segundo_plano", False)
                    self.sempre_no_topo = d.get("sempre_no_topo", False)
                    self.modo_claro = d.get("modo_claro", False)
                    self.wallpaper = d.get("wallpaper", "Nenhum")
                    self.desfoque = NIVEIS_DESFOQUE[indice_desfoque(d.get("desfoque", 20))]
                    self.espessura_borda = NIVEIS_ESPESSURA[indice_espessura(d.get("espessura_borda", 1.0))]
                    self.pos_x = d.get("pos_x", None)
                    self.pos_y = d.get("pos_y", None)
                    self.atalhos = [a for a in d.get("atalhos", []) if a is not None]
                    self.tempos_uso = d.get("tempos_uso", {})
                    self.nomes_atalhos = d.get("nomes_atalhos", {})
                    self.monitorar_tempo_atalhos = d.get("monitorar_tempo_atalhos", True)
                    self.tempo_parabens = max(10, min(20, int(d.get("tempo_parabens", 10))))
            except Exception:
                pass

    def salvar(self):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.__dict__, f)
        except Exception:
            pass

    def aplicar_registro_windows(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_ALL_ACCESS)
            if getattr(sys, 'frozen', False):
                app_path = os.path.abspath(sys.executable)
            else:
                app_path = os.path.abspath(sys.argv[0])

            if self.iniciar_com_windows:
                winreg.SetValueEx(key, "WidgetAniversarios", 0, winreg.REG_SZ, f'"{app_path}"')
            else:
                winreg.DeleteValue(key, "WidgetAniversarios")
            winreg.CloseKey(key)
        except Exception:
            pass

config_app = Configuracoes()
