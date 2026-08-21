"""Busca PDFs en una carpeta de Google Drive, detecta páginas que contienen
ciertas palabras clave, y guarda esas páginas como imágenes PNG en una
carpeta local lista para subir a un CRM.

Uso:
    python main.py [--config config.yaml]

Ver README.md para instrucciones de configuración.
"""

import argparse
import io
import os
import sys

import fitz  # PyMuPDF
import yaml
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

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

    return build("drive", "v3", credentials=creds)


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
                fields="nextPageToken, files(id, name)",
                pageToken=page_token,
            )
            .execute()
        )
        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return files


def download_pdf(service, file_id, destination):
    request = service.files().get_media(fileId=file_id)
    with io.FileIO(destination, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()


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

    config = load_config(args.config)

    folder_id = config["drive_folder_id"]
    keywords = config["keywords"]
    output_dir = config["output_dir"]
    downloads_dir = config["downloads_dir"]
    zoom = float(config.get("zoom", 2.0))
    credentials_file = config.get("credentials_file", "credentials.json")
    token_file = config.get("token_file", "token.json")

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(downloads_dir, exist_ok=True)

    service = get_drive_service(credentials_file, token_file)
    pdfs = list_pdfs(service, folder_id)

    if not pdfs:
        print("No se encontraron PDFs en la carpeta indicada.")
        return

    print(f"Encontrados {len(pdfs)} PDF(s) en la carpeta.")

    total_saved = 0
    for pdf in pdfs:
        local_path = os.path.join(downloads_dir, sanitize_filename(pdf["name"]))
        print(f"Descargando: {pdf['name']}")
        download_pdf(service, pdf["id"], local_path)

        saved = extract_matching_pages(local_path, keywords, output_dir, zoom)
        if saved:
            print(f"  -> {len(saved)} página(s) guardada(s):")
            for path in saved:
                print(f"     {path}")
        else:
            print("  -> ninguna página coincidió con las palabras clave.")
        total_saved += len(saved)

    print(f"\nListo. {total_saved} imagen(es) guardada(s) en '{output_dir}'.")


if __name__ == "__main__":
    main()
