"""Server-side client for the existing BBB portal. No account data is cached globally."""
import csv
import io
import uuid
import requests

DEFAULT_URL = 'https://bbb-review-portal-2026.dingaan-mahl-3739.chatgpt.site'

class PortalError(Exception):
    def __init__(self, message, status=0):
        super().__init__(message)
        self.status = status

class PortalClient:
    def __init__(self, base_url=DEFAULT_URL, api_token=''):
        self.base_url = base_url.rstrip('/')
        if not self.base_url.startswith('https://'):
            raise ValueError('The portal URL must use HTTPS.')
        self.session = requests.Session()
        self.session.headers.update({'Origin': self.base_url, 'Accept': 'application/json'})
        if api_token:
            self.session.headers['OAI-Sites-Authorization'] = 'Bearer ' + api_token

    def call(self, method, path, data=None):
        if path not in {'/api/session', '/api/reviews', '/api/reviewers', '/api/review-batch'}:
            raise PortalError('Unknown portal operation.')
        try:
            response = self.session.request(method, self.base_url + path, json=data, timeout=(15, 45), allow_redirects=False)
        except requests.RequestException as exc:
            raise PortalError('The portal service could not be reached. Your unsent draft is still on this page.') from exc
        try:
            result = response.json()
        except ValueError as exc:
            raise PortalError('The portal connection is unavailable. Please contact the administrator.', response.status_code) from exc
        if not response.ok:
            message = result.get('error', 'The request could not be completed.') if isinstance(result, dict) else 'The request could not be completed.'
            raise PortalError(message, response.status_code)
        return result

    def login(self, role, password, email=''):
        return self.call('POST', '/api/session', {'role': role, 'email': email.strip().lower(), 'password': password})

    def logout(self):
        try:
            self.call('DELETE', '/api/session')
        finally:
            self.session.cookies.clear()
            self.session.close()

def new_entry():
    return {'id': str(uuid.uuid4()), 'location': '', 'comment': '', 'recommendation': ''}

def empty_batch(document_ids):
    return {'id': str(uuid.uuid4()), 'revision': 1, 'payload': {'reviewer': '', 'email': '', 'organization': '', 'documents': [
        {'document': doc, 'reviewed': False, 'entries': [new_entry()]} for doc in document_ids
    ]}}

def has_content(entry):
    return any(entry.get(k, '').strip() for k in ('location', 'comment', 'recommendation'))

def submission_issues(draft):
    p = draft['payload']
    issues = []
    if not p['reviewer'].strip() or not p['organization'].strip() or '@' not in p['email']:
        issues.append('Complete your name, email and organisation.')
    count = 0
    for doc in p['documents']:
        entries = [e for e in doc['entries'] if has_content(e)]
        count += len(entries) + int(doc['reviewed'] and not entries)
        for entry in entries:
            if not all(entry[k].strip() for k in ('location', 'comment', 'recommendation')):
                issues.append(doc['document'] + ': complete the reference, comment and recommended change, or remove the unfinished comment.')
    if not count:
        issues.append('Add a comment or mark at least one document as reviewed.')
    return list(dict.fromkeys(issues))

def review_csv(rows):
    columns = ['id', 'reviewer', 'email', 'organization', 'document', 'location', 'comment', 'recommendation', 'created', 'batchId']
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=columns, extrasaction='ignore')
    writer.writeheader()
    for row in rows:
        safe = {}
        for key in columns:
            value = str(row.get(key) or '')
            safe[key] = "'" + value if value.startswith(('=', '+', '-', '@', '\t', '\r')) else value
        writer.writerow(safe)
    return ('\ufeff' + out.getvalue()).encode('utf-8')
