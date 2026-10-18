"""Strict public observation boundary. Unknown nested fields are discarded.

This is structural validation, not a claim that arbitrary prose is non-sensitive.
Only already-public collectors may supply free text; owner state is never an input.
"""
import datetime as dt
import ipaddress
import json
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode


def text(value, maximum, field, default=''):
    if value is None:
        return default
    if not isinstance(value, str) or len(value) > maximum or '\x00' in value:
        raise ValueError('Invalid public field: ' + field)
    return value


def public_url(value):
    value = text(value, 4096, 'url')
    try:
        u = urlsplit(value)
        host = u.hostname or ''
        if u.scheme not in ('http', 'https') or not host or u.username or u.password:
            raise ValueError()
        if host == 'localhost' or host.endswith(('.local', '.internal')) or '.' not in host:
            raise ValueError()
        try:
            if not ipaddress.ip_address(host).is_global:
                raise ValueError()
        except ValueError:
            if re.fullmatch(r'[0-9.:]+', host) or ':' in host:
                raise ValueError()
        if u.port not in (None, 80, 443):
            raise ValueError()
        pairs = parse_qsl(u.query, keep_blank_values=True)
        if any(re.search(r'token|secret|password|api.?key|authorization|signature', k, re.I) for k, _ in pairs):
            raise ValueError()
        return urlunsplit((u.scheme, u.netloc.lower(), u.path, urlencode(sorted(pairs)), ''))
    except (ValueError, TypeError):
        raise ValueError('Invalid or non-public URL') from None


def instant(value):
    if value is None or value == '':
        return None
    value = text(value, 64, 'timestamp')
    # Day-only publication is preserved as such; never invent a timezone.
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return dt.date.fromisoformat(value).isoformat()
    d = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if d.tzinfo is None:
        raise ValueError('Timestamp timezone required')
    return d.astimezone(dt.timezone.utc).isoformat()


def sanitize(raw, canonical=lambda u: u):
    if not isinstance(raw, dict):
        raise ValueError('Observation must be an object')
    out = {'url': public_url(canonical(public_url(raw.get('url'))))}
    for key, limit in (('title', 2000), ('summary', 10000), ('scope', 500)):
        out[key] = text(raw.get(key), limit, key)
    for key in ('published_at', 'updated_at'):
        out[key] = instant(raw.get(key))
    cats = raw.get('categories')
    if cats is None: cats = []
    if not isinstance(cats, list) or len(cats) > 40:
        raise ValueError('Invalid categories')
    out['categories'] = sorted(set(text(x, 120, 'category') for x in cats))
    sources = raw.get('sources')
    if sources is None: sources = []
    if not isinstance(sources, list) or len(sources) > 32:
        raise ValueError('Invalid sources')
    clean = []
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError('Source must be an object')
        s = {}
        for key, limit in (('id', 100), ('name', 200), ('identifier', 500)):
            if source.get(key) is not None:
                s[key] = text(source[key], limit, 'source.' + key)
        for key in ('entry_url', 'feed_url', 'terms'):
            if source.get(key):
                s[key] = public_url(source[key])
        # No metadata, author details, notes, profile, credentials or arbitrary blobs.
        clean.append(s)
    out['sources'] = sorted(clean, key=lambda s: json.dumps(s, sort_keys=True))
    return out
