import logging
import uvicorn
import threading
import time

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from module.api import router
from module.conf import VERSION, settings, setup_logger
from module.rss import RSSAnalyser
from module.conf.uvicorn_logging import logging_config


logger = logging.getLogger(__name__)


stop_event = threading.Event()

rss_link = settings.rss_link()


def rss_loop(stop_event, rss_link: str):
    rss_analyser = RSSAnalyser()
    while not stop_event.is_set():
        rss_analyser.run(rss_link)
        logger.info("RSS loop finished.")
        stop_event.wait(settings.program.sleep_time)


rss_thread = threading.Thread(
    target=rss_loop,
    args=(stop_event, rss_link),
)


@router.on_event("startup")
async def startup():
    global rss_thread
    setup_logger()
    rss_thread = threading.Thread(
        target=rss_loop,
        args=(stop_event, rss_link),
    )
    rss_thread.start()


@router.on_event("shutdown")
async def shutdown():
    stop_event.set()
    logger.info("Stopping RSS analyser...")


@router.get("/api/v1/restart", tags=["program"])
async def restart():
    global rss_thread
    if not rss_thread.is_alive():
        return {"status": "Already stopped."}
    stop_event.set()
    logger.info("Stopping RSS analyser...")
    rss_thread.join()
    stop_event.clear()
    time.sleep(1)
    settings.load()
    rss_link = settings.rss_link()
    if "://" not in rss_link:
        rss_link = f"https://{rss_link}"
    rss_thread = threading.Thread(
        target=rss_loop,
        args=(stop_event, rss_link),
    )
    rss_thread.start()
    return {"status": "ok"}


@router.get("/api/v1/start", tags=["program"])
async def start():
    global rss_thread
    if rss_thread.is_alive():
        return {"status": "Already started."}
    rss_thread = threading.Thread(
        target=rss_loop,
        args=(stop_event, rss_link),
    )
    rss_thread.start()
    return {"status": "ok"}


@router.get("/api/v1/stop", tags=["program"])
async def stop():
    global rss_thread
    if not rss_thread.is_alive():
        return {"status": "Already stopped."}
    stop_event.set()
    logger.info("Stopping RSS analyser...")
    rss_thread.join()
    stop_event.clear()
    return {"status": "ok"}


if VERSION != "DEV_VERSION":
    router.mount("/assets", StaticFiles(directory="templates/assets"), name="assets")
    templates = Jinja2Templates(directory="templates")

    # HTML Response
    @router.get("/{full_path:path}", response_class=HTMLResponse, tags=["html"])
    def index(request: Request):
        context = {"request": request}
        return templates.TemplateResponse("index.html", context)

else:

    @router.get("/", status_code=302, tags=["html"])
    def index():
        return RedirectResponse("/docs")


if __name__ == "__main__":
    uvicorn.run(
        router, host="0.0.0.0", port=settings.program.webui_port
    )
