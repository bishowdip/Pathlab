"""
Minimal cache-backed rate limiter. No external deps.

Usage:
    @rate_limit(key="chat", max_hits=20, window_seconds=60)
    def my_view(request): ...

Keyed by (view-key + client IP). Anonymous and authenticated users share the
IP bucket — intentional for abuse protection.
"""
from functools import wraps
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse


def _client_ip(request):
    """
    Resolve the client IP honouring a configured number of trusted proxies.

    By default (TRUSTED_PROXY_COUNT=0) we use REMOTE_ADDR — the TCP peer.
    Trusting X-Forwarded-For without a proxy count is a well-known spoof
    vector: anyone can send `X-Forwarded-For: 1.2.3.4` and bypass rate limits.

    When behind N reverse proxies (Cloudflare + Nginx = 2), each one appends
    its upstream to XFF, so the Nth-from-right entry is the real client.
    """
    proxy_count = int(getattr(settings, "TRUSTED_PROXY_COUNT", 0) or 0)
    remote = request.META.get("REMOTE_ADDR", "0.0.0.0")
    if proxy_count <= 0:
        return remote
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if not xff:
        return remote
    parts = [p.strip() for p in xff.split(",") if p.strip()]
    # Take the Nth-from-right entry (the last one our trusted proxies haven't added).
    if len(parts) >= proxy_count:
        return parts[-proxy_count]
    return remote


def rate_limit(key, max_hits, window_seconds):
    """Decorator. Returns 429 when a client exceeds max_hits in the window."""
    def deco(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            cache_key = f"rl:{key}:{_client_ip(request)}"
            current = cache.get(cache_key, 0)
            if current >= max_hits:
                # Respect content-type — JSON clients get JSON, HTML gets text.
                if request.content_type == "application/json" or \
                   request.META.get("HTTP_ACCEPT", "").startswith("application/json"):
                    return JsonResponse(
                        {"error": "Too many requests. Please slow down."},
                        status=429,
                    )
                return HttpResponse(
                    "Too many requests. Please slow down and try again in a minute.",
                    status=429,
                )
            # Atomic-ish increment. cache.add sets value only if missing.
            if current == 0:
                cache.add(cache_key, 1, timeout=window_seconds)
            else:
                try:
                    cache.incr(cache_key)
                except ValueError:
                    cache.set(cache_key, 1, timeout=window_seconds)
            return view(request, *args, **kwargs)
        return wrapper
    return deco
