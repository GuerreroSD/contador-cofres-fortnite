import sys


def main() -> None:
    args = sys.argv[1:]
    if any(a in args for a in ("--vigilar", "--instalar", "--desinstalar", "--probar")):
        import vigilar_fortnite
        vigilar_fortnite.main(args)
        return

    if getattr(sys, "frozen", False) and "--contador" not in args:
        import vigilar_fortnite
        try:
            if vigilar_fortnite.asegurar_vigilante():
                vigilar_fortnite.informar(
                    "¡Listo! Desde ahora el contador se abrirá solo cada vez que abras "
                    "Fortnite (también después de reiniciar el PC).\n\n"
                    "No necesitas volver a abrir este programa.\n"
                    "Para desactivarlo usa 'Quitar de inicio.bat'.")
        except Exception:
            import traceback
            vigilar_fortnite.anotar("ERROR al instalar:\n" + traceback.format_exc())

    import contador_cofres
    contador_cofres.main()


if __name__ == "__main__":
    main()
