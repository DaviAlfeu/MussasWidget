import time
import subprocess
import urllib.request
import csv
import codecs
from PyQt6.QtCore import QThread, pyqtSignal
from utils import parse_data_jogo_bg
from config import URL_CSV_ANIVERSARIOS, URL_CSV_JOGO

class WorkerDownload(QThread):
    resultado = pyqtSignal(list, list, object, object, bytes, bytes)

    def run(self):
        dados_planilha = []
        dados_jogo = [{"imagem": "", "link": ""}, {"imagem": "", "link": ""}]
        data_inicio = None
        data_fim = None
        img_bytes1 = b""
        img_bytes2 = b""

        try:
            req_aniv = urllib.request.urlopen(URL_CSV_ANIVERSARIOS, timeout=10)
            csv_aniv = csv.reader(codecs.iterdecode(req_aniv, 'utf-8'))
            next(csv_aniv, None)
            for r in csv_aniv:
                if len(r) >= 2 and r[0].strip():
                    dados_planilha.append((r[0].strip(), r[1].strip(), r[2].strip() if len(r) >= 3 else ""))
        except Exception:
            pass

        try:
            req_jogo = urllib.request.urlopen(URL_CSV_JOGO, timeout=10)
            csv_jogo = list(csv.reader(codecs.iterdecode(req_jogo, 'utf-8')))
            if len(csv_jogo) > 1:
                linha2 = csv_jogo[1]
                if len(linha2) >= 1: dados_jogo[0]["imagem"] = linha2[0].strip()
                if len(linha2) >= 2: dados_jogo[0]["link"] = linha2[1].strip()
                if len(linha2) >= 4:
                    data_inicio = parse_data_jogo_bg(linha2[2].strip())
                    data_fim = parse_data_jogo_bg(linha2[3].strip())
            if len(csv_jogo) > 2:
                linha3 = csv_jogo[2]
                if len(linha3) >= 1: dados_jogo[1]["imagem"] = linha3[0].strip()
                if len(linha3) >= 2: dados_jogo[1]["link"] = linha3[1].strip()
        except Exception:
            pass

        try:
            if dados_jogo[0]["imagem"]:
                req = urllib.request.Request(dados_jogo[0]["imagem"], headers={'User-Agent': 'Mozilla/5.0'})
                img_bytes1 = urllib.request.urlopen(req, timeout=10).read()
        except Exception:
            pass
        
        try:
            if dados_jogo[1]["imagem"]:
                req = urllib.request.Request(dados_jogo[1]["imagem"], headers={'User-Agent': 'Mozilla/5.0'})
                img_bytes2 = urllib.request.urlopen(req, timeout=10).read()
        except Exception:
            pass

        self.resultado.emit(dados_planilha, dados_jogo, data_inicio, data_fim, img_bytes1, img_bytes2)


class WorkerMonitorProcessos(QThread):
    processos_atualizados = pyqtSignal(set)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._executando = True

    def parar(self):
        self._executando = False

    def run(self):
        CREATE_NO_WINDOW = 0x08000000
        while self._executando:
            inicio = time.monotonic()
            try:
                out = subprocess.check_output(
                    ['tasklist', '/FO', 'CSV', '/NH'],
                    creationflags=CREATE_NO_WINDOW,
                    text=True
                )
                nomes = set(
                    line.split(',')[0].strip('"').lower()
                    for line in out.splitlines() if line
                )
                self.processos_atualizados.emit(nomes)
            except Exception:
                pass

            time.sleep(max(0.05, 0.50 - (time.monotonic() - inicio)))
