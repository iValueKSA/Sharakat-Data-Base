import asyncio
import html
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx
from bs4 import BeautifulSoup


def norm(value):
    value = html.unescape(str(value or '')).casefold()
    value = re.sub(r'[^\w\u0600-\u06ff]+', '', value, flags=re.UNICODE)
    return value


def source_slug_match(row, final_url):
    expected = urlsplit(row.get('url') or '')
    final = urlsplit(final_url)
    if expected.netloc.casefold().removeprefix('www.') != final.netloc.casefold().removeprefix('www.'):
        return False
    if row.get('source_key') == 'furas':
        return unquote(final.path).rstrip('/').endswith('/opportunity/' + str(row.get('reference') or row.get('external_id') or ''))
    if row.get('source_key') == 'alahsa-opportunities':
        return unquote(final.path).rstrip('/').endswith('/opportunities/' + str(row.get('external_id') or ''))
    # AHDA, Invest Saudi, and NCP links are opportunity/article-specific paths.
    return unquote(final.path).rstrip('/') == unquote(expected.path).rstrip('/')


async def check(client, sem, row, url, label):
    async with sem:
        try:
            response = await client.get(url)
            status = response.status_code
            final = str(response.url)
            content_type = response.headers.get('content-type', '')
            identity = {'title_match': False, 'reference_match': False, 'external_id_match': False,
                        'url_slug_match': source_slug_match(row, final), 'identity_match': False,
                        'generic_or_error': False}
            if status == 200 and 'html' in content_type.casefold():
                soup = BeautifulSoup(response.text, 'html.parser')
                text = soup.get_text(' ', strip=True)
                body_norm = norm(text)
                title = norm(row.get('title'))
                reference = norm(row.get('reference'))
                external = norm(row.get('external_id'))
                identity['title_match'] = bool(title and title in body_norm)
                identity['reference_match'] = bool(reference and reference in body_norm)
                identity['external_id_match'] = bool(external and external in body_norm)
                identity['generic_or_error'] = any(norm(term) in body_norm for term in (
                    'الصفحة غير موجودة', 'page not found', '404 not found', 'record not found', 'الفرصة غير موجودة'))
                has_id = identity['reference_match'] or identity['external_id_match'] or identity['url_slug_match']
                identity['identity_match'] = bool(has_id and identity['title_match'] and not identity['generic_or_error'])
            if status == 404: cls = 'HTTP_404'
            elif status == 410: cls = 'HTTP_410'
            elif status == 403: cls = 'HTTP_403'
            elif status == 401: cls = 'LOGIN_REQUIRED'
            elif status >= 500: cls = 'SOURCE_ERROR'
            elif status == 200 and identity['identity_match']:
                cls = 'VALID_REDIRECT' if response.history else 'VALID_200'
            elif status == 200: cls = 'HTTP_200_BUT_CONTENT_MISMATCH'
            else: cls = 'SOURCE_ERROR'
            return {'label': label, 'url': url, 'class': cls, 'final_url': final, 'http_status': status,
                    'redirected': bool(response.history), 'redirect_count': len(response.history),
                    'content_type': content_type, 'bytes_read': len(response.content), 'identity': identity,
                    'error': None}
        except httpx.HTTPError as exc:
            return {'label': label, 'url': url, 'class': 'NETWORK_ERROR', 'final_url': None,
                    'http_status': None, 'identity': None, 'error': str(exc)[:300]}


async def main():
    rows = json.loads(Path('/tmp/source-link-audit.json').read_text(encoding='utf-8'))
    pending = []
    for row in rows:
        checks = row.get('checks') or []
        chosen = next((c for c in checks if c.get('label') == 'canonical_candidate'), checks[0] if checks else None)
        if chosen and chosen.get('class') not in ('VALID_200', 'VALID_REDIRECT', 'HTTP_404', 'HTTP_410'):
            pending.append((row, chosen.get('url'), chosen.get('label')))
    sem = asyncio.Semaphore(10)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/pdf,*/*;q=0.8',
        'Accept-Language': 'ar,en-US;q=0.9,en;q=0.8',
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=10), follow_redirects=True,
                                 max_redirects=8, headers=headers) as client:
        tasks = [check(client, sem, row, url, label) for row, url, label in pending]
        results = await asyncio.gather(*tasks)
    result = {int(row['source_record_id']): check for (row, _, _), check in zip(pending, results)}
    Path('/tmp/source-link-recheck.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    print(f'rechecked {len(results)} disputed links')


if __name__ == '__main__':
    asyncio.run(main())
