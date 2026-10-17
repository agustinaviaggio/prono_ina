
import csv
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

# --------------------------------------------------
# Configuración
# --------------------------------------------------
BASE_URL = "https://alerta.ina.gob.ar/a5"
CAL_ID = 432
ESTACION_ID = 52

CARPETA = Path(__file__).resolve().parent
ARCHIVO_CSV = CARPETA / "pronosticos_san_fernando.csv"
ARCHIVO_PROCESADOS = CARPETA / "corridas_procesadas.txt"

CALIFICADORES = {"main", "p05", "p25", "p75", "p95"}
ZONA_LOCAL = ZoneInfo("America/Argentina/Buenos_Aires")

COLUMNAS = [
    "cor_id",
    "fecha_emision_utc",
    "series_id",
    "fecha_pronosticada_utc",
    "fecha_pronosticada_local",
    "qualifier",
    "valor_m",
]


def fecha_local(fecha_utc):
    if not fecha_utc:
        return ""
    fecha = datetime.fromisoformat(fecha_utc.replace("Z", "+00:00"))
    return fecha.astimezone(ZONA_LOCAL).isoformat()


def descargar_ultima_corrida():
    url = f"{BASE_URL}/sim/calibrados/{CAL_ID}/corridas/last"

    respuesta = requests.get(
        url,
        params={
            "estacion_id": ESTACION_ID,
            "includeProno": "true",
        },
        timeout=90,
    )
    respuesta.raise_for_status()
    corrida = respuesta.json()

    # Aceptar respuestas representadas como objeto o lista.
    if isinstance(corrida, list):
        if not corrida:
            raise ValueError("La API devolvió una lista vacía.")
        corrida = corrida[0]

    cor_id = corrida.get("id", corrida.get("cor_id"))
    if cor_id is None:
        raise ValueError(
            f"No se encontró el identificador de la corrida: {corrida}"
        )

    fecha_emision = corrida.get("forecast_date", "")
    filas = []

    for serie in corrida.get("series", []):
        series_id = serie.get("series_id")

        for pronostico in serie.get("pronosticos", []):
            qualifier = pronostico.get("qualifier", "main")

            if qualifier not in CALIFICADORES:
                continue

            fecha = pronostico.get("timestart")
            valor = pronostico.get("valor")

            if fecha is None or valor is None:
                continue

            filas.append({
                "cor_id": cor_id,
                "fecha_emision_utc": fecha_emision,
                "series_id": series_id,
                "fecha_pronosticada_utc": fecha,
                "fecha_pronosticada_local": fecha_local(fecha),
                "qualifier": qualifier,
                "valor_m": valor,
            })

    if not filas:
        raise ValueError(
            f"La corrida {cor_id} no devolvió pronósticos. "
            "No se marcará como procesada."
        )

    return str(cor_id), filas


def main():
    ARCHIVO_PROCESADOS.touch(exist_ok=True)

    procesados = set(
        ARCHIVO_PROCESADOS.read_text(encoding="utf-8").splitlines()
    )

    cor_id, filas = descargar_ultima_corrida()

    if cor_id in procesados:
        print(f"Sin emisión nueva. Última corrida consultada: {cor_id}")
        return

    existe_csv = ARCHIVO_CSV.exists() and ARCHIVO_CSV.stat().st_size > 0

    with ARCHIVO_CSV.open(
        "a", newline="", encoding="utf-8-sig"
    ) as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=COLUMNAS)

        if not existe_csv:
            escritor.writeheader()

        escritor.writerows(filas)

    # Registrar la corrida después de guardar sus valores.
    with ARCHIVO_PROCESADOS.open("a", encoding="utf-8") as archivo:
        archivo.write(cor_id + "\n")

    print(f"Nueva emisión descargada: {cor_id}")
    print(f"Registros guardados: {len(filas)}")
    print(f"Archivo: {ARCHIVO_CSV}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}")
        raise
