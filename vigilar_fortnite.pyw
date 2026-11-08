import csv
import io
import os
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PREFIJO_FORTNITE = "fortniteclient-win64-shipping"
INTERVALO = 5
PUERTO_BLOQUEO = 47813

CONGELADO = getattr(sys, "frozen", False)
if CONGELADO:
    EXE = Path(sys.executable).resolve()
    CARPETA = EXE.parent
else:
    EXE = None
    CARPETA = Path(__file__).resolve().parent
CONTADOR = CARPETA / "contador_cofres.py"
LOG = CARPETA / "vigilante.log"
LOG_CONTADOR = CARPETA / "contador_error.log"
ARCHIVO_INICIO = (
    Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu"
    / "Programs" / "Startup" / "contador_cofres_fortnite.bat"
)
SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
INDEPENDIENTE = (getattr(subprocess, "DETACHED_PROCESS", 0)
                 | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
SALIR_DEL_JOB = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)


def anotar(msg: str) -> None:
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")
    except OSError:
        pass


def informar(texto: str, titulo: str = "Contador de cofres") -> None:
    if CONGELADO or sys.stdout is None:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, texto, titulo, 0x40)
    else:
        print(texto)


def python_consola() -> str:
    exe = Path(sys.executable)
    c = exe.with_name("python.exe")
    return str(c if c.exists() else exe)


def pythonw() -> str:
    exe = Path(sys.executable)
    c = exe.with_name("pythonw.exe")
    return str(c if c.exists() else exe)


def comando_contador() -> list[str]:
    return [str(EXE), "--contador"] if CONGELADO else [pythonw(), str(CONTADOR)]


def comando_vigilante() -> list[str]:
    return [str(EXE), "--vigilar"] if CONGELADO else [pythonw(), str(Path(__file__).resolve())]


def procesos_fortnite() -> list[str]:
    try:
        salida = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, errors="ignore", creationflags=SIN_VENTANA,
        ).stdout
    except OSError as e:
        anotar(f"No se pudo ejecutar tasklist: {e}")
        return []
    nombres = [fila[0] for fila in csv.reader(io.StringIO(salida)) if fila]
    return [n for n in nombres if n.lower().startswith(PREFIJO_FORTNITE)]


def lanzar_contador() -> subprocess.Popen:
    err = LOG_CONTADOR.open("a", encoding="utf-8")
    err.write(f"\n--- {datetime.now():%Y-%m-%d %H:%M:%S} ---\n")
    err.flush()
    return subprocess.Popen(comando_contador(), cwd=CARPETA, stdout=err, stderr=err,
                            stdin=subprocess.DEVNULL)


def cerrar_contador(proc: subprocess.Popen) -> None:
    try:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       capture_output=True, creationflags=SIN_VENTANA)
    except OSError:
        proc.terminate()


def vigilante_corriendo() -> bool:
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", PUERTO_BLOQUEO))
        return False
    except OSError:
        return True
    finally:
        s.close()


def lanzar_vigilante() -> None:
    args = comando_vigilante()
    try:
        subprocess.Popen(args, cwd=CARPETA, creationflags=INDEPENDIENTE | SALIR_DEL_JOB,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, close_fds=True)
    except OSError:
        subprocess.Popen(args, cwd=CARPETA, creationflags=INDEPENDIENTE,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, close_fds=True)


def vigilar() -> None:
    anotar("Arrancando vigilante...")
    try:
        _vigilar()
    except Exception:
        import traceback
        anotar("ERROR:\n" + traceback.format_exc())


def _vigilar() -> None:
    bloqueo = socket.socket()
    try:
        bloqueo.bind(("127.0.0.1", PUERTO_BLOQUEO))
    except OSError:
        anotar("Ya hay otro vigilante corriendo; este se cierra.")
        return

    anotar(f"Vigilante iniciado con {sys.executable}")
    contador = None
    lanzado_en_sesion = False
    reintentos = 0

    while True:
        if procesos_fortnite():
            if not lanzado_en_sesion:
                anotar("Fortnite detectado -> abriendo contador")
                contador = lanzar_contador()
                lanzado_en_sesion = True
                reintentos = 0
            elif contador is not None and contador.poll() not in (None, 0):
                anotar(f"El contador se cerró con error (código {contador.returncode}); "
                       f"revisa {LOG_CONTADOR.name}")
                contador = None
                if reintentos < 3:
                    reintentos += 1
                    anotar(f"Reabriendo contador (intento {reintentos}/3)")
                    contador = lanzar_contador()
        elif lanzado_en_sesion:
            anotar("Fortnite cerrado -> cerrando contador")
            if contador is not None and contador.poll() is None:
                cerrar_contador(contador)
            contador = None
            lanzado_en_sesion = False
        time.sleep(INTERVALO)


