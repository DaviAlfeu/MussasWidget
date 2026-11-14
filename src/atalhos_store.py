import json
import os
import time
import uuid

from config import APPDATA_DIR


ARQUIVO_ATALHOS_V2 = os.path.join(APPDATA_DIR, "atalhos_v2.json")


class AtalhosStore:
    def __init__(self, config):
        self._config = config
        self._itens = []
        self._carregar_ou_migrar()

    def _carregar_ou_migrar(self):
        if os.path.isfile(ARQUIVO_ATALHOS_V2):
            try:
                with open(ARQUIVO_ATALHOS_V2, "r", encoding="utf-8") as arquivo:
                    dados = json.load(arquivo)
                itens = dados.get("itens", [])
                if isinstance(itens, list):
                    self._itens = [self._normalizar_item(item) for item in itens]
                    self._itens = [item for item in self._itens if item is not None]
                    self._sincronizar_legacy(salvar_config=False)
                    return
            except (OSError, ValueError, TypeError):
                pass

        self._migrar_legacy()

    def _migrar_legacy(self):
        atalhos = [
            caminho for caminho in getattr(self._config, "atalhos", [])
            if isinstance(caminho, str) and caminho.strip()
        ]
        nomes = getattr(self._config, "nomes_atalhos", {})
        tempos = getattr(self._config, "tempos_uso", {})
        agora = int(time.time())
        self._itens = []
        for caminho in atalhos:
            nome = ""
            if isinstance(nomes, dict):
                valor_nome = nomes.get(caminho, "")
                if isinstance(valor_nome, str):
                    nome = valor_nome.strip()[:120]
            segundos = 0.0
            if isinstance(tempos, dict):
                try:
                    segundos = max(0.0, float(tempos.get(caminho, 0.0)))
                except (TypeError, ValueError):
                    segundos = 0.0
            self._itens.append({
                "id": uuid.uuid4().hex,
                "caminho": caminho,
                "nome": nome,
                "segundos": segundos,
                "criado_em": agora,
            })
        self._salvar_arquivo()
        self._sincronizar_legacy(salvar_config=True)

    @staticmethod
    def _normalizar_item(item):
        if not isinstance(item, dict):
            return None
        caminho = item.get("caminho")
        if not isinstance(caminho, str) or not caminho.strip():
            return None
        nome = item.get("nome", "")
        if not isinstance(nome, str):
            nome = ""
        try:
            segundos = max(0.0, float(item.get("segundos", 0.0)))
        except (TypeError, ValueError):
            segundos = 0.0
        criado_em = item.get("criado_em")
        if not isinstance(criado_em, int):
            criado_em = int(time.time())
        identificador = item.get("id")
        if not isinstance(identificador, str) or not identificador:
            identificador = uuid.uuid4().hex
        return {
            "id": identificador,
            "caminho": caminho.strip(),
            "nome": nome.strip()[:120],
            "segundos": segundos,
            "criado_em": criado_em,
        }

    def _sincronizar_legacy(self, salvar_config):
        self._config.atalhos = [item["caminho"] for item in self._itens]
        self._config.nomes_atalhos = {
            item["caminho"]: item["nome"]
            for item in self._itens
            if item["nome"]
        }
        self._config.tempos_uso = {
            item["caminho"]: item["segundos"] for item in self._itens
        }
        if salvar_config:
            self._config.salvar()

    def _salvar_arquivo(self):
        os.makedirs(APPDATA_DIR, exist_ok=True)
        temporario = ARQUIVO_ATALHOS_V2 + ".tmp"
        conteudo = {
            "versao": 2,
            "atualizado_em": int(time.time()),
            "itens": self._itens,
        }
        with open(temporario, "w", encoding="utf-8") as arquivo:
            json.dump(conteudo, arquivo, ensure_ascii=False, indent=2)
        os.replace(temporario, ARQUIVO_ATALHOS_V2)

    def caminhos(self):
        return [item["caminho"] for item in self._itens]

    def quantidade(self):
        return len(self._itens)

    def caminho_por_indice(self, indice):
        return self._itens[indice]["caminho"]

    def nome_customizado(self, caminho):
        for item in self._itens:
            if item["caminho"] == caminho:
                return item["nome"]
        return ""

    def segundos_uso(self, caminho):
        for item in self._itens:
            if item["caminho"] == caminho:
                return item["segundos"]
        return 0.0

    def adicionar(self, caminho):
        if not isinstance(caminho, str) or not caminho.strip():
            return False
        self._itens.append({
            "id": uuid.uuid4().hex,
            "caminho": caminho.strip(),
            "nome": "",
            "segundos": 0.0,
            "criado_em": int(time.time()),
        })
        self._salvar_arquivo()
        self._sincronizar_legacy(salvar_config=True)
        return True

    def remover(self, indice):
        if indice < 0 or indice >= len(self._itens):
            return False
        self._itens.pop(indice)
        self._salvar_arquivo()
        self._sincronizar_legacy(salvar_config=True)
        return True

    def mover(self, origem, destino):
        if (
            origem < 0 or origem >= len(self._itens)
            or destino < 0 or destino > len(self._itens)
            or origem == destino
        ):
            return False
        item = self._itens.pop(origem)
        self._itens.insert(destino, item)
        self._salvar_arquivo()
        self._sincronizar_legacy(salvar_config=True)
        return True

    def renomear(self, caminho, novo_nome):
        for item in self._itens:
            if item["caminho"] != caminho:
                continue
            item["nome"] = (novo_nome or "").strip()[:120]
            self._salvar_arquivo()
            self._sincronizar_legacy(salvar_config=True)
            return True
        return False

    def incrementar_tempo(self, caminho, delta):
        for item in self._itens:
            if item["caminho"] != caminho:
                continue
            item["segundos"] = max(0.0, item["segundos"] + delta)
            return True
        return False

    def salvar_tempos(self):
        self._salvar_arquivo()
        self._sincronizar_legacy(salvar_config=False)
