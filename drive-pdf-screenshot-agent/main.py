"""Busca PDFs en una carpeta de Google Drive, detecta páginas que contienen
ciertas palabras clave, y guarda esas páginas como imágenes PNG en una
carpeta local lista para subir a un CRM.

Uso:
    python main.py [--config config.yaml]

Ver README.md para instrucciones de configuración.
"""

import argparse
import os
import sys
import time

import fitz  # PyMuPDF
import requests
import yaml
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def load_config(path):
    if not os.path.exists(path):
        sys.exit(
            f"No se encontró '{path}'. Copiá config.example.yaml a config.yaml "
            "y completá tus valores."
        )
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_drive_service(credentials_file, token_file):
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_file):
                sys.exit(
                    f"No se encontró '{credentials_file}'. Descargalo desde Google "
                    "Cloud Console (credenciales OAuth de tipo 'Desktop app'). "
                    "Ver README.md."
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return creds, build("drive", "v3", credentials=creds)


def list_pdfs(service, folder_id):
    query = f"'{folder_id}' in parents and mimeType='application/pdf' and trashed=false"
    files = []
    page_token = None
    while True:
        response = (
            service.files()
            .list(
                q=query,
                spaces="drive",
                fields="nextPageToken, files(id, name, size)",
                pageToken=page_token,
            )
            .execute()
        )
        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return files


def download_pdf(creds, file_id, destination, retries=6):
    """Descarga el archivo usando `requests`, con soporte de reanudación por
    HTTP Range: si se corta a mitad de camino, el reintento sigue desde el
    último byte recibido en vez de empezar de cero."""
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    downloaded = 0
    total_size = None

    for attempt in range(1, retries + 1):
        headers = {"Authorization": f"Bearer {creds.token}"}
        mode = "wb"
        if downloaded:
            headers["Range"] = f"bytes={downloaded}-"
            mode = "ab"
        try:
            with requests.get(url, headers=headers, stream=True, timeout=(15, 60)) as resp:
                resp.raise_for_status()
                if total_size is None:
                    content_range = resp.headers.get("Content-Range")
                    if content_range and "/" in content_range:
                        total_size = int(content_range.rsplit("/", 1)[-1])
                    else:
                        total_size = int(resp.headers.get("Content-Length", 0)) or None
                with open(destination, mode) as fh:
                    for chunk in resp.iter_content(chunk_size=256 * 1024):
                        if chunk:
                            fh.write(chunk)
                            downloaded += len(chunk)
            return
        except (requests.exceptions.RequestException, OSError) as e:
            if attempt >= retries:
                raise
            total_label = f"{total_size / (1024 * 1024):.1f}" if total_size else "?"
            wait_seconds = 5 * attempt
            print(
                f"  (falló la descarga en {downloaded / (1024 * 1024):.1f}/{total_label} MB, "
                f"intento {attempt}/{retries}: {e}, reintentando en {wait_seconds}s...)"
            )
            time.sleep(wait_seconds)


def sanitize_filename(name):
    return "".join(c if c.isalnum() or c in " ._-" else "_" for c in name)


def extract_matching_pages(pdf_path, keywords, output_dir, zoom):
    keywords_lower = [k.lower() for k in keywords]
    stem = sanitize_filename(os.path.splitext(os.path.basename(pdf_path))[0])
    saved = []

    doc = fitz.open(pdf_path)
    try:
        for page_index in range(len(doc)):
            page = doc[page_index]
            text = page.get_text().lower()
            if not any(keyword in text for keyword in keywords_lower):
                continue

            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            out_path = os.path.join(output_dir, f"{stem}_pagina{page_index + 1}.png")
            pix.save(out_path)
            saved.append(out_path)
    finally:
        doc.close()

    return saved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml", help="Ruta al archivo de configuración")
    args = parser.parse_args()

    run_with_config(load_config(args.config))


def main_with_config(config_path):
    """Punto de entrada para invocar el agente desde otro código (ej. app.py)."""
    run_with_config(load_config(config_path))


def run_with_config(config):
    folder_id = config["drive_folder_id"]
    keywords = config["keywords"]
    output_dir = config["output_dir"]
    downloads_dir = config["downloads_dir"]
    zoom = float(config.get("zoom", 2.0))
    credentials_file = config.get("credentials_file", "credentials.json")
    token_file = config.get("token_file", "token.json")

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(downloads_dir, exist_ok=True)

    creds, service = get_drive_service(credentials_file, token_file)
    pdfs = list_pdfs(service, folder_id)

    if not pdfs:
        print("No se encontraron PDFs en la carpeta indicada.")
        return

    print(f"Encontrados {len(pdfs)} PDF(s) en la carpeta.")

    total_saved = 0
    failed = []
    for pdf in pdfs:
        local_path = os.path.join(downloads_dir, sanitize_filename(pdf["name"]))
        size_mb = int(pdf["size"]) / (1024 * 1024) if pdf.get("size") else None
        size_label = f" ({size_mb:.1f} MB)" if size_mb is not None else ""
        print(f"Descargando: {pdf['name']}{size_label}")
        try:
            download_pdf(creds, pdf["id"], local_path)
            saved = extract_matching_pages(local_path, keywords, output_dir, zoom)
        except Exception as e:  # noqa: BLE001
            print(f"  -> ERROR, se salteó este PDF: {e}")
            failed.append(pdf["name"])
            continue

        if saved:
            print(f"  -> {len(saved)} página(s) guardada(s):")
            for path in saved:
                print(f"     {path}")
        else:
            print("  -> ninguna página coincidió con las palabras clave.")
        total_saved += len(saved)

    print(f"\nListo. {total_saved} imagen(es) guardada(s) en '{output_dir}'.")
    if failed:
        print(f"\n{len(failed)} PDF(s) fallaron y se saltearon:")
        for name in failed:
            print(f"  - {name}")
        print("Volvé a correr el agente para reintentarlos.")


if __name__ == "__main__":
    main()
