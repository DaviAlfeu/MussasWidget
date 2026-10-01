import os
import importlib.util
import json
import tempfile
import urllib.request
from config import APPDATA_DIR

PASTA_MODULOS = os.path.join(APPDATA_DIR, "Modulos")
os.makedirs(PASTA_MODULOS, exist_ok=True)

URL_MODULOS_GITHUB = "https://api.github.com/repos/DaviAlfeu/MussasWidget/contents/Modulos"
URL_DOWNLOAD_MODULOS_GITHUB = "https://raw.githubusercontent.com/DaviAlfeu/MussasWidget/"


def listar_modulos_github():
    requisicao = urllib.request.Request(
        URL_MODULOS_GITHUB,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "MussasWidget"}
    )
    with urllib.request.urlopen(requisicao, timeout=15) as resposta:
        entradas = json.loads(resposta.read().decode("utf-8"))

    if not isinstance(entradas, list):
        raise ValueError("A resposta do GitHub não contém uma lista de módulos.")

    modulos = []
    for entrada in entradas:
        nome = entrada.get("name", "")
        url = entrada.get("download_url")
        if (entrada.get("type") == "file" and isinstance(nome, str)
                and nome.endswith(".py") and os.path.basename(nome) == nome
                and isinstance(url, str) and url.startswith(URL_DOWNLOAD_MODULOS_GITHUB)):
            modulos.append({"nome": nome, "url": url})
    return sorted(modulos, key=lambda modulo: modulo["nome"].lower())


def baixar_modulo_github(nome, url):
    if (not isinstance(nome, str) or not nome.endswith(".py")
            or os.path.basename(nome) != nome):
        raise ValueError("Nome de módulo inválido.")
    if not isinstance(url, str) or not url.startswith(URL_DOWNLOAD_MODULOS_GITHUB):
        raise ValueError("URL de download não permitida.")

    requisicao = urllib.request.Request(url, headers={"User-Agent": "MussasWidget"})
    with urllib.request.urlopen(requisicao, timeout=30) as resposta:
        conteudo = resposta.read()

    descritor, caminho_temporario = tempfile.mkstemp(
        prefix=".modulo_", suffix=".tmp", dir=PASTA_MODULOS
    )
    try:
        with os.fdopen(descritor, "wb") as arquivo:
            arquivo.write(conteudo)
        os.replace(caminho_temporario, os.path.join(PASTA_MODULOS, nome))
    except Exception:
        if os.path.exists(caminho_temporario):
            os.remove(caminho_temporario)
        raise
    return nome


def _validar_nome_modulo(nome):
    if (not isinstance(nome, str) or not nome.endswith(".py")
            or os.path.basename(nome) != nome):
        raise ValueError("Nome de módulo inválido.")


def estado_modulo(nome):
    _validar_nome_modulo(nome)
    caminho_ativo = os.path.join(PASTA_MODULOS, nome)
    caminho_desativado = caminho_ativo + ".disabled"
    if os.path.isfile(caminho_ativo):
        return "ativo"
    if os.path.isfile(caminho_desativado):
        return "desativado"
    return "nao_instalado"


def alterar_estado_modulo(nome, ativar):
    _validar_nome_modulo(nome)
    caminho_ativo = os.path.join(PASTA_MODULOS, nome)
    caminho_desativado = caminho_ativo + ".disabled"
    origem, destino = (
        (caminho_desativado, caminho_ativo) if ativar
        else (caminho_ativo, caminho_desativado)
    )
    if not os.path.isfile(origem):
        raise FileNotFoundError("O arquivo do módulo não está no estado esperado.")
    if os.path.exists(destino):
        raise FileExistsError("Já existe um arquivo do módulo no destino.")
    os.replace(origem, destino)
    return nome


def excluir_modulo(nome):
    _validar_nome_modulo(nome)
    caminho_ativo = os.path.join(PASTA_MODULOS, nome)
    caminhos = (caminho_ativo, caminho_ativo + ".disabled")
    encontrados = [caminho for caminho in caminhos if os.path.isfile(caminho)]
    if not encontrados:
        raise FileNotFoundError("O módulo não está instalado.")
    for caminho in encontrados:
        os.remove(caminho)
    return nome


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

    def ao_mudar_area_pagina(self, area):
        """Chamado quando a área disponível das páginas muda."""
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

    def notificar_area_pagina(self, area):
        for plugin in self.modulos_carregados:
            try:
                plugin.ao_mudar_area_pagina(area)
            except Exception as e:
                print(f"[Módulo] Erro em ao_mudar_area_pagina de '{plugin.nome}': {e}")
