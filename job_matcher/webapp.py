from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Job Matcher WebApp")

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "templates")), name="static")


@app.get("/webapp", response_class=HTMLResponse)
async def profile_form(request: Request) -> HTMLResponse:
    options = {
        "platforms": ["freelancer", "upwork", "fiverr", "toptal"],
        "positions": [
            "front developer",
            "back developer",
            "fullstack developer",
            "data scientist",
            "devops engineer",
            "mobile developer",
        ],
        "availability": ["part-time", "full-time", "hourly"],
        "experience_level": ["entry", "intermediate", "expert"],
        "location": ["remote", "on-site", "hybrid"],
        "languages": ["English", "Spanish", "French", "German", "Chinese"],
        "currency": ["USD", "EUR", "GBP"],
    }
    return templates.TemplateResponse(
        "profile_form.html",
        {"request": request, "options": options},
    )


@app.get("/bid-form", response_class=HTMLResponse)
async def bid_form(request: Request, job_id: int, title: str, currency: str = "USD") -> HTMLResponse:
    context = {
        "request": request,
        "job_id": job_id,
        "title": title,
        "currency": currency,
    }
    return templates.TemplateResponse("bid_form.html", context)
