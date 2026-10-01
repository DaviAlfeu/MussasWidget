import os
import importlib.util
from config import APPDATA_DIR

PASTA_MODULOS = os.path.join(APPDATA_DIR, "Modulos")
os.makedirs(PASTA_MODULOS, exist_ok=True)

URL_MODULOS_GITHUB = "https://api.github.com/repos/DaviAlfeu/MussasWidget/contents/Modulos"


class PluginBase:
    """Classe base que todo módulo deve herdar."""
    nome = "Plugin"
    versao = "1.0.0"

    def __init__(self, app):
        self.app = app

    def criar_pagina(self):
        """Retorna um QWidget para ser adicionado como página, ou None."""
        return None

    def botoes_topo(self):
        """Retorna lista de dicts: [{nome_png, texto_fallback, callback}, ...] ou []."""
        return []

    def ao_aplicar_tema(self):
        """Chamado quando o tema muda. Override para atualizar estilos."""
        pass

    def ao_baixar_dados(self, *args):
        """Chamado quando novos dados são baixados da planilha. Override se necessário."""
        pass


class GerenciadorModulos:
    def __init__(self, main_app):
        self.main_app = main_app
        self.modulos_carregados = []

    def carregar_modulos(self):
        """Varre a pasta de módulos e carrega plugins."""
        for arquivo in sorted(os.listdir(PASTA_MODULOS)):
            if not arquivo.endswith('.py'):
                continue
            caminho = os.path.join(PASTA_MODULOS, arquivo)
            nome_modulo = arquivo[:-3]
            try:
                spec = importlib.util.spec_from_file_location(nome_modulo, caminho)
                modulo = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(modulo)

                if hasattr(modulo, 'Plugin'):
                    plugin = modulo.Plugin(self.main_app)
                    self._registrar_plugin(plugin)
                    self.modulos_carregados.append(plugin)
                    print(f"[Módulo] '{plugin.nome}' v{plugin.versao} carregado.")
            except Exception as e:
                print(f"[Módulo] Erro ao carregar '{nome_modulo}': {e}")

    def _registrar_plugin(self, plugin):
        """Registra página e botões de um plugin no app principal."""
        pagina = plugin.criar_pagina()
        if pagina is not None:
            self.main_app.registrar_pagina(pagina)

        for btn_info in plugin.botoes_topo():
            self.main_app.adicionar_botao_topo(
                btn_info.get("nome_png", ""),
                btn_info.get("texto_fallback", "?"),
                btn_info.get("callback", lambda: None)
            )

    def notificar_tema(self):
        """Notifica todos os módulos sobre mudança de tema."""
        for plugin in self.modulos_carregados:
            try:
                plugin.ao_aplicar_tema()
            except Exception as e:
                print(f"[Módulo] Erro em ao_aplicar_tema de '{plugin.nome}': {e}")

    def notificar_dados(self, *args):
        """Notifica todos os módulos sobre novos dados baixados."""
        for plugin in self.modulos_carregados:
            try:
                plugin.ao_baixar_dados(*args)
            except Exception as e:
                print(f"[Módulo] Erro em ao_baixar_dados de '{plugin.nome}': {e}")