def probar() -> None:
    ok = lambda b: "OK " if b else "XX "
    lineas = ["=== Diagnóstico ==="]
    if CONGELADO:
        lineas.append(f"Ejecutable:           {EXE}")
    else:
        lineas.append(f"Python:               {sys.executable}")
        lineas.append(f"pythonw:              {pythonw()}  "
                      f"{ok(Path(pythonw()).name.lower() == 'pythonw.exe')}")
        lineas.append(f"contador_cofres.py:   {ok(CONTADOR.exists())}{CONTADOR}")
    lineas.append(f"Inicio (registro):    {ok(leer_inicio() == contenido_inicio())}"
                  f"{leer_inicio() or 'no instalado'}")
    lineas.append(f"Inicio (tarea):       {ok(tarea_existe())}{NOMBRE_TAREA}")

    if not CONGELADO:
        r = subprocess.run([python_consola(), "-c", "import mss, cv2, numpy, PIL, pynput"],
                           capture_output=True, text=True)
        lineas.append(f"Librerías:            {ok(r.returncode == 0)}"
                      + ("" if r.returncode == 0 else r.stderr.strip().splitlines()[-1]))

    if vigilante_corriendo():
        lineas.append("Vigilante corriendo:  OK sí")
    else:
        lineas.append("Vigilante corriendo:  XX no (usa --instalar o reinicia el PC)")

    encontrados = procesos_fortnite()
    lineas.append(f"Fortnite abierto:     {ok(bool(encontrados))}"
                  f"{', '.join(encontrados) or 'no encontrado'}")

    if LOG.exists():
        lineas.append("\nÚltimas líneas de vigilante.log:")
        lineas.append("".join(LOG.read_text(encoding="utf-8").splitlines(True)[-5:]))
    if LOG_CONTADOR.exists() and LOG_CONTADOR.stat().st_size:
        lineas.append("Últimas líneas de contador_error.log:")
        lineas.append("".join(LOG_CONTADOR.read_text(encoding="utf-8").splitlines(True)[-8:]))
    informar("\n".join(lineas), "Diagnóstico")


CLAVE_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOMBRE_RUN = "ContadorCofresFortnite"


def contenido_inicio() -> str:
    return " ".join(f'"{a}"' if not a.startswith("--") else a for a in comando_vigilante())


def leer_inicio() -> str | None:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLAVE_RUN) as k:
            return winreg.QueryValueEx(k, NOMBRE_RUN)[0]
    except OSError:
        return None


NOMBRE_TAREA = "ContadorCofresFortnite"


def _xml(texto: str) -> str:
    from xml.sax.saxutils import escape
    return escape(texto)


def tarea_existe() -> bool:
    try:
        r = subprocess.run(["schtasks", "/Query", "/TN", NOMBRE_TAREA, "/XML"],
                           capture_output=True, text=True, errors="ignore",
                           creationflags=SIN_VENTANA)
    except OSError:
        return False
    return r.returncode == 0 and _xml(comando_vigilante()[0]) in r.stdout


