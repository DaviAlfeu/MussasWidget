import faulthandler
import os
import sys
import threading
import time
import traceback

from PyQt6.QtCore import QtMsgType, qInstallMessageHandler

from config import APPDATA_DIR

ARQUIVO_LOG = os.path.join(APPDATA_DIR, "crash.log")
LIMITE_BYTES = 512 * 1024

_arquivo_nativo = None


def _escrever(texto):
    try:
        with open(ARQUIVO_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {texto}\n")
    except OSError:
        pass


def _excecao_nao_tratada(tipo, valor, tb):
    if issubclass(tipo, KeyboardInterrupt):
        return
    _escrever("Exceção não tratada:\n" + "".join(traceback.format_exception(tipo, valor, tb)))


def _excecao_em_thread(args):
    if args.exc_type is SystemExit:
        return
    nome = args.thread.name if args.thread else "?"
    _escrever(
        f"Exceção na thread {nome}:\n"
        + "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
    )


def _mensagem_qt(tipo, contexto, mensagem):
    if tipo in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
        nivel = {QtMsgType.QtWarningMsg: "aviso", QtMsgType.QtCriticalMsg: "crítico"}.get(tipo, "FATAL")
        _escrever(f"Qt {nivel}: {mensagem}")


def instalar():
    """Registra erros em crash.log e evita que exceções em slots do PyQt6 derrubem o app."""
    global _arquivo_nativo
    try:
        if os.path.exists(ARQUIVO_LOG) and os.path.getsize(ARQUIVO_LOG) > LIMITE_BYTES:
            os.replace(ARQUIVO_LOG, ARQUIVO_LOG + ".old")
    except OSError:
        pass

    sys.excepthook = _excecao_nao_tratada
    threading.excepthook = _excecao_em_thread
    qInstallMessageHandler(_mensagem_qt)

    try:
        _arquivo_nativo = open(ARQUIVO_LOG, "a", encoding="utf-8")
        _arquivo_nativo.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Início da sessão (pid={os.getpid()})\n")
        _arquivo_nativo.flush()
        faulthandler.enable(file=_arquivo_nativo, all_threads=True)
    except OSError:
        pass
