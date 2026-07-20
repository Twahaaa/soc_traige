"""REST endpoints for triage reports, stats, hosts and timeline.

All data is read from Qdrant via ``QdrantService`` — no synthetic values.
Field names are snake_case and match ``triage.report_schema.TriageReport``
exactly (one source of truth).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from dashboard.config_loader import get_async_qdrant
from dashboard.schemas import (
    HealthOut,
    HostStatOut,
    ReportListOut,
    StatsOut,
    TimelineEventOut,
    TriageReportOut,
)
from dashboard.services.qdrant_service import QdrantService
from qdrant_client import AsyncQdrantClient

router = APIRouter()


def get_qdrant_service(
    client: AsyncQdrantClient = Depends(get_async_qdrant),
) -> QdrantService:
    return QdrantService(client)


_SEVERITY_QUERY_DESC = (
    "Filter by severity (Critical/High/Medium/Low/Informational). Omit for all."
)


@router.get("/reports", response_model=ReportListOut)
async def list_reports(
    severity: Optional[str] = Query(None, description=_SEVERITY_QUERY_DESC),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    svc: QdrantService = Depends(get_qdrant_service),
) -> ReportListOut:
    items, total = await svc.list_reports(severity=severity, limit=limit, offset=offset)
    return ReportListOut(items=items, total=total, limit=limit, offset=offset)


@router.get("/reports/{incident_id}", response_model=TriageReportOut)
async def get_report(
    incident_id: str,
    svc: QdrantService = Depends(get_qdrant_service),
) -> TriageReportOut:
    report = await svc.get_report(incident_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"report {incident_id} not found")
    return report


@router.get("/stats", response_model=StatsOut)
async def get_stats(
    svc: QdrantService = Depends(get_qdrant_service),
) -> StatsOut:
    return await svc.compute_stats()


@router.get("/hosts", response_model=list[HostStatOut])
async def list_hosts(
    limit: int = Query(20, ge=1, le=100),
    svc: QdrantService = Depends(get_qdrant_service),
) -> list[HostStatOut]:
    return await svc.list_host_stats(limit=limit)


@router.get("/timeline", response_model=list[TimelineEventOut])
async def list_timeline(
    limit: int = Query(100, ge=1, le=500),
    svc: QdrantService = Depends(get_qdrant_service),
) -> list[TimelineEventOut]:
    return await svc.list_timeline_events(limit=limit)