def crear_tarea() -> bool:
    usuario = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}"
    exe, *args = comando_vigilante()
    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Abre el contador de cofres al iniciar Fortnite</Description></RegistrationInfo>
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled><UserId>{_xml(usuario)}</UserId></LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{_xml(usuario)}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <StartWhenAvailable>true</StartWhenAvailable>
    <Priority>5</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{_xml(exe)}</Command>
      <Arguments>{_xml(" ".join(f'"{a}"' if not a.startswith("--") else a for a in args))}</Arguments>
      <WorkingDirectory>{_xml(str(CARPETA))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""
    import tempfile
    ruta = Path(tempfile.gettempdir()) / "contador_cofres_tarea.xml"
    try:
        ruta.write_text(xml, encoding="utf-16")
        r = subprocess.run(["schtasks", "/Create", "/TN", NOMBRE_TAREA, "/XML", str(ruta), "/F"],
                           capture_output=True, text=True, errors="ignore",
                           creationflags=SIN_VENTANA)
    except OSError as e:
        anotar(f"No se pudo crear la tarea programada: {e}")
        return False
    finally:
        try:
            ruta.unlink()
        except OSError:
            pass
    if r.returncode != 0:
        anotar(f"No se pudo crear la tarea programada: {(r.stderr or r.stdout).strip()}")
        return False
    anotar("Tarea programada creada (inicio de sesión)")
    return True


def borrar_tarea() -> bool:
    try:
        r = subprocess.run(["schtasks", "/Delete", "/TN", NOMBRE_TAREA, "/F"],
                           capture_output=True, creationflags=SIN_VENTANA)
        return r.returncode == 0
    except OSError:
        return False


def esta_instalado() -> bool:
    return leer_inicio() == contenido_inicio() and tarea_existe()


def escribir_inicio() -> None:
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, CLAVE_RUN) as k:
        winreg.SetValueEx(k, NOMBRE_RUN, 0, winreg.REG_SZ, contenido_inicio())
    crear_tarea()
    try:
        ARCHIVO_INICIO.unlink()
    except OSError:
        pass


def borrar_inicio() -> bool:
    import winreg
    borrado = False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLAVE_RUN, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, NOMBRE_RUN)
            borrado = True
    except OSError:
        pass
    try:
        ARCHIVO_INICIO.unlink()
        borrado = True
    except OSError:
        pass
    return borrar_tarea() or borrado


def cerrar_vigilantes_antiguos() -> None:
    if not CONGELADO:
        return
    ps = ("Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
          "Where-Object { $_.CommandLine -match 'vigilar_fortnite' } | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, creationflags=SIN_VENTANA, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        pass
    for _ in range(10):
        if not vigilante_corriendo():
            break
        time.sleep(0.3)


def asegurar_vigilante() -> bool:
    primera_vez = not esta_instalado()
    if primera_vez:
        escribir_inicio()
        cerrar_vigilantes_antiguos()
        anotar(f"Instalado en el inicio de Windows: {ARCHIVO_INICIO}")
    if not vigilante_corriendo():
        lanzar_vigilante()
    return primera_vez


def instalar() -> None:
    escribir_inicio()
    cerrar_vigilantes_antiguos()
    msg = ["Se iniciará con Windows (registro: HKCU\\...\\Run\\" + NOMBRE_RUN + ")."]
    if vigilante_corriendo():
        msg.append("El vigilante ya estaba corriendo. Abre Fortnite y aparecerá el contador.")
        informar("\n".join(msg))
        return
    lanzar_vigilante()
    for _ in range(20):
        time.sleep(0.5)
        if vigilante_corriendo():
            msg.append("Listo: el vigilante está corriendo. Abre Fortnite y aparecerá el contador.")
            informar("\n".join(msg))
            return
    msg.append("XX El vigilante no quedó corriendo. Ejecuta el diagnóstico (--probar).")
    if LOG.exists():
        msg.append("\nÚltimas líneas de vigilante.log:")
        msg.append("".join(LOG.read_text(encoding="utf-8").splitlines(True)[-8:]))
    informar("\n".join(msg))


def desinstalar() -> None:
    msg = "Ya no se iniciará con Windows." if borrar_inicio() else "No estaba instalado."
    proceso = "ContadorCofres.exe" if CONGELADO else "pythonw.exe"
    informar(f"{msg}\nSi el vigilante está corriendo ahora, se detiene al reiniciar o desde el\n"
             f"Administrador de tareas (proceso '{proceso}').")


def main(argv: list[str]) -> None:
    if "--probar" in argv:
        probar()
    elif "--instalar" in argv:
        instalar()
    elif "--desinstalar" in argv:
        desinstalar()
    else:
        vigilar()


if __name__ == "__main__":
    main(sys.argv)
