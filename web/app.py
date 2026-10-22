"""MikeAdamsNC.com: the web server.

One small Python app. Today it serves the coming-soon page; the projects, about and
idea pages will be added here. Brand files (logo, icons) are served from brand/.
"""
import pathlib
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

ROOT = pathlib.Path(__file__).resolve().parent.parent
EASTERN = ZoneInfo("America/New_York")

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/brand", StaticFiles(directory=ROOT / "brand"), name="brand")
templates = Jinja2Templates(directory=ROOT / "web" / "templates")


@app.get("/")
def home(request: Request):
    year = datetime.now(EASTERN).year
    return templates.TemplateResponse(request, "coming_soon.html", {"year": year})


@app.get("/health")
def health():
    """The scheduler pings this every 10 minutes so the site stays warm.
    (Not /healthz: Cloud Run reserves paths ending in z.)"""
    return PlainTextResponse("ok")


@app.get("/favicon.ico")
def favicon():
    from fastapi.responses import FileResponse
    return FileResponse(ROOT / "brand" / "icon" / "favicon-32.png", media_type="image/png")
