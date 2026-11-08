# Contador de Cofres para Fortnite

Contador automático de cofres abiertos en Fortnite que funciona **mirando la pantalla**: no lee la memoria del juego, no inyecta nada y no toca archivos de Fortnite. Muestra una pequeña ventana flotante con los cofres de la partida y el total histórico, y se abre sola cada vez que inicias el juego.

## Características

- **Detección automática** del aviso del cofre ("E ABRIR") usando reconocimiento de imagen (OpenCV).
- **Se abre y se cierra solo** junto con Fortnite.
- **Arranca con Windows** sin retraso (tarea programada al iniciar sesión).
- **Contador de partida y total histórico**, que se guarda entre sesiones.
- **Compatible con OBS**: escribe `cofres.txt` con el texto `Cofres: N`, para mostrarlo en stream con una fuente de texto.
- **Ventana flotante** semitransparente, siempre visible y que se puede arrastrar.

## Instalación

### Opción A: Ejecutable (no necesita Python)

1. Descarga **[ContadorCofres-v1.0.0-windows.zip](https://github.com/GuerreroSD/contador-cofres-fortnite/releases/latest)** y descomprímelo donde quieras (o compílalo tú, ver [Compilar](#compilar)).
2. Haz doble clic en `ContadorCofres.exe` **una sola vez**.
3. Aparece el mensaje *"¡Listo!"*. Desde ahí el contador se abre solo cada vez que abras Fortnite, también después de reiniciar el PC.

> Si Windows muestra "Windows protegió tu PC", haz clic en **Más información → Ejecutar de todas formas** (el programa no tiene firma digital).
> Si Windows Defender lo borra (es un falso positivo común de PyInstaller), agrega la carpeta `ContadorCofres` como exclusión en *Seguridad de Windows → Protección antivirus → Exclusiones*.

### Opción B: Desde el código con Python

```bash
pip install mss opencv-python numpy pillow pynput
python app.py
```

## Primer uso: calibrar

1. En Fortnite, acércate a un **cofre cerrado** hasta que aparezca el aviso para abrirlo.
2. Presiona **F6**: se congela la pantalla.
3. Arrastra un rectángulo ajustado sobre **"E ABRIR"** (solo el texto, sin el cofre).

La calibración se guarda en `plantilla_cofre.png` y no hay que repetirla.

> Usa Fortnite en modo **"Pantalla completa en ventana"** para que la ventana del contador se vea encima del juego.

## Controles

| Tecla | Acción |
|---|---|
| **F5** | Pausar / reanudar la detección automática |
| **F6** | Calibrar |
| **F7** | Restar 1 cofre (corrección) |
| **F8** | Sumar 1 cofre (manual) |
| **F9** | Reiniciar el contador de la partida |
| **F10** / clic derecho | Cerrar el contador |
| Arrastrar con el mouse | Mover la ventana |

La línea pequeña de la ventana muestra el estado de la detección: el parecido con el aviso (0 a 1), si el aviso está visible y si se presionó **E**.

## Cómo funciona

1. Captura la zona central de la pantalla unas 15 veces por segundo (`mss`).
2. Deja solo los píxeles blancos (las letras del aviso) y busca la plantilla calibrada con `cv2.matchTemplate`.
3. Si el aviso estaba visible, presionaste **E** y el aviso desaparece en menos de 3 segundos, cuenta **+1 cofre**.

Un **vigilante** en segundo plano revisa cada 5 segundos si `FortniteClient-Win64-Shipping*.exe` está corriendo: abre el contador cuando inicias el juego y lo cierra cuando lo cierras. Si el contador se cae por un error, lo vuelve a abrir (hasta 3 veces). Si lo cierras con F10, respeta tu decisión hasta la próxima partida.

## Archivos

| Archivo | Descripción |
|---|---|
| `app.py` | Punto de entrada del ejecutable (decide qué modo ejecutar) |
| `contador_cofres.py` | Ventana del contador y detección por pantalla |
| `vigilar_fortnite.pyw` | Vigilante: detecta Fortnite e instala el inicio automático |
| `compilar.bat` | Genera la carpeta `ContadorCofres/` con el ejecutable |

Archivos que genera el programa (junto al `.exe`):

| Archivo | Descripción |
|---|---|
| `cofres_data.json` | Total histórico |
| `cofres.txt` | Texto para OBS |
| `plantilla_cofre.png` | Calibración |
| `vigilante.log` / `contador_error.log` | Registros para diagnóstico |

## Opciones de línea de comandos

```text
ContadorCofres.exe                 Abre el contador (la primera vez, además instala el inicio automático)
ContadorCofres.exe --probar        Diagnóstico
ContadorCofres.exe --instalar      Fuerza la instalación del inicio automático
ContadorCofres.exe --desinstalar   Quita el inicio automático
```

Dentro de la carpeta del programa también están `Diagnostico.bat` y `Quitar de inicio.bat`.

## Compilar

Requiere Python 3.11+ en Windows:

```bash
pip install mss opencv-python numpy pillow pynput pyinstaller
compilar.bat
```

El resultado queda en `ContadorCofres/`. Puedes mover esa carpeta a donde quieras; después de moverla, abre el `.exe` una vez para actualizar el inicio automático.

## Configuración

Al principio de `contador_cofres.py` puedes ajustar:

| Variable | Por defecto | Descripción |
|---|---|---|
| `TECLA_INTERACTUAR` | `"e"` | Tecla para abrir cofres |
| `UMBRAL` | `0.80` | Parecido mínimo para considerar visible el aviso |
| `FPS` | `15` | Capturas por segundo |
| `ESCALA` | `1.0` | Bájalo a `0.5` si el PC va lento |
| `REQUERIR_TECLA` | `True` | `False` para jugar con mando (cuenta cuando el aviso desaparece) |
| `MONITOR` | `1` | Monitor donde está el juego |

## Desinstalar

1. Ejecuta `Quitar de inicio.bat` (o `ContadorCofres.exe --desinstalar`).
2. Borra la carpeta `ContadorCofres`.

## Aviso

Proyecto personal sin relación con Epic Games. Solo captura la pantalla y escucha el teclado, igual que un programa de grabación o de stream. Úsalo bajo tu propia responsabilidad.
