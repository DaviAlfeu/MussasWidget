import os
import ast
import importlib.util
import json
import tempfile
import urllib.request
from PyQt6.QtCore import QThread, QTimer
from PyQt6.QtMultimedia import QMediaPlayer
from config import APPDATA_DIR

PASTA_MODULOS = os.path.join(APPDATA_DIR, "Modulos")
os.makedirs(PASTA_MODULOS, exist_ok=True)

URL_MODULOS_GITHUB = "https://api.github.com/repos/DaviAlfeu/MussasWidget/contents/Modulos"
URL_DOWNLOAD_MODULOS_GITHUB = "https://raw.githubusercontent.com/DaviAlfeu/MussasWidget/"


def _extrair_versao_modulo(conteudo):
    try:
        arvore = ast.parse(conteudo.decode("utf-8-sig"))
    except (UnicodeDecodeError, SyntaxError):
        return None

    for classe in arvore.body:
        if not isinstance(classe, ast.ClassDef) or classe.name != "Plugin":
            continue
        for instrucao in classe.body:
            if isinstance(instrucao, ast.Assign):
                alvos = instrucao.targets
            elif isinstance(instrucao, ast.AnnAssign):
                alvos = [instrucao.target]
            else:
                continue
            if any(isinstance(alvo, ast.Name) and alvo.id == "versao" for alvo in alvos):
                if isinstance(instrucao.value, ast.Constant) and isinstance(instrucao.value.value, str):
                    return instrucao.value.value
    return None


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
            versao = None
            try:
                req_modulo = urllib.request.Request(
                    url, headers={"User-Agent": "MussasWidget"}
                )
                with urllib.request.urlopen(req_modulo, timeout=10) as resposta_modulo:
                    versao = _extrair_versao_modulo(resposta_modulo.read())
            except Exception:
                pass
            modulos.append({"nome": nome, "url": url, "versao": versao})
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

    def encerrar(self):
        """Libera recursos do plugin antes de removê-lo do aplicativo."""
        return True


class GerenciadorModulos:
    def __init__(self, main_app):
        self.main_app = main_app
        self.modulos_carregados = []
        self._registros_modulos = {}

    def carregar_modulos(self):
        """Varre a pasta de módulos e carrega plugins."""
        for arquivo in sorted(os.listdir(PASTA_MODULOS)):
            if not arquivo.endswith('.py'):
                continue
            self.ativar_modulo(arquivo)

    def ativar_modulo(self, arquivo):
        if (not isinstance(arquivo, str) or not arquivo.endswith(".py")
                or os.path.basename(arquivo) != arquivo):
            raise ValueError("Nome de módulo inválido.")
        if arquivo in self._registros_modulos:
            return True

        caminho = os.path.join(PASTA_MODULOS, arquivo)
        if not os.path.isfile(caminho):
            return False

        nome_modulo = arquivo[:-3]
        paginas_antes = set(self.main_app.paginas)
        botoes_antes = self._botoes_topo_atuais()
        try:
            spec = importlib.util.spec_from_file_location(nome_modulo, caminho)
            if spec is None or spec.loader is None:
                raise ImportError(f"Não foi possível carregar {arquivo}.")
            modulo = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(modulo)
            if not hasattr(modulo, "Plugin"):
                return False

            plugin = modulo.Plugin(self.main_app)
            self._registrar_plugin(plugin)
            paginas = [pagina for pagina in self.main_app.paginas if pagina not in paginas_antes]
            botoes = [botao for botao in self._botoes_topo_atuais() if botao not in botoes_antes]
            self.modulos_carregados.append(plugin)
            self._registros_modulos[arquivo] = {
                "plugin": plugin,
                "paginas": paginas,
                "botoes": botoes,
                "encerrando": False
            }
            self.main_app._aplicar_area_segura_paginas()
            self.main_app._criar_dots_pagina()
            self.main_app.posicionar_elementos()
            try:
                plugin.ao_aplicar_tema()
            except Exception as erro:
                print(f"[Módulo] Erro ao aplicar tema em '{plugin.nome}': {erro}")
            print(f"[Módulo] '{plugin.nome}' v{plugin.versao} carregado.")
            return True
        except Exception as erro:
            print(f"[Módulo] Erro ao carregar '{nome_modulo}': {erro}")
            return False

    def desativar_modulo(self, arquivo):
        registro = self._registros_modulos.get(arquivo)
        if registro is None:
            return True

        plugin = registro["plugin"]
        if not registro["encerrando"]:
            registro["encerrando"] = True
            plugin._encerrando = True
            try:
                plugin.encerrar()
            except Exception as erro:
                print(f"[Módulo] Erro ao encerrar '{plugin.nome}': {erro}")

            for recurso in vars(plugin).values():
                if isinstance(recurso, QTimer):
                    recurso.stop()
                elif isinstance(recurso, QMediaPlayer):
                    recurso.stop()

            calendario = getattr(plugin, "janela_calendario", None)
            if calendario is not None:
                calendario.hide()
                calendario.deleteLater()
                if getattr(self.main_app, "janela_calendario", None) is calendario:
                    self.main_app.janela_calendario = None
                    self.main_app.calendario_aberto = False

        workers_ativos = [
            recurso for recurso in vars(plugin).values()
            if isinstance(recurso, QThread) and recurso.isRunning()
        ]
        if workers_ativos:
            QTimer.singleShot(150, lambda: self.desativar_modulo(arquivo))
            return False

        pagina_atual = (
            self.main_app.paginas[self.main_app.pagina_atual]
            if self.main_app.paginas else None
        )
        animacao = getattr(self.main_app, "anim_group", None)
        if animacao is not None:
            animacao.stop()

        paginas_removidas = registro["paginas"]
        for pagina in paginas_removidas:
            if pagina in self.main_app.paginas:
                self.main_app.paginas.remove(pagina)
            pagina.hide()
            pagina.setParent(None)
            pagina.deleteLater()

        for botao in registro["botoes"]:
            self.main_app.top_layout.removeWidget(botao)
            botao.hide()
            botao.deleteLater()

        if plugin in self.modulos_carregados:
            self.modulos_carregados.remove(plugin)
        del self._registros_modulos[arquivo]

        if pagina_atual in self.main_app.paginas:
            self.main_app.pagina_atual = self.main_app.paginas.index(pagina_atual)
        else:
            self.main_app.pagina_atual = self.main_app._indice_pagina_principal()

        self.main_app._posicao_botoes_modulos = max(
            0, self.main_app.top_layout.indexOf(self.main_app.btn_config)
        )
        self.main_app._criar_dots_pagina()
        self.main_app.posicionar_elementos()
        self.main_app.aplicar_tema()
        return True

    def _botoes_topo_atuais(self):
        botoes = []
        for indice in range(self.main_app.top_layout.count()):
            botao = self.main_app.top_layout.itemAt(indice).widget()
            if botao is not None:
                botoes.append(botao)
        return botoes

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
