# Drive PDF Screenshot Agent

Script en Python que recorre una carpeta de Google Drive, busca dentro de
cada PDF las páginas que contienen ciertas palabras clave, y guarda esas
páginas como imágenes PNG en una carpeta local — listas para subir a un CRM.

## Cómo funciona

1. Se conecta a tu Google Drive (OAuth, de forma read-only).
2. Lista los PDFs de la carpeta que indiques.
3. Descarga cada PDF a una carpeta temporal local (`downloads/`).
4. Revisa el texto de cada página buscando las palabras clave configuradas.
5. Renderiza como imagen PNG cada página que coincide y la guarda en
   `output/`, con el nombre `<nombre_pdf>_pagina<N>.png`.

## Requisitos

- Python 3.9+
- Una cuenta de Google con acceso a la carpeta de Drive.
- Un proyecto en Google Cloud con la API de Drive habilitada.

## Setup

### 1. Instalar dependencias

```bash
python -m venv venv
source venv/bin/activate  # en Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Crear credenciales de Google Drive

1. Entrá a [Google Cloud Console](https://console.cloud.google.com/).
2. Creá un proyecto (o usá uno existente).
3. Habilitá la **Google Drive API** (menú "APIs & Services" → "Library").
4. Andá a "APIs & Services" → "Credentials" → "Create Credentials" →
   "OAuth client ID".
5. Tipo de aplicación: **Desktop app**.
6. Descargá el JSON generado y guardalo en esta carpeta como
   `credentials.json`.

La primera vez que corras el script se va a abrir el navegador para que
inicies sesión y autorices el acceso (solo lectura). Después queda guardado
un `token.json` local y no vuelve a pedirte login.

### 3. Configurar

Copiá el archivo de ejemplo:

```bash
cp config.example.yaml config.yaml
```

Editá `config.yaml`:

- `drive_folder_id`: el ID de la carpeta de Drive (lo sacás de la URL,
  `https://drive.google.com/drive/folders/<ID>`).
- `keywords`: lista de palabras o frases a buscar en cada página. Si una
  página contiene alguna de ellas, se guarda como imagen.
- `output_dir` / `downloads_dir`: carpetas locales de salida.
- `zoom`: resolución de las imágenes generadas.

### 4. Ejecutar

```bash
python main.py
```

Al terminar, las imágenes están en la carpeta indicada por `output_dir`
(por defecto `./output`), listas para subir manualmente al CRM.

## Notas

- `credentials.json`, `token.json`, `config.yaml`, `downloads/` y
  `output/` están en `.gitignore`: nunca se suben al repo porque contienen
  datos privados.
- El matching de palabras clave no distingue mayúsculas/minúsculas y busca
  coincidencia de substring simple.
- Si querés que además suba las imágenes directamente al CRM (si tiene
  API), se puede agregar un paso extra al final de `main.py`.
