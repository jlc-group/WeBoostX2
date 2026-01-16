"""
API v1 routes
"""
from fastapi import APIRouter

from app.api.v1 import auth, health, pages, contents, settings, tasks, employees, products, targeting, ads, spark_auth

api_router = APIRouter(prefix="/api/v1")

# Include routers
api_router.include_router(auth.router)
api_router.include_router(health.router)
api_router.include_router(contents.router)
api_router.include_router(settings.router)
api_router.include_router(tasks.router)
api_router.include_router(employees.router)
api_router.include_router(employees.influencer_router)
api_router.include_router(products.router)
api_router.include_router(products.groups_router)
api_router.include_router(targeting.router)
api_router.include_router(ads.router)
api_router.include_router(spark_auth.router)

# Page routes (no prefix)
page_router = pages.router
