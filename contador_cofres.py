"""
Contador automático de cofres para Fortnite (por reconocimiento de pantalla)
---------------------------------------------------------------------------
El script solo MIRA la pantalla (como una captura). No lee la memoria del juego
ni se mete en él.

Cómo detecta un cofre:
  1. Busca en pantalla el aviso del cofre ("Cofre - Buscar [E]") usando una
     imagen de referencia que tú recortas una vez (calibración).
  2. Si el aviso estaba visible, tú presionaste la tecla de interactuar (E)
     y el aviso desaparece -> el cofre se abrió -> +1.

Teclas:
  F5  -> activar / pausar la detección automática
  F6  -> calibrar (mira un cofre cerrado con el aviso visible y presiona F6)
  F7  -> -1 cofre (corrección)
  F8  -> +1 cofre (manual)
  F9  -> reiniciar contador de la partida
  F10 -> cerrar  (clic derecho sobre la ventana también cierra)

Requisitos:
  pip install mss opencv-python numpy pillow pynput

Usa Fortnite en "Pantalla completa en ventana".
"""

import ctypes
import json
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path

import cv2
import mss
import numpy as np
from PIL import Image, ImageTk
from pynput import keyboard

# Para que las coordenadas coincidan con píxeles reales si Windows tiene escalado (125 %, 150 %...)
if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# ======================= Configuración =======================
TECLA_INTERACTUAR = "e"      # tu tecla para abrir cofres en Fortnite
UMBRAL = 0.80                # parecido mínimo (0-1) para considerar que el aviso está en pantalla
HISTERESIS = 0.12            # el aviso "desaparece" cuando baja de UMBRAL - HISTERESIS
AREA_BUSQUEDA = 0.9          # fracción central de la pantalla donde se busca el aviso (1.0 = toda)
ESCALA = 1.0                 # bájalo a 0.5 si el PC va lento (detecta un poco peor)
FPS = 15                     # capturas por segundo
TIEMPO_ARMADO = 3.0          # segundos tras presionar E (con el aviso visible) en que se espera que el aviso desaparezca
ENFRIAMIENTO = 1.2           # segundos mínimos entre dos conteos automáticos
REQUERIR_TECLA = True        # False = cuenta cada vez que el aviso desaparece, sin mirar la E
                             #         (útil con mando/joystick, pero puede contar si te alejas del cofre)
MIN_VISIBLE = 0.3            # (solo con REQUERIR_TECLA = False) segundos mínimos que el aviso debe estar visible
MONITOR = 1                  # 1 = monitor principal

# Si corre como .exe (PyInstaller), los datos van junto al .exe y no en la carpeta temporal
if getattr(sys, "frozen", False):
    CARPETA = Path(sys.executable).resolve().parent
else:
    CARPETA = Path(__file__).resolve().parent
ARCHIVO_DATOS = CARPETA / "cofres_data.json"
ARCHIVO_OBS = CARPETA / "cofres.txt"
ARCHIVO_PLANTILLA = CARPETA / "plantilla_cofre.png"

OPACIDAD = 0.85
COLOR_FONDO = "#1b1b2f"
COLOR_TEXTO = "#ffd54f"
# =============================================================


# ---------------------- Persistencia ----------------------
def cargar_total() -> int:
    try:
        return int(json.loads(ARCHIVO_DATOS.read_text(encoding="utf-8")).get("total", 0))
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        return 0


def _escribir(archivo: Path, texto: str) -> None:
    # Otro programa (OBS, antivirus, indexador) puede tener el archivo bloqueado un instante
    for intento in range(5):
        try:
            archivo.write_text(texto, encoding="utf-8")
            return
        except OSError:
            time.sleep(0.05 * (intento + 1))


def guardar(partida: int, total: int) -> None:
    _escribir(ARCHIVO_DATOS, json.dumps({"total": total}))
    _escribir(ARCHIVO_OBS, f"Cofres: {partida}")


def nueva_captura():
    """mss >= 10 renombró mss.mss a mss.MSS."""
    return getattr(mss, "MSS", mss.mss)()


def cargar_calibracion():
    if not ARCHIVO_PLANTILLA.exists():
        return None
    try:
        plantilla = cv2.imread(str(ARCHIVO_PLANTILLA), cv2.IMREAD_GRAYSCALE)
        return plantilla
    except Exception:
        return None


