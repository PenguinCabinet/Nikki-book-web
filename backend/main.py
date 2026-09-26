import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.auth import routes as auth
from app.nikki import routes as nikki
from app.habits import routes as habits
from app.sync import routes as sync
from app.core.settings import jst
from app.storage.database import create_db_and_tables
from app.nikki.routes import apply_nikki_template_to_today_nikki
from app.habits.routes import count_habit_keyword_continuations

load_dotenv()
if os.getenv("NIKKI_BOOK_SECRET_KEY") is None:
    raise EnvironmentError("NIKKI_BOOK_SECRET_KEY is None")

scheduler = AsyncIOScheduler(timezone=jst)


def create_template_batch_trigger():
    return CronTrigger(hour=0, minute=0, timezone=jst)


app = FastAPI()
allow_origins = ["http://localhost:5173"]
frontend_url = os.getenv("frontend_url")
if frontend_url is not None:
    allow_origins.append(frontend_url)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(nikki.router)
app.include_router(sync.router)
app.include_router(habits.router)


@app.on_event("startup")
def on_startup():
    scheduler.add_job(apply_nikki_template_to_today_nikki, create_template_batch_trigger())
    scheduler.add_job(count_habit_keyword_continuations, create_template_batch_trigger())
    scheduler.start()
    create_db_and_tables()


@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    print(exc.errors())
    raise exc
