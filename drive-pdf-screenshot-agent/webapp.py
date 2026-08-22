"""Interfaz web local para el Drive PDF Screenshot Agent.

Corre un servidor solo accesible desde tu propia computadora (127.0.0.1) y
abre el navegador automáticamente. Permite configurar la carpeta de Drive,
las palabras clave y la carpeta de salida sin usar la terminal.
"""

import contextlib
import io
import os
import re
import subprocess
import sys
import threading
import webbrowser

import yaml
from flask import Flask, redirect, render_template_string, request, url_for

import main as agent

CONFIG_PATH = "config.yaml"
EXAMPLE_CONFIG_PATH = "config.example.yaml"
PORT = 5050

FOLDER_URL_RE = re.compile(r"/folders/([a-zA-Z0-9_-]+)")

app = Flask(__name__)


def extract_folder_id(value):
    value = value.strip()
    match = FOLDER_URL_RE.search(value)
    return match.group(1) if match else value


def load_current_config():
    path = CONFIG_PATH if os.path.exists(CONFIG_PATH) else EXAMPLE_CONFIG_PATH
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_config(config):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)


PAGE_TEMPLATE = """
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Drive PDF Screenshot Agent</title>
<style>
  body { font-family: -apple-system, sans-serif; max-width: 720px; margin: 40px auto; padding: 0 16px; color: #222; }
  label { display: block; margin-top: 16px; font-weight: 600; }
  input[type=text], textarea { width: 100%; padding: 8px; font-size: 14px; box-sizing: border-box; }
  textarea { height: 100px; font-family: inherit; }
  button { margin-top: 20px; padding: 10px 20px; font-size: 15px; cursor: pointer; }
  pre { background: #111; color: #0f0; padding: 16px; white-space: pre-wrap; border-radius: 6px; overflow-x: auto; }
  .actions { margin-top: 16px; }
  .hint { color: #666; font-size: 13px; margin-top: 4px; }
</style>
</head>
<body>
  <h1>Drive PDF Screenshot Agent</h1>

  <form method="post" action="/run">
    <label>Carpeta de Google Drive (ID o link)</label>
    <input type="text" name="folder" value="{{ folder }}">

    <label>Palabras clave (una por línea)</label>
    <textarea name="keywords">{{ keywords }}</textarea>
    <div class="hint">Se captura toda página que contenga alguna de estas palabras.</div>

    <label>Carpeta de salida</label>
    <input type="text" name="output_dir" value="{{ output_dir }}">

    <div class="actions">
      <button type="submit">Ejecutar</button>
    </div>
  </form>

  {% if log is not none %}
  <h2>Resultado</h2>
  <pre>{{ log }}</pre>
  <form method="get" action="/open-output">
    <button type="submit">Abrir carpeta de resultados</button>
  </form>
  {% endif %}
</body>
</html>
"""


@app.route("/", methods=["GET"])
def index():
    config = load_current_config()
    return render_template_string(
        PAGE_TEMPLATE,
        folder=config.get("drive_folder_id", ""),
        keywords="\n".join(config.get("keywords", [])),
        output_dir=config.get("output_dir", "./output"),
        log=None,
    )


@app.route("/run", methods=["POST"])
def run():
    config = load_current_config()
    config["drive_folder_id"] = extract_folder_id(request.form.get("folder", ""))
    config["keywords"] = [
        line.strip() for line in request.form.get("keywords", "").splitlines() if line.strip()
    ]
    config["output_dir"] = request.form.get("output_dir", "./output").strip() or "./output"
    save_config(config)

    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            agent.run_with_config(config)
    except SystemExit as e:
        buffer.write(f"\n{e}\n")
    except Exception as e:  # noqa: BLE001
        buffer.write(f"\nError: {e}\n")

    return render_template_string(
        PAGE_TEMPLATE,
        folder=config["drive_folder_id"],
        keywords="\n".join(config["keywords"]),
        output_dir=config["output_dir"],
        log=buffer.getvalue(),
    )


@app.route("/open-output", methods=["GET"])
def open_output():
    config = load_current_config()
    output_dir = config.get("output_dir", "./output")
    os.makedirs(output_dir, exist_ok=True)
    if sys.platform == "darwin":
        subprocess.run(["open", output_dir])
    elif sys.platform.startswith("linux"):
        subprocess.run(["xdg-open", output_dir])
    else:
        os.startfile(output_dir)  # noqa: PLW1508 (Windows only)
    return redirect(url_for("index"))


def main():
    threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    app.run(host="127.0.0.1", port=PORT, debug=False)


if __name__ == "__main__":
    main()