def zona_busqueda(monitor: dict) -> dict:
    """Rectángulo central del monitor donde se busca el aviso."""
    ancho = int(monitor["width"] * AREA_BUSQUEDA)
    alto = int(monitor["height"] * AREA_BUSQUEDA)
    return {
        "left": monitor["left"] + (monitor["width"] - ancho) // 2,
        "top": monitor["top"] + (monitor["height"] - alto) // 2,
        "width": ancho, "height": alto,
    }


def reducir(img: np.ndarray) -> np.ndarray:
    if ESCALA == 1.0:
        return img
    return cv2.resize(img, None, fx=ESCALA, fy=ESCALA, interpolation=cv2.INTER_AREA)


# ---------------------- Detección ----------------------
UMBRAL_BLANCO = 200          # brillo mínimo (0-255) para considerar un píxel como "letra blanca"


def preprocesar(img_bgra: np.ndarray) -> np.ndarray:
    """Deja solo las letras blancas del aviso (E / ABRIR) y borra el fondo semitransparente."""
    gris = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2GRAY)
    _, binaria = cv2.threshold(gris, UMBRAL_BLANCO, 255, cv2.THRESH_BINARY)
    return binaria


def parecido(zona: np.ndarray, plantilla: np.ndarray) -> float:
    res = cv2.matchTemplate(zona, plantilla, cv2.TM_CCOEFF_NORMED)
    res = np.nan_to_num(res, nan=0.0, posinf=0.0, neginf=0.0)
    return float(res.max())

class Detector(threading.Thread):
    """Captura la zona del aviso y decide cuándo se abrió un cofre."""

    def __init__(self, app: "App") -> None:
        super().__init__(daemon=True)
        self.app = app
        self.lock = threading.Lock()
        self.plantilla = None
        self.plantilla_red = None
        self.activo = threading.Event()
        self.activo.set()
        self.detener = threading.Event()
        self.puntaje = 0.0
        self.visible = False
        self.armado = False

    def set_calibracion(self, plantilla) -> None:
        with self.lock:
            self.plantilla = plantilla
            self.plantilla_red = reducir(plantilla)
            self.visible = False

    def run(self) -> None:
        ultimo_conteo = 0.0
        armado_hasta = 0.0
        press_visto = 0.0
        visible_desde = 0.0
        periodo = 1.0 / FPS
        with nueva_captura() as sct:
            zona = zona_busqueda(sct.monitors[MONITOR])
            while not self.detener.is_set():
                t0 = time.time()
                with self.lock:
                    plantilla = self.plantilla_red

                if plantilla is None or not self.activo.is_set():
                    time.sleep(0.2)
                    continue

                img = reducir(preprocesar(np.asarray(sct.grab(zona))))
                if img.shape[0] < plantilla.shape[0] or img.shape[1] < plantilla.shape[1]:
                    time.sleep(0.5)
                    continue

                self.puntaje = parecido(img, plantilla)

                # Histéresis: aparecer con UMBRAL, desaparecer bajo UMBRAL - HISTERESIS
                if self.visible:
                    ahora_visible = self.puntaje >= UMBRAL - HISTERESIS
                else:
                    ahora_visible = self.puntaje >= UMBRAL

                ahora = time.time()
                if ahora_visible and not self.visible:
                    visible_desde = ahora

                # Presionaste E mientras el aviso estaba visible -> queda "armado" unos segundos
                ultimo_press = self.app.e_ultimo_press
                if ahora_visible and (ultimo_press > press_visto or self.app.e_presionada):
                    press_visto = ultimo_press
                    armado_hasta = ahora + TIEMPO_ARMADO

                if self.visible and not ahora_visible:
                    # El aviso se fue: ¿fue porque abriste el cofre?
                    if REQUERIR_TECLA:
                        abrio = ahora <= armado_hasta
                    else:
                        abrio = ahora - visible_desde >= MIN_VISIBLE
                    if abrio and ahora - ultimo_conteo > ENFRIAMIENTO:
                        ultimo_conteo = ahora
                        self.app.eventos.put("auto")
                    armado_hasta = 0.0
                self.visible = ahora_visible
                self.armado = ahora <= armado_hasta

                time.sleep(max(0.0, periodo - (time.time() - t0)))


