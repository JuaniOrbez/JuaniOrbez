"""Interfaz gráfica simple para el Drive PDF Screenshot Agent.

Permite configurar la carpeta de Drive, las palabras clave y la carpeta de
salida sin usar la terminal, y ejecutar el proceso con un botón.
"""

import os
import queue
import re
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

import yaml

import main as agent

CONFIG_PATH = "config.yaml"
EXAMPLE_CONFIG_PATH = "config.example.yaml"

FOLDER_URL_RE = re.compile(r"/folders/([a-zA-Z0-9_-]+)")


def extract_folder_id(value):
    value = value.strip()
    match = FOLDER_URL_RE.search(value)
    return match.group(1) if match else value


class QueueWriter:
    """Redirige texto (ej. stdout) hacia una cola para mostrarlo en la GUI."""

    def __init__(self, log_queue):
        self.log_queue = log_queue

    def write(self, text):
        if text:
            self.log_queue.put(text)

    def flush(self):
        pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Drive PDF Screenshot Agent")
        self.geometry("640x560")
        self.resizable(False, False)

        self.log_queue = queue.Queue()
        self.worker_thread = None

        self._build_widgets()
        self._load_config()
        self.after(100, self._poll_log_queue)

    def _build_widgets(self):
        padding = {"padx": 12, "pady": 6}

        tk.Label(self, text="Carpeta de Google Drive (ID o link)", anchor="w").pack(
            fill="x", **padding
        )
        self.folder_entry = tk.Entry(self)
        self.folder_entry.pack(fill="x", padx=12)

        tk.Label(
            self,
            text="Palabras clave (una por línea): páginas que contengan alguna se capturan",
            anchor="w",
        ).pack(fill="x", **padding)
        self.keywords_text = tk.Text(self, height=6)
        self.keywords_text.pack(fill="x", padx=12)

        tk.Label(self, text="Carpeta de salida (imágenes)", anchor="w").pack(
            fill="x", **padding
        )
        output_frame = tk.Frame(self)
        output_frame.pack(fill="x", padx=12)
        self.output_entry = tk.Entry(output_frame)
        self.output_entry.pack(side="left", fill="x", expand=True)
        tk.Button(output_frame, text="Elegir...", command=self._choose_output_dir).pack(
            side="left", padx=(6, 0)
        )

        button_frame = tk.Frame(self)
        button_frame.pack(fill="x", padx=12, pady=(12, 6))
        self.run_button = tk.Button(
            button_frame, text="Ejecutar", command=self._on_run, bg="#2e7d32", fg="white"
        )
        self.run_button.pack(side="left")
        tk.Button(
            button_frame, text="Guardar configuración", command=self._save_config
        ).pack(side="left", padx=(8, 0))
        tk.Button(
            button_frame, text="Abrir carpeta de resultados", command=self._open_output_dir
        ).pack(side="left", padx=(8, 0))

        tk.Label(self, text="Registro", anchor="w").pack(fill="x", padx=12)
        self.log_widget = scrolledtext.ScrolledText(self, height=16, state="disabled")
        self.log_widget.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def _load_config(self):
        path = CONFIG_PATH if os.path.exists(CONFIG_PATH) else EXAMPLE_CONFIG_PATH
        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        self.folder_entry.insert(0, config.get("drive_folder_id", ""))
        self.keywords_text.insert("1.0", "\n".join(config.get("keywords", [])))
        self.output_entry.insert(0, config.get("output_dir", "./output"))
        self._extra_config = {
            "downloads_dir": config.get("downloads_dir", "./downloads"),
            "zoom": config.get("zoom", 2.0),
            "credentials_file": config.get("credentials_file", "credentials.json"),
            "token_file": config.get("token_file", "token.json"),
        }

    def _current_config(self):
        keywords = [
            line.strip()
            for line in self.keywords_text.get("1.0", "end").splitlines()
            if line.strip()
        ]
        return {
            "drive_folder_id": extract_folder_id(self.folder_entry.get()),
            "keywords": keywords,
            "output_dir": self.output_entry.get().strip() or "./output",
            **self._extra_config,
        }

    def _save_config(self):
        config = self._current_config()
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
        self._log("Configuración guardada en config.yaml\n")

    def _choose_output_dir(self):
        chosen = filedialog.askdirectory()
        if chosen:
            self.output_entry.delete(0, "end")
            self.output_entry.insert(0, chosen)

    def _open_output_dir(self):
        output_dir = self.output_entry.get().strip() or "./output"
        os.makedirs(output_dir, exist_ok=True)
        if sys.platform == "darwin":
            os.system(f'open "{output_dir}"')
        elif sys.platform.startswith("linux"):
            os.system(f'xdg-open "{output_dir}"')
        else:
            os.startfile(output_dir)  # noqa: PLW1508 (Windows only)

    def _on_run(self):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("En progreso", "Ya hay una ejecución en curso.")
            return

        if not self.folder_entry.get().strip():
            messagebox.showwarning("Falta información", "Ingresá el ID o link de la carpeta de Drive.")
            return

        self._save_config()
        self.run_button.config(state="disabled", text="Ejecutando...")
        self.log_widget.config(state="normal")
        self.log_widget.delete("1.0", "end")
        self.log_widget.config(state="disabled")

        self.worker_thread = threading.Thread(target=self._run_agent, daemon=True)
        self.worker_thread.start()

    def _run_agent(self):
        original_stdout = sys.stdout
        sys.stdout = QueueWriter(self.log_queue)
        try:
            agent.main_with_config(CONFIG_PATH)
        except SystemExit as e:
            self.log_queue.put(f"\n{e}\n")
        except Exception as e:  # noqa: BLE001
            self.log_queue.put(f"\nError: {e}\n")
        finally:
            sys.stdout = original_stdout
            self.log_queue.put("__DONE__")

    def _poll_log_queue(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                if line == "__DONE__":
                    self.run_button.config(state="normal", text="Ejecutar")
                else:
                    self._log(line)
        except queue.Empty:
            pass
        self.after(100, self._poll_log_queue)

    def _log(self, text):
        self.log_widget.config(state="normal")
        self.log_widget.insert("end", text)
        self.log_widget.see("end")
        self.log_widget.config(state="disabled")


if __name__ == "__main__":
    App().mainloop()
