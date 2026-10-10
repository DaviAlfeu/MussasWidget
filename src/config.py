import os
import sys
import json
import winreg

APP_VERSION = "1.3.3"
URL_UPDATE_CHECK = "https://raw.githubusercontent.com/DaviAlfeu/MussasWidget/main/version.json"
URL_DOWNLOAD_EXE = "https://github.com/DaviAlfeu/MussasWidget/raw/main/WidgetAniversarios.exe"
URL_CSV_ANIVERSARIOS = "https://docs.google.com/spreadsheets/d/1W1cX9dCAFnLPjDImSB6rjSSC0GhvOX0rp_HiaHeHAGI/export?format=csv&gid=0"
URL_CSV_JOGO = "https://docs.google.com/spreadsheets/d/1W1cX9dCAFnLPjDImSB6rjSSC0GhvOX0rp_HiaHeHAGI/export?format=csv&gid=36262169"
MARGEM_SEGURANCA_BOLINHAS = 19
MARGEM_AREA_ICONES = 14

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

TEMAS = {
    "claro": ("Claro", True, "#f5f5f5"),
    "escuro": ("Escuro", False, "#191919"),
    "azul_claro": ("Azul", True, "#78a5c4"),
    "azul_escuro": ("Azul Escuro", False, "#30424e"),
}

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
        self.tema = "escuro"
        self.modo_claro = False
        self.wallpaper = "Nenhum"
        self.desfoque = 20
        self.vidro_desfocado = False
        self.espessura_borda = 1.0
        self.pos_x = None
        self.pos_y = None
        self.atalhos = []
        self.tempos_uso = {}
        self.nomes_atalhos = {}
        self.monitorar_tempo_atalhos = True
        self.voltar_pagina_principal = True
        self.tempo_parabens = 10
        self.posicao_bolinhas = "baixo"
        self.indicador_pagina = "bolinhas"
        self.pagina_principal = ""
        self.config_modulos = {}
        self.carregar()

    def carregar(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    d = json.load(f)
                    self.iniciar_com_windows = d.get("iniciar_com_windows", False)
                    self.segundo_plano = d.get("segundo_plano", False)
                    self.sempre_no_topo = d.get("sempre_no_topo", False)
                    tema = d.get("tema")
                    if tema not in TEMAS:
                        tema = "claro" if d.get("modo_claro", False) else "escuro"
                    self.definir_tema(tema)
                    self.wallpaper = d.get("wallpaper", "Nenhum")
                    self.desfoque = NIVEIS_DESFOQUE[indice_desfoque(d.get("desfoque", 20))]
                    self.vidro_desfocado = bool(d.get("vidro_desfocado", False))
                    self.espessura_borda = NIVEIS_ESPESSURA[indice_espessura(d.get("espessura_borda", 1.0))]
                    self.pos_x = d.get("pos_x", None)
                    self.pos_y = d.get("pos_y", None)
                    self.atalhos = [a for a in d.get("atalhos", []) if a is not None]
                    self.tempos_uso = d.get("tempos_uso", {})
                    self.nomes_atalhos = d.get("nomes_atalhos", {})
                    self.monitorar_tempo_atalhos = d.get("monitorar_tempo_atalhos", True)
                    self.voltar_pagina_principal = d.get("voltar_pagina_principal", True)
                    self.tempo_parabens = max(10, min(20, int(d.get("tempo_parabens", 10))))
                    self.posicao_bolinhas = d.get("posicao_bolinhas", "baixo")
                    indicador = d.get("indicador_pagina", "bolinhas")
                    self.indicador_pagina = indicador if indicador in ("bolinhas", "numeros") else "bolinhas"
                    self.pagina_principal = d.get("pagina_principal", "")
                    config_modulos = d.get("config_modulos", {})
                    self.config_modulos = (
                        config_modulos if isinstance(config_modulos, dict) else {}
                    )
            except Exception:
                pass

    def definir_tema(self, tema):
        if tema not in TEMAS:
            tema = "escuro"
        self.tema = tema
        self.modo_claro = TEMAS[tema][1]

    @property
    def cor_base(self):
        return TEMAS[self.tema][2]

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
