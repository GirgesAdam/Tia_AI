from fastapi import APIRouter

from app.api.routes.agent import router as agent_router
from app.api.routes.analytics import router as analytics_router
from app.api.routes.analytics_views import router as analytics_views_router
from app.api.routes.auth import router as auth_router
from app.api.routes.automations import router as automations_router
from app.api.routes.booking import router as booking_router
from app.api.routes.campaign_analytics import router as campaign_analytics_router
from app.api.routes.channels import router as channels_router
from app.api.routes.clinic import router as clinic_router
from app.api.routes.clinic_setup_v2 import router as clinic_setup_v2_router
from app.api.routes.crm import router as crm_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.expenses import router as expenses_router
from app.api.routes.health import router as health_router
from app.api.routes.inbox import router as inbox_router
from app.api.routes.onboarding import router as onboarding_router
from app.api.routes.operations import router as operations_router
from app.api.routes.payments import router as payments_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(agent_router, prefix="/agent", tags=["agent"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["analytics"])
api_router.include_router(analytics_views_router, prefix="/analytics", tags=["analytics"])
api_router.include_router(campaign_analytics_router, prefix="/analytics", tags=["analytics"])
api_router.include_router(automations_router, prefix="/automations", tags=["automations"])
api_router.include_router(booking_router, prefix="/booking", tags=["booking"])
api_router.include_router(channels_router, prefix="/channels", tags=["channels"])
api_router.include_router(clinic_router, prefix="/clinic", tags=["clinic"])
api_router.include_router(clinic_setup_v2_router, prefix="/clinic", tags=["clinic-setup"])
api_router.include_router(crm_router, prefix="/crm", tags=["crm"])
api_router.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(expenses_router, prefix="/expenses", tags=["expenses"])
api_router.include_router(inbox_router, prefix="/inbox", tags=["inbox"])
api_router.include_router(onboarding_router, prefix="/onboarding", tags=["onboarding"])
api_router.include_router(operations_router, prefix="/operations", tags=["operations"])
api_router.include_router(payments_router, prefix="/payments", tags=["payments"])
