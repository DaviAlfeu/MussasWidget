import ctypes
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from config import APPDATA_DIR

APPLY_UPDATE_FLAG = "--apply-update"
UPDATE_TARGET_FLAG = "--update-target"
UPDATE_PID_FLAG = "--update-pid"

TAMANHO_MINIMO_EXE = 1_000_000
SYNCHRONIZE = 0x00100000
CREATE_NO_WINDOW = 0x08000000


def pasta_updates():
    caminho = Path(APPDATA_DIR) / "updates"
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho


def registrar_log(mensagem):
    try:
        with open(pasta_updates() / "update.log", "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {mensagem}\n")
    except OSError:
        pass


def executavel_atual():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return Path(sys.argv[0]).resolve()


def limpar_updates_antigos(manter=None):
    for arquivo in pasta_updates().glob("*.exe"):
        if manter and arquivo.resolve() == Path(manter).resolve():
            continue
        try:
            arquivo.unlink()
        except OSError:
            pass


def baixar_arquivo(url, destino, ao_progresso=None):
    req = urllib.request.Request(url, headers={"User-Agent": "MussasWidget-Updater"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(destino, "wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        baixado = 0
        while True:
            bloco = resp.read(256 * 1024)
            if not bloco:
                break
            f.write(bloco)
            baixado += len(bloco)
            if ao_progresso and total:
                ao_progresso(min(100, int(baixado * 100 / total)))
    if total and baixado != total:
        raise IOError(f"Download incompleto ({baixado} de {total} bytes).")


def validar_exe(caminho):
    caminho = Path(caminho)
    if not caminho.is_file() or caminho.stat().st_size < TAMANHO_MINIMO_EXE:
        raise ValueError("O arquivo baixado parece estar incompleto ou corrompido.")
    with open(caminho, "rb") as f:
        if f.read(2) != b"MZ":
            raise ValueError("O arquivo baixado não é um executável válido (verifique o link de download).")


def baixar_atualizacao(url, versao, ao_progresso=None):
    """Baixa o novo .exe para a pasta de updates e valida o conteúdo."""
    pasta = pasta_updates()
    limpar_updates_antigos()
    parcial = pasta / f"MussasWidget_{versao}.download"
    novo_exe = pasta / f"MussasWidget_{versao}.exe"
    registrar_log(f"download inicio url={url}")
    baixar_arquivo(url, parcial, ao_progresso)
    parcial.replace(novo_exe)
    validar_exe(novo_exe)
    registrar_log(f"download ok {novo_exe} ({novo_exe.stat().st_size} bytes)")
    return novo_exe


def iniciar_aplicacao_da_atualizacao(novo_exe):
    """Abre o exe novo em modo de aplicação; o chamador deve encerrar o app em seguida."""
    if not getattr(sys, "frozen", False):
        raise RuntimeError("A instalação automática exige o aplicativo compilado.")
    alvo = executavel_atual()
    registrar_log(f"iniciando apply-update novo={novo_exe} alvo={alvo} pid={os.getpid()}")
    ambiente = dict(os.environ)
    ambiente["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    ambiente.pop("_MEIPASS2", None)
    subprocess.Popen(
        [str(novo_exe), APPLY_UPDATE_FLAG, UPDATE_TARGET_FLAG, str(alvo), UPDATE_PID_FLAG, str(os.getpid())],
        cwd=str(Path(novo_exe).parent),
        env=ambiente,
        close_fds=True,
        creationflags=CREATE_NO_WINDOW,
    )


def _esperar_processo(pid, timeout_ms=120_000):
    if pid <= 0:
        return
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        return
    try:
        kernel32.WaitForSingleObject(handle, timeout_ms)
    finally:
        kernel32.CloseHandle(handle)


def executar_aplicacao(alvo, pid_espera):
    """Roda dentro do exe novo: espera o app antigo fechar, substitui o exe e reabre."""
    origem = executavel_atual()
    alvo = Path(alvo).resolve()
    registrar_log(f"apply-update origem={origem} alvo={alvo} espera_pid={pid_espera}")
    _esperar_processo(pid_espera)
    time.sleep(1.0)

    copiado = False
    for tentativa in range(1, 31):
        try:
            shutil.copy2(origem, alvo)
            copiado = True
            registrar_log(f"copia ok tentativa={tentativa}")
            break
        except OSError as exc:
            registrar_log(f"copia falhou tentativa={tentativa} erro={exc}")
            time.sleep(1.0)

    if not copiado:
        registrar_log("copia falhou definitivamente")
        return 1

    try:
        ambiente = dict(os.environ)
        ambiente["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        ambiente.pop("_MEIPASS2", None)
        subprocess.Popen([str(alvo)], cwd=str(alvo.parent), env=ambiente, close_fds=True)
        registrar_log("reinicio ok")
    except OSError as exc:
        registrar_log(f"reinicio falhou: {exc}")
        return 1
    return 0


def tratar_argumentos_de_atualizacao(argv):
    """Retorna o código de saída se o processo for um aplicador de update; senão None."""
    if APPLY_UPDATE_FLAG not in argv:
        return None

    def valor(flag):
        return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else ""

    alvo = valor(UPDATE_TARGET_FLAG)
    try:
        pid = int(valor(UPDATE_PID_FLAG) or 0)
    except ValueError:
        pid = 0
    if not alvo:
        return 1
    return executar_aplicacao(alvo, pid)
