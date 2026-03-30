import hashlib
import time
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse


DEFAULT_RATE_LIMITS = {
    'login_ip': {'limit': 5, 'window': 15 * 60},
    'login_username': {'limit': 5, 'window': 15 * 60},
    'register_ip': {'limit': 5, 'window': 60 * 60},
    'transaction_submit_user': {'limit': 10, 'window': 60 * 60},
    'transaction_action_user': {'limit': 20, 'window': 60 * 60},
    'admin_action_user': {'limit': 30, 'window': 60 * 60},
}


def get_client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return (
        request.META.get('HTTP_X_REAL_IP')
        or request.META.get('REMOTE_ADDR')
        or 'unknown'
    )


def ip_key(request):
    return get_client_ip(request)


def user_key(request):
    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        return f"user:{user.pk}"
    return f"ip:{get_client_ip(request)}"


def post_field_key(field_name, default='anonymous'):
    def builder(request):
        value = request.POST.get(field_name, '').strip().lower()
        return value or default

    return builder


def _get_rate_limit(name):
    configured = getattr(settings, 'RATE_LIMITS', {})
    rate_limit = dict(DEFAULT_RATE_LIMITS.get(name, {}))
    rate_limit.update(configured.get(name, {}))
    return rate_limit


def _bucket_key(name, identifier, window):
    digest = hashlib.sha256(str(identifier).encode('utf-8')).hexdigest()
    bucket = int(time.time() // window)
    return f"ratelimit:{name}:{digest}:{bucket}"


def _consume(name, identifier, limit, window):
    key = _bucket_key(name, identifier, window)
    timeout = max(int(window) + 1, 1)
    cache.add(key, 0, timeout=timeout)
    try:
        count = cache.incr(key)
    except ValueError:
        cache.add(key, 1, timeout=timeout)
        count = 1

    retry_after = max(window - int(time.time() % window), 1)
    return count <= limit, retry_after


def _rate_limited_response(name, retry_after):
    message = (
        f"Too many requests for {name.replace('_', ' ')}. "
        f"Please try again in {retry_after} seconds."
    )
    response = HttpResponse(message, status=429, content_type='text/plain')
    response['Retry-After'] = str(retry_after)
    return response


def rate_limit(name, *, key_func=None, methods=('POST',)):
    key_func = key_func or ip_key

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if methods and request.method not in methods:
                return view_func(request, *args, **kwargs)

            rate_limit_config = _get_rate_limit(name)
            if not rate_limit_config:
                return view_func(request, *args, **kwargs)

            limit = int(rate_limit_config.get('limit', 0))
            window = int(rate_limit_config.get('window', 0))
            if limit <= 0 or window <= 0:
                return view_func(request, *args, **kwargs)

            identifier = key_func(request) or 'anonymous'
            allowed, retry_after = _consume(name, identifier, limit, window)
            if not allowed:
                return _rate_limited_response(name, retry_after)

            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator
