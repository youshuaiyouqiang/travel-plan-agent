from __future__ import annotations

import asyncio
import logging
import os
import urllib.parse
import urllib.request
import json as _json

from fastapi import APIRouter, Request

from application.dto.request import BatchGeocodeRequest, IntlGeocodeRequest
from application.exceptions import (
    UnauthorizedException,
    ServiceUnavailableException,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["geocode"])


def _nominatim_lookup(query: str) -> dict | None:
    """同步调用 Nominatim —— 必须在线程池中执行，避免阻塞事件循环。"""
    try:
        qs = urllib.parse.urlencode(
            {
                "q": query,
                "format": "json",
                "limit": "1",
                "accept-language": "zh",
            }
        )
        url = f"https://nominatim.openstreetmap.org/search?{qs}"
        req = urllib.request.Request(url, headers={"User-Agent": "ClawTravelApp/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read().decode())
        if data and len(data) > 0:
            lat = float(data[0].get("lat", 0))
            lon = float(data[0].get("lon", 0))
            if lat != 0 and lon != 0:
                return {
                    "lng": lon,
                    "lat": lat,
                    "formatted": data[0].get("display_name", ""),
                }
    except Exception as e:
        logger.warning("Nominatim geocode failed for '%s': %s", query, e)
    return None


@router.post("")
async def batch_geocode(req: BatchGeocodeRequest, request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    amap_key = os.environ.get("AMAP_WEBSERVICE_KEY", "")
    if not amap_key:
        raise ServiceUnavailableException("高德地图服务未配置")

    results = []
    for addr in req.addresses:
        addr = str(addr).strip()
        if not addr:
            results.append({"address": addr, "lng": None, "lat": None, "formatted": ""})
            continue
        try:
            qs = urllib.parse.urlencode({"address": addr, "key": amap_key})
            url = f"https://restapi.amap.com/v3/geocode/geo?{qs}"
            req_obj = urllib.request.Request(url)
            with urllib.request.urlopen(req_obj, timeout=10) as resp:
                data = _json.loads(resp.read().decode())
            geocodes = data.get("geocodes", [])
            if geocodes:
                loc = geocodes[0].get("location", "")
                parts = loc.split(",") if loc else []
                results.append(
                    {
                        "address": addr,
                        "lng": float(parts[0]) if len(parts) == 2 else None,
                        "lat": float(parts[1]) if len(parts) == 2 else None,
                        "formatted": geocodes[0].get("formatted_address", ""),
                    }
                )
            else:
                results.append({"address": addr, "lng": None, "lat": None, "formatted": ""})
        except Exception as e:
            logger.warning("Geocode failed for '%s': %s", addr, e)
            results.append({"address": addr, "lng": None, "lat": None, "formatted": ""})
    return {"results": results}


@router.post("/intl")
async def intl_geocode(req: IntlGeocodeRequest, request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    from api.intl_coords import lookup_intl_coords

    coords = lookup_intl_coords(req.address, req.city or None)
    if coords:
        return {"address": req.address, "lng": coords[0], "lat": coords[1], "formatted": req.address}

    query = f"{req.city} {req.address}" if req.city and req.address not in req.city else req.address
    # 用线程池执行同步阻塞的 Nominatim 调用，避免卡死事件循环
    result = await asyncio.to_thread(_nominatim_lookup, query)
    if result:
        return {"address": req.address, **result}
    return {"address": req.address, "lng": None, "lat": None, "formatted": ""}