# ---------------------- Calibración ----------------------
class Calibrador:
    """Muestra una captura a pantalla completa para recortar el aviso del cofre."""

    def __init__(self, app: "App", captura: np.ndarray, monitor: dict) -> None:
        self.app = app
        self.captura = captura          # BGRA
        self.monitor = monitor
        self.inicio = None
        self.rect = None

        self.win = tk.Toplevel(app.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.geometry(f"{monitor['width']}x{monitor['height']}+{monitor['left']}+{monitor['top']}")

        rgb = cv2.cvtColor(captura, cv2.COLOR_BGRA2RGB)
        self.foto = ImageTk.PhotoImage(Image.fromarray(rgb))
        self.canvas = tk.Canvas(self.win, highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_image(0, 0, image=self.foto, anchor="nw")
        self.canvas.create_rectangle(10, 10, 700, 52, fill="#000000", outline="")
        self.canvas.create_text(
            20, 31, anchor="w", fill="white", font=("Segoe UI", 13, "bold"),
            text="Arrastra un rectángulo ajustado sobre  E  ABRIR  (sin incluir el cofre).  Esc = cancelar",
        )

        self.canvas.bind("<ButtonPress-1>", self._presionar)
        self.canvas.bind("<B1-Motion>", self._mover)
        self.canvas.bind("<ButtonRelease-1>", self._soltar)
        self.win.bind("<Escape>", lambda e: self._cerrar(False))
        self.win.focus_force()
        self.win.grab_set()

    def _presionar(self, e) -> None:
        self.inicio = (e.x, e.y)
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="#00e676", width=2)

    def _mover(self, e) -> None:
        if self.inicio:
            self.canvas.coords(self.rect, *self.inicio, e.x, e.y)

    def _soltar(self, e) -> None:
        if not self.inicio:
            return
        x1, y1 = self.inicio
        x0, x1 = sorted((x1, e.x))
        y0, y1 = sorted((y1, e.y))
        if x1 - x0 < 15 or y1 - y0 < 8:
            return  # recorte demasiado pequeño, intenta de nuevo

        plantilla = preprocesar(self.captura)[y0:y1, x0:x1].copy()
        if cv2.countNonZero(plantilla) < 20:
            return  # el recorte no tiene letras blancas; vuelve a intentarlo sobre "E  ABRIR"


        cv2.imwrite(str(ARCHIVO_PLANTILLA), plantilla)
        self.app.detector.set_calibracion(plantilla)
        self._cerrar(True)

    def _cerrar(self, ok: bool) -> None:
        self.win.grab_release()
        self.win.destroy()
        self.app.fin_calibracion(ok)


# ---------------------- Interfaz principal ----------------------
class App:
    def __init__(self) -> None:
        self.partida = 0
        self.total = cargar_total()
        self.eventos: "queue.Queue[str]" = queue.Queue()
        self.e_presionada = False
        self.e_ultimo_press = 0.0
        self.calibrando = False

        self.root = tk.Tk()
        self.root.title("Cofres")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", OPACIDAD)
        self.root.configure(bg=COLOR_FONDO)
        self.root.geometry("+30+30")

        self.lbl_partida = tk.Label(self.root, font=("Segoe UI", 22, "bold"),
                                    fg=COLOR_TEXTO, bg=COLOR_FONDO, padx=14)
        self.lbl_partida.pack(pady=(4, 0))
        self.lbl_total = tk.Label(self.root, font=("Segoe UI", 10),
                                  fg="#cfcfe6", bg=COLOR_FONDO, padx=14)
        self.lbl_total.pack()
        self.lbl_estado = tk.Label(self.root, font=("Consolas", 9),
                                   fg="#8a8aa8", bg=COLOR_FONDO, padx=14)
        self.lbl_estado.pack(pady=(0, 6))

        for w in (self.root, self.lbl_partida, self.lbl_total, self.lbl_estado):
            w.bind("<Button-1>", self._iniciar_arrastre)
            w.bind("<B1-Motion>", self._arrastrar)
            w.bind("<Button-3>", lambda e: self.salir())

        self.detector = Detector(self)
        plantilla = cargar_calibracion()
        if plantilla is not None:
            self.detector.set_calibracion(plantilla)
        self.detector.start()

        self.listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self.listener.daemon = True
        self.listener.start()

        self.actualizar()
        self.root.after(30, self._bucle)

    # ---- teclado (hilo de pynput: solo encola / marca tiempos) ----
    @staticmethod
    def _es_interactuar(key) -> bool:
        ch = getattr(key, "char", None)
        return ch is not None and ch.lower() == TECLA_INTERACTUAR

    def _on_press(self, key) -> None:
        if self._es_interactuar(key):
            if not self.e_presionada:          # ignora la auto-repetición al mantenerla
                self.e_ultimo_press = time.time()
            self.e_presionada = True
            return
        acciones = {
            keyboard.Key.f5: "toggle", keyboard.Key.f6: "calibrar",
            keyboard.Key.f7: "restar", keyboard.Key.f8: "sumar",
            keyboard.Key.f9: "reset", keyboard.Key.f10: "salir",
        }
        if key in acciones:
            self.eventos.put(acciones[key])

    def _on_release(self, key) -> None:
        if self._es_interactuar(key):
            self.e_presionada = False

    # ---- hilo de la interfaz ----
    def _bucle(self) -> None:
        cambio = False
        while not self.eventos.empty():
            ev = self.eventos.get_nowait()
            if ev in ("sumar", "auto"):
                self.partida += 1
                self.total += 1
                cambio = True
            elif ev == "restar" and self.partida > 0:
                self.partida -= 1
                self.total = max(0, self.total - 1)
                cambio = True
            elif ev == "reset":
                self.partida = 0
                cambio = True
            elif ev == "toggle":
                if self.detector.activo.is_set():
                    self.detector.activo.clear()
                else:
                    self.detector.activo.set()
            elif ev == "calibrar" and not self.calibrando:
                self.iniciar_calibracion()
            elif ev == "salir":
                self.salir()
                return
        if cambio:
            self.actualizar()
        self._actualizar_estado()
        self.root.after(30, self._bucle)

    def iniciar_calibracion(self) -> None:
        self.calibrando = True
        self.detector.activo.clear()
        self.root.withdraw()  # que el contador no salga en la captura
        self.root.after(150, self._capturar_para_calibrar)

    def _capturar_para_calibrar(self) -> None:
        with nueva_captura() as sct:
            mon = sct.monitors[MONITOR]
            captura = np.asarray(sct.grab(mon))
        self.root.deiconify()
        Calibrador(self, captura, dict(mon))

    def fin_calibracion(self, ok: bool) -> None:
        self.calibrando = False
        self.detector.activo.set()

    def actualizar(self) -> None:
        self.lbl_partida.config(text=f"🧰 {self.partida}")
        self.lbl_total.config(text=f"Total histórico: {self.total}")
        guardar(self.partida, self.total)

    def _actualizar_estado(self) -> None:
        d = self.detector
        if d.plantilla is None:
            txt = "Sin calibrar: F6"
        elif not d.activo.is_set():
            txt = "Auto: PAUSA (F5)"
        else:
            aviso = "AVISO" if d.visible else "-----"
            tecla = "E" if (time.time() - self.e_ultimo_press < 0.5 or self.e_presionada) else "_"
            armado = "LISTO" if d.armado else "     "
            txt = f"{d.puntaje:.2f} {aviso} [{tecla}] {armado}"
        self.lbl_estado.config(text=txt)

    def _iniciar_arrastre(self, e) -> None:
        self._dx = e.x_root - self.root.winfo_x()
        self._dy = e.y_root - self.root.winfo_y()

    def _arrastrar(self, e) -> None:
        self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def salir(self) -> None:
        guardar(self.partida, self.total)
        self.detector.detener.set()
        self.listener.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


PUERTO_CONTADOR = 47814      # evita que se abran dos contadores a la vez


def main() -> None:
    import socket
    candado = socket.socket()
    try:
        candado.bind(("127.0.0.1", PUERTO_CONTADOR))
    except OSError:
        return  # ya hay un contador abierto
    try:
        App().run()
    except Exception:
        import traceback
        from datetime import datetime
        with (CARPETA / "contador_error.log").open("a", encoding="utf-8") as f:
            f.write(f"\n--- {datetime.now():%Y-%m-%d %H:%M:%S} ---\n{traceback.format_exc()}")
        raise


if __name__ == "__main__":
    main()