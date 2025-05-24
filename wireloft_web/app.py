import os
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Paths
CONFIG_FILE = os.environ.get("DW_CONFIG_FILE", os.path.join(os.getcwd(), "config", "config.yml"))
COOKIES_FILE = os.environ.get("DW_COOKIES_FILE", os.path.join(os.getcwd(), "config", "cookies.txt"))
DOWNLOAD_DIR = os.environ.get("DW_DOWNLOAD_DIR", os.path.join(os.getcwd(), "downloads"))

app = FastAPI(title="Wireloft")

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

@app.get("/")
def index():
    return FileResponse(os.path.join(FRONTEND_DIR, "public", "index.html"))

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


def _load_config():
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f)

def _save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        yaml.safe_dump(cfg, f)

def _show_path(name):
    return os.path.join(DOWNLOAD_DIR, name)

def _dir_size(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except FileNotFoundError:
                pass
    return total


def _library_overview():
    cfg = _load_config()
    shows = cfg.get("shows", [])
    show_sizes = {s["name"]: _dir_size(_show_path(s["name"])) for s in shows}
    total_size = sum(show_sizes.values())
    file_count = 0
    for _, _, files in os.walk(DOWNLOAD_DIR):
        file_count += len(files)
    return {
        "library_size": total_size,
        "files": file_count,
        "shows": len(shows),
    }


@app.get("/api/overview")
def api_overview():
    return _library_overview()


@app.get("/api/shows")
def api_shows():
    cfg = _load_config()
    result = []
    for s in cfg.get("shows", []):
        size = _dir_size(_show_path(s["name"]))
        result.append({"name": s["name"], "url": s.get("url", ""), "size": size})
    return result


class ShowConfig(BaseModel):
    config: dict


@app.get("/api/shows/{name}")
def api_show(name: str):
    cfg = _load_config()
    for s in cfg.get("shows", []):
        if s.get("name") == name:
            size = _dir_size(_show_path(name))
            return {"name": name, "size": size, "config": s}
    raise HTTPException(status_code=404, detail="Show not found")


@app.put("/api/shows/{name}")
def api_update_show(name: str, data: ShowConfig):
    cfg = _load_config()
    for idx, s in enumerate(cfg.get("shows", [])):
        if s.get("name") == name:
            cfg["shows"][idx] = data.config
            _save_config(cfg)
            return {"status": "ok"}
    raise HTTPException(status_code=404, detail="Show not found")


@app.get("/api/settings")
def api_settings():
    cfg = _load_config()
    cfg.pop("shows", None)
    return cfg


class SettingsModel(BaseModel):
    settings: dict


@app.put("/api/settings")
def api_update_settings(data: SettingsModel):
    cfg = _load_config()
    for k, v in data.settings.items():
        cfg[k] = v
    _save_config(cfg)
    return {"status": "ok"}
