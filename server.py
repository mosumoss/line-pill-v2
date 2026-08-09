"""FastAPI アプリケーション エントリポイント。"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import api as api_router
from routers import webhook as webhook_router

app = FastAPI(
    title="line-pill v2",
    description="LIFF版 育毛特化 服薬リマインダー",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://line-pill-v2.pages.dev",
        "https://liff.line.me",
        # 開発用
        "http://localhost:5173",
        "http://localhost:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router.router, prefix="/api", tags=["api"])
app.include_router(webhook_router.router, tags=["webhook"])
