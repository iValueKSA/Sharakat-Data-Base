import asyncio
import html
import json
import re
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit, parse_qsl, urlencode

import httpx

INPUT = Path('/tmp/source-link-input.json')
OUTPUT = Path('/tmp/source-link-audit.json')
MAX_BODY = 2_500_000
TIMEOUT = httpx.Timeout(25.0, connect=12.0)


def norm(value):
    value = html.unescape(str(value or '')).casefold()
    value = re.sub(r'<[^>]+>', ' ', value)
    value = re.sub(r'[^\w\u0600-\u06ff]+', '', value, flags=re.UNICODE)
    return value


def furas_route_type(value):
    v = str(value or '').strip()
    return {'TemporaryRental': 'TempRental', 'TempRental': 'TempRental'}.get(v, v or 'Investment')


def canonical_furas_url(row):
    ref = str(row.get('reference') or row.get('official_id_original') or row.get('external_id') or '').strip()
    if not ref:
        return None
    attrs = (row.get('raw') or {}).get('attributes') or {}
    typ = furas_route_type(attrs.get('OPPORTUNITYTYPE'))
    return f"https://furas.momah.gov.sa/index.php/ar/opportunity/{quote(ref, safe='')}?{urlencode({'type': typ})}"


def content_identity(row, body, content_type):
    if 'html' not in (content_type or '').lower() and 'text' not in (content_type or '').lower():
        # The identity can still be verified from a unique, ID-bearing document URL.
        return {'reference_match': False, 'external_id_match': False, 'title_match': False,
                'owner_match': False, 'location_match': False, 'identity_match': False,
                'generic_or_error': False, 'non_html': True}
    text = html.unescape(re.sub(r'<[^>]+>', ' ', body.decode('utf-8', errors='ignore')))
    folded = norm(text)
    ref = norm(row.get('reference'))
    external = norm(row.get('external_id'))
    title = norm(row.get('title'))
    raw = row.get('raw') or {}
    attrs = raw.get('attributes') or {}
    owner = norm(attrs.get('AMANA') or row.get('owner'))
    loc = norm(attrs.get('DISTRICT') or attrs.get('CITYNAME') or row.get('location'))
    ref_match = bool(ref and ref in folded)
    external_match = bool(external and external in folded)
    title_match = bool(title and (title in folded or (len(title) > 20 and title[:min(60, len(title))] in folded)))
    owner_match = bool(owner and owner in folded)
    location_match = bool(loc and loc in folded)
    generic_or_error = any(norm(term) in folded for term in ('الصفحة غير موجودة', 'page not found', '404 not found', 'record not found', 'الفرصة غير موجودة'))
    # Prefer exact official identifiers. Where the source has no reference number,
    # require the exact normalized source title plus at least one secondary field.
    if ref or external:
        identity = (ref_match or external_match) and (title_match or location_match or owner_match)
    else:
        identity = title_match and (location_match or owner_match)
    return {'reference_match': ref_match, 'external_id_match': external_match,
            'title_match': title_match, 'owner_match': owner_match,
            'location_match': location_match, 'identity_match': bool(identity),
            'generic_or_error': generic_or_error, 'non_html': False}


async def get_url(client, sem, url, row, label):
    if not url:
        return {'label': label, 'url': url, 'class': 'MISSING_URL', 'final_url': None,
                'http_status': None, 'identity': None, 'error': None}
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.netloc:
        return {'label': label, 'url': url, 'class': 'INVALID_URL', 'final_url': None,
                'http_status': None, 'identity': None, 'error': None}
    try:
        async with sem:
            async with client.stream('GET', url) as response:
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) >= MAX_BODY:
                        break
                status = response.status_code
                final = str(response.url)
                was_redirected = bool(response.history)
                ctype = response.headers.get('content-type', '')
                identity = content_identity(row, bytes(body), ctype) if status == 200 else None
                if status == 404: cls = 'HTTP_404'
                elif status == 410: cls = 'HTTP_410'
                elif status == 403: cls = 'HTTP_403'
                elif status in (401,): cls = 'LOGIN_REQUIRED'
                elif status >= 500: cls = 'SOURCE_ERROR'
                elif status in (301, 302, 303, 307, 308): cls = 'VALID_REDIRECT' if identity and identity['identity_match'] else 'CONTENT_MISMATCH'
                elif status == 200:
                    if identity and identity['generic_or_error']:
                        cls = 'HTTP_200_BUT_CONTENT_MISMATCH'
                    elif 'login' in final.casefold() or 'signin' in final.casefold() or 'تسجيل الدخول' in norm(bytes(body).decode('utf-8', errors='ignore')):
                        cls = 'LOGIN_REQUIRED'
                    elif identity and identity['identity_match']:
                        cls = 'VALID_REDIRECT' if was_redirected else 'VALID_200'
                    else:
                        cls = 'HTTP_200_BUT_CONTENT_MISMATCH'
                else:
                    cls = 'SOURCE_ERROR'
                return {'label': label, 'url': url, 'class': cls, 'final_url': final,
                        'http_status': status, 'content_type': ctype,
                        'redirected': was_redirected, 'redirect_count': len(response.history),
                        'bytes_read': len(body), 'identity': identity, 'error': None}
    except httpx.TimeoutException as exc:
        cls = 'NETWORK_ERROR'
        return {'label': label, 'url': url, 'class': cls, 'final_url': None,
                'http_status': None, 'identity': None, 'error': type(exc).__name__}
    except httpx.HTTPError as exc:
        return {'label': label, 'url': url, 'class': 'NETWORK_ERROR', 'final_url': None,
                'http_status': None, 'identity': None, 'error': str(exc)[:300]}


async def main():
    rows = json.loads(INPUT.read_text(encoding='utf-8'))
    sem = asyncio.Semaphore(5)
    limits = httpx.Limits(max_connections=12, max_keepalive_connections=8)
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; AHDA-source-link-integrity-review/1.0)',
               'Accept': 'text/html,application/xhtml+xml,application/pdf,*/*;q=0.8'}
    out = []
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True,
                                 max_redirects=8, limits=limits, headers=headers) as client:
        for offset in range(0, len(rows), 20):
            batch = rows[offset:offset + 20]
            tasks = []
            for row in batch:
                links = []
                links.append(get_url(client, sem, row.get('url'), row, 'stored'))
                candidate = canonical_furas_url(row) if row.get('source_key') == 'furas' else None
                if candidate and candidate != row.get('url'):
                    links.append(get_url(client, sem, candidate, row, 'canonical_candidate'))
                tasks.append(asyncio.gather(*links))
            results = await asyncio.gather(*tasks)
            for row, checks in zip(batch, results):
                out.append({**row, 'canonical_candidate_url': canonical_furas_url(row) if row.get('source_key') == 'furas' else None,
                            'checks': checks})
            OUTPUT.write_text(json.dumps(out, ensure_ascii=False), encoding='utf-8')
            print(f'checked {len(out)}/{len(rows)}', flush=True)
    OUTPUT.write_text(json.dumps(out, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    asyncio.run(main())
