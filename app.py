"""BBB Review Portal: Streamlit interface sharing the existing authenticated service."""
import base64
import importlib
import json
import re

import streamlit as st

import portal_client

# Streamlit can rerun app.py while retaining imports from the previous release.
required_paths = {'/api/tool-annexures', '/api/main-framework'}
if not required_paths.issubset(getattr(portal_client, 'ALLOWED_PATHS', ())):
    importlib.reload(portal_client)

from portal_client import PortalClient, PortalError, DEFAULT_URL, empty_batch, new_entry, has_content, submission_issues, review_csv

st.set_page_config(page_title='Build Back Better Review Portal', page_icon='🏛️', layout='wide')

def setting(key, default=''):
    try:
        return st.secrets.get(key, default)
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return default

try:
    DOCS = json.loads(setting('DOCUMENT_CONFIG_JSON', '{}'))
    DOCUMENT_IDS = DOCS['documentIds']
    TOOLS = {item['id']: item['title'] for item in DOCS['tools']}
    PILOTS = {item['id']: item for item in DOCS['pilots']}
except (ValueError, KeyError, TypeError):
    st.error('The portal document configuration is not available. Please contact the administrator.')
    st.stop()

st.markdown('''<style>
.stApp{background:#f5f7f4}h1,h2,h3{color:#173d3c}h1,h2{font-family:Georgia,serif!important}
[data-testid="stSidebar"]{background:#e8eeea}.bbb-hero{background:#173d3c;color:white;padding:32px 38px;border-radius:10px;margin:0 0 26px}.bbb-hero h1{color:white!important;font-size:44px;margin:10px 0}.bbb-hero em{color:#d9c192}.bbb-hero p{color:#d0dfd6}.bbb-eyebrow{color:#d7b77e;font-size:11px;font-weight:700;letter-spacing:.18em}button[kind="primary"]{background:#9d7841!important;border-color:#9d7841!important}
.st-key-admin_navigation button[kind="primary"]{background:#173d3c!important;border-color:#173d3c!important;color:white!important}
.st-key-admin_navigation button[kind="primary"]:hover{background:#245553!important;border-color:#245553!important}
.st-key-admin_navigation button:focus-visible{outline:2px solid #173d3c;outline-offset:3px}
</style>''', unsafe_allow_html=True)

def title(doc):
    return TOOLS.get(doc, PILOTS.get(doc, {}).get('title', 'BBB Engineering Framework' if doc == 'Main Framework' else doc))

def source_url(doc):
    return PILOTS[doc]['url'] if doc in PILOTS else DOCS['frameworkUrl']

def show_error(exc):
    st.error(str(exc))
    if not isinstance(exc, PortalError):
        return
    if exc.status == 401:
        st.info('Your session may have expired. Save any available draft backup before signing in again.')
    elif exc.status == 403 and st.session_state.get('role') == 'admin':
        st.info('The portal service denied this action. Check the administrator permissions in the portal service.')

def client():
    connection = st.session_state['portal_client']
    if type(connection).__module__ == portal_client.__name__ and type(connection) is not PortalClient:
        # Keep the authenticated HTTP session when replacing a pre-deploy client.
        connection.__class__ = PortalClient
    return connection

def review_form(document, key='single_review'):
    with st.form(key, clear_on_submit=True):
        a, b = st.columns(2)
        reviewer = a.text_input('Full name', max_chars=200)
        email = b.text_input('Email', value=st.session_state.get('reviewer_email', ''), max_chars=254)
        organization = st.text_input('Organisation', max_chars=300)
        location = st.text_input('Document version, page / clause / section', max_chars=500)
        comment = st.text_area('Review comment', max_chars=10000)
        recommendation = st.text_area('Recommended change / proposed wording', max_chars=10000)
        send = st.form_submit_button('Submit review', type='primary')
    if send:
        st.session_state['selected_review_document'] = document
        try:
            client().call('POST', '/api/reviews', dict(reviewer=reviewer, email=email.strip(), organization=organization, document=document, location=location, comment=comment, recommendation=recommendation))
            st.success('Your review was submitted successfully.')
        except PortalError as exc:
            show_error(exc)
            st.code(json.dumps(dict(reviewer=reviewer, email=email, organization=organization, document=document, location=location, comment=comment, recommendation=recommendation), indent=2), language='json')


def download_tool_annexures():
    try:
        annexures = client().call('GET', '/api/tool-annexures')
        if not annexures['accepted']:
            with st.form('tool_annexures_declaration'):
                accepted = st.checkbox(annexures['declaration'])
                submitted = st.form_submit_button('Accept declaration', type='primary')
            if submitted:
                if not accepted:
                    st.error('Tick the box to confirm the review-only declaration.')
                else:
                    client().call('POST', '/api/tool-annexures', dict(accepted=True, version=annexures['version']))
                    st.rerun()
            return
        content = base64.b64decode(annexures['content'], validate=True)
    except PortalError as exc:
        show_error(exc)
        return
    except (KeyError, TypeError, ValueError):
        st.error('The tool annexures could not be loaded. Please try refreshing the page.')
        return
    st.download_button('Download all 21 tools', content, annexures['filename'], annexures['mime'],
                       on_click='ignore', type='primary')


def select_review_document(doc, open_form=False):
    st.session_state['selected_review_document'] = doc
    st.session_state['review_document'] = doc
    if open_form:
        st.session_state['workspace_page'] = 'Submit a review'

def remember_tool():
    select_review_document(st.session_state['tool_to_review'])

def open_admin_page(page):
    st.session_state['admin_page'] = page
    st.session_state['workspace_page'] = None

def request_reviewer_access():
    with st.expander('New reviewer? Request access'):
        st.write('Use your email address and choose a password of 12–20 characters.')
        with st.form('request_reviewer_access', clear_on_submit=True):
            email = st.text_input('Email address', max_chars=254)
            password = st.text_input('New password', type='password', max_chars=20)
            submit = st.form_submit_button('Request access', type='primary', use_container_width=True)
        if submit:
            st.session_state.pop('reviewer_request_reference', None)
            email = email.strip().lower()
            if not re.fullmatch(r'\S+@\S+\.\S+', email) or not 12 <= len(password) <= 20:
                st.error('Enter a valid email address and a password of 12–20 characters.')
            else:
                portal = PortalClient(setting('PORTAL_API_URL', DEFAULT_URL), setting('PORTAL_API_TOKEN'))
                try:
                    result = portal.call('POST', '/api/reviewers', dict(action='request', email=email, password=password))
                    st.session_state['reviewer_request_reference'] = result['reference']
                except PortalError as exc:
                    st.error(str(exc))
                finally:
                    portal.session.close()
        reference = st.session_state.get('reviewer_request_reference')
        if reference:
            st.success('Send this reference from your email address to the administrator. If you already submitted a request, use your original reference. Once approved, sign in with the email and password you chose.')
            st.code(reference, language=None)


def login():
    st.markdown('<div class="bbb-hero"><div class="bbb-eyebrow">BUILD BACK BETTER · TECHNICAL REVIEW</div><h1>Stronger foundations.<br><em>Better recovery.</em></h1><p>One framework. Twenty-one tools. Three pilot studies.</p></div>', unsafe_allow_html=True)
    _, middle, _ = st.columns([1, 2, 1])
    with middle:
        st.subheader('Welcome back')
        role_label = st.selectbox('Access level', ['Reviewer / user', 'Administrator'])
        with st.form('sign_in', clear_on_submit=True):
            email = st.text_input('Reviewer email') if role_label == 'Reviewer / user' else ''
            password = st.text_input('Password', type='password')
            clicked = st.form_submit_button('Sign in', type='primary', use_container_width=True)
        if clicked:
            if not password or (role_label == 'Reviewer / user' and not email.strip()):
                st.error('Enter your sign-in details.')
                return
            portal = PortalClient(setting('PORTAL_API_URL', DEFAULT_URL), setting('PORTAL_API_TOKEN'))
            try:
                result = portal.login('admin' if role_label == 'Administrator' else 'reviewer', password, email)
                st.session_state['portal_client'] = portal
                st.session_state['role'] = result['role']
                st.session_state['reviewer_email'] = email.strip().lower()
                st.rerun()
            except PortalError as exc:
                portal.session.close()
                show_error(exc)
        if role_label == 'Reviewer / user':
            request_reviewer_access()

if 'role' not in st.session_state:
    login()
    st.stop()

# Preserve the document when its form widget is hidden on another page.
if 'review_document' in st.session_state:
    st.session_state['review_document'] = st.session_state['review_document']
    st.session_state['selected_review_document'] = st.session_state['review_document']

with st.sidebar:
    st.markdown('### BUILD BACK BETTER')
    st.caption('Technical review workspace')
    st.caption('Signed in as ' + ('Administrator' if st.session_state['role'] == 'admin' else st.session_state.get('reviewer_email', 'Reviewer')))
    pages = ['Overview', 'Main Framework', '21 Tools', *PILOTS, 'Submit a review', 'Review batch']
    is_admin = st.session_state['role'] == 'admin'
    page = st.radio('Workspace', pages, key='workspace_page')
    if is_admin:
        page = page or st.session_state.get('admin_page', 'Overview')
        with st.container(key='admin_navigation'):
            st.markdown('**Administrator controls**')
            st.button('Administration', type='primary', use_container_width=True,
                      on_click=open_admin_page, args=('Administration',))
            st.button('Reviewer access', type='primary', use_container_width=True,
                      on_click=open_admin_page, args=('Reviewer access',))
    if st.button('Sign out', use_container_width=True):
        if st.session_state.get('batch_dirty'):
            st.warning('Your latest draft has not been saved. Return to Review batch to save it or download a backup before signing out.')
        else:
            try:
                client().logout()
            except PortalError:
                pass
            st.session_state.clear()
            st.rerun()

# Administrator pages use their own authenticated endpoints.
admin_page = is_admin and page in ('Administration', 'Reviewer access')
if not admin_page and st.session_state.get('verified_page') != page:
    try:
        restored = client().call('GET', '/api/review-batch')
        if 'batch' not in st.session_state:
            st.session_state['batch'] = restored or empty_batch(DOCUMENT_IDS)
        st.session_state['verified_page'] = page
    except PortalError as exc:
        show_error(exc)
        if st.session_state.get('batch'):
            st.download_button('Download unsent draft backup', json.dumps(st.session_state['batch'], indent=2), 'BBB-draft-backup.json', 'application/json')
        st.stop()

st.markdown('<div class="bbb-eyebrow" style="color:#9d7841">CONSULTATION & TECHNICAL VALIDATION</div>', unsafe_allow_html=True)

if page == 'Overview':
    st.markdown('<div class="bbb-hero"><h1>Stronger foundations.<br><em>Better recovery.</em></h1><p>Review the engineering framework, compliance tools and pilot evidence. Submit individual comments or work through a saved review batch.</p></div>', unsafe_allow_html=True)
    a, b, c = st.columns(3)
    a.metric('Main Framework', '1')
    b.metric('Compliance tools', '21')
    c.metric('Pilot studies', '3')
    st.subheader('Two ways to contribute')
    st.write('**Submit a review:** send one comment immediately. **Review batch:** review documents one by one, save a private draft, and submit all comments together at the end.')
    st.info('These are developed documents for consultation and technical validation. Publication in this portal does not constitute formal approval.')
    st.link_button('Open peer review source folder', DOCS['folderUrl'])

elif page == 'Main Framework':
    st.title('BBB Engineering Framework')
    st.write('Review the engineering standard, its governance arrangements and implementation provisions. Reference the document version, page and clause in your comments.')
    st.link_button('Open Main Framework in Google Drive', DOCS['frameworkUrl'])
    st.link_button('Open supporting National Technical Standard', DOCS['supportUrl'])
    preview, review = st.columns([3, 2], gap='large')
    with preview:
        st.subheader('Framework preview')
        try:
            document = client().call('GET', '/api/main-framework')
            pdf = base64.b64decode(document['content'], validate=True)
            if not pdf.startswith(b'%PDF-'):
                raise ValueError('Invalid Framework PDF')
            st.pdf(pdf, height=760, key='main_framework_pdf', alt='Main Framework PDF preview')
        except PortalError as exc:
            show_error(exc)
        except (KeyError, TypeError, ValueError):
            st.error('The Main Framework preview could not be loaded. Please try refreshing the page.')
    with review:
        st.subheader('Review the Main Framework')
        review_form('Main Framework', key='main_framework_review')

elif page == '21 Tools':
    st.title('All 21 compliance tools')
    st.write('Download the consolidated annexures once. Use the BBB reference below to find each tool in the document.')
    download_tool_annexures()
    selected = st.session_state.get('selected_review_document')
    st.selectbox('Tool to review', list(TOOLS),
                 index=list(TOOLS).index(selected) if selected in TOOLS else 0,
                 format_func=lambda d: f'{d} · {title(d)}', key='tool_to_review', on_change=remember_tool)
    select_review_document(st.session_state['tool_to_review'])
    st.button('Review selected tool', on_click=select_review_document,
              args=(st.session_state['tool_to_review'], True), type='primary')
    for doc, name in TOOLS.items():
        with st.expander(f'{doc} · {name}'):
            st.button(f'Review {doc}', key='review_' + doc,
                      on_click=select_review_document, args=(doc, True))

elif page in PILOTS:
    st.title(title(page))
    st.caption('Pilot evidence · Updated August 2026')
    st.write('Review the findings, evidence, proposed interventions and implications for the framework and tools. Identify evidence gaps and practical implementation recommendations.')
    st.link_button('Open pilot report', source_url(page), type='primary')

elif page == 'Submit a review':
    st.title('Submit a technical review')
    st.write('Submit one comment immediately. To collect comments across documents, choose Review batch instead.')
    if 'review_document' not in st.session_state:
        selected = st.session_state.get('selected_review_document', DOCUMENT_IDS[0])
        st.session_state['review_document'] = selected if selected in DOCUMENT_IDS else DOCUMENT_IDS[0]
    document = st.selectbox('Document', DOCUMENT_IDS,
                            format_func=lambda d: f'{d} · {title(d)}', key='review_document')
    st.session_state['selected_review_document'] = document
    review_form(document)

elif page == 'Review batch':
    st.title('Review documents, submit once')
    st.write('Work through each document. Drafts are private and reach the administrator only after you submit the entire batch.')
    if st.session_state.get('submitted_batch'):
        st.success('Your complete review batch was submitted. Reference: ' + st.session_state['submitted_batch'])
        if st.button('Start another review batch'):
            old_profile = st.session_state['batch']['payload']
            fresh = empty_batch(DOCUMENT_IDS)
            for k in ('reviewer', 'email', 'organization'):
                fresh['payload'][k] = old_profile[k]
            st.session_state['batch'] = fresh
            st.session_state['batch_dirty'] = False
            st.session_state.pop('submitted_batch')
            st.rerun()
        st.stop()
    draft = st.session_state['batch']
    payload = draft['payload']
    def save_batch():
        try:
            client().call('PUT', '/api/review-batch', st.session_state['batch'])
            st.session_state['batch_dirty'] = False
            st.session_state['batch_save_error'] = ''
            st.session_state['batch_saved'] = True
            return True
        except PortalError as exc:
            st.session_state['batch_save_error'] = str(exc)
            st.session_state['batch_dirty'] = True
            return False
    def changed():
        st.session_state['batch']['revision'] += 1
        st.session_state['batch_dirty'] = True
        save_batch()
    def profile_changed(field, key):
        st.session_state['batch']['payload'][field] = st.session_state[key]
        changed()
    def entry_changed(doc_index, entry_id, field, key):
        for entry in st.session_state['batch']['payload']['documents'][doc_index]['entries']:
            if entry['id'] == entry_id:
                entry[field] = st.session_state[key]
        changed()
    def reviewed_changed(doc_index, key):
        st.session_state['batch']['payload']['documents'][doc_index]['reviewed'] = st.session_state[key]
        changed()
    with st.expander('Reviewer details for this batch', expanded=not bool(payload['reviewer'])):
        for field, label, maximum in [('reviewer', 'Full name', 200), ('email', 'Email', 254), ('organization', 'Organisation', 300)]:
            key = f"profile_{draft['id']}_{field}"
            st.text_input(label, value=payload[field], key=key, max_chars=maximum, on_change=profile_changed, args=(field, key))
    marked = sum(d['reviewed'] for d in payload['documents'])
    count = sum(has_content(e) for d in payload['documents'] for e in d['entries'])
    st.caption(f'{marked}/25 documents marked reviewed · {count} comments')
    if st.session_state.get('batch_save_error'):
        st.error('Draft not saved: ' + st.session_state['batch_save_error'])
    elif st.session_state.get('batch_saved'):
        st.caption('Draft saved to your account.')
    a, b = st.columns([1, 3])
    if a.button('Save draft'):
        if save_batch():
            st.success('Draft saved.')
    summary = b.toggle('Check complete batch before submission', key='batch_summary')
    st.download_button('Download a draft backup', json.dumps(draft, indent=2), 'BBB-draft-backup.json', 'application/json')
    if not summary:
        doc_id = st.selectbox('Document to review', DOCUMENT_IDS, format_func=lambda d: ('✓ ' if payload['documents'][DOCUMENT_IDS.index(d)]['reviewed'] else '') + d + ' · ' + title(d), key='batch_document')
        doc_index = DOCUMENT_IDS.index(doc_id)
        doc = payload['documents'][doc_index]
        st.subheader(title(doc_id))
        if doc_id in TOOLS:
            download_tool_annexures()
            st.caption('Locate ' + doc_id + ' in the consolidated annexures.')
        else:
            st.link_button('Open source document', source_url(doc_id), type='primary')
        for number, entry in enumerate(doc['entries'], 1):
            with st.container(border=True):
                st.markdown(f'**Comment {number}**')
                for field, label, maximum in [('location', 'Document version, page / clause / section', 500), ('comment', 'Review comment', 10000), ('recommendation', 'Recommended change / proposed wording', 10000)]:
                    key = f"entry_{draft['id']}_{entry['id']}_{field}"
                    widget = st.text_input if field == 'location' else st.text_area
                    widget(label, value=entry[field], key=key, max_chars=maximum, on_change=entry_changed, args=(doc_index, entry['id'], field, key))
                if st.button('Remove comment', key='remove_' + entry['id']):
                    doc['entries'] = [e for e in doc['entries'] if e['id'] != entry['id']]
                    changed()
                    st.rerun()
        if st.button('Add another comment', disabled=len(doc['entries']) >= 30 or sum(len(d['entries']) for d in payload['documents']) >= 200):
            doc['entries'].append(new_entry())
            changed()
            st.rerun()
        key = f"reviewed_{draft['id']}_{doc_id}"
        st.checkbox('Mark this document as reviewed' + (' — no changes proposed' if not any(has_content(e) for e in doc['entries']) else ''), value=doc['reviewed'], key=key, on_change=reviewed_changed, args=(doc_index, key))
        st.caption('Select the next document above. Your comments remain in the batch.')
    else:
        for doc in payload['documents']:
            notes = [e for e in doc['entries'] if has_content(e)]
            if not doc['reviewed'] and not notes:
                continue
            with st.expander(doc['document'] + ' · ' + title(doc['document']), expanded=True):
                if not notes:
                    st.write('Reviewed — no changes proposed.')
                for entry in notes:
                    st.markdown('**Reference:** ' + (entry['location'] or 'Reference needed'))
                    st.write(entry['comment'] or 'Comment needed')
                    st.markdown('**Recommended change:**')
                    st.write(entry['recommendation'] or 'Recommended change needed')
        if st.button('Submit entire review batch', type='primary'):
            issues = submission_issues(draft)
            if issues:
                for issue in issues:
                    st.error(issue)
            elif save_batch():
                try:
                    result = client().call('POST', '/api/review-batch', {'id': draft['id']})
                    st.session_state['submitted_batch'] = result['id']
                    st.rerun()
                except PortalError as exc:
                    show_error(exc)

elif page == 'Administration':
    st.title('Review consolidation')
    try:
        rows = client().call('GET', '/api/reviews')
    except PortalError as exc:
        show_error(exc)
        st.stop()
    st.metric('Submitted comments', len(rows))
    query = st.text_input('Filter by reviewer, document or organisation').lower()
    filtered = [r for r in rows if query in ' '.join(str(r.get(k) or '') for k in ('reviewer', 'document', 'email', 'organization')).lower()]
    st.download_button('Download complete register' if not query else 'Download filtered register', review_csv(filtered), 'BBB-review-register.csv', 'text/csv', type='primary')
    if rows:
        batch_ids = list(dict.fromkeys(r['batchId'] for r in rows if r.get('batchId')))
        if batch_ids:
            chosen = st.selectbox('Complete review batch', batch_ids, format_func=lambda bid: next(r['reviewer'] for r in rows if r.get('batchId') == bid) + ' · ' + bid[:8])
            st.download_button('Download selected batch', review_csv([r for r in rows if r.get('batchId') == chosen]), 'BBB-batch-' + chosen + '.csv', 'text/csv')
        if filtered:
            selected = st.selectbox('Individual review', filtered, format_func=lambda r: r['reviewer'] + ' · ' + r['document'] + ' · ' + r['location'])
            st.write(selected['comment'])
            st.markdown('**Recommended change:**')
            st.write(selected['recommendation'])
            st.download_button('Download individual review', review_csv([selected]), 'BBB-review-' + selected['id'].replace(':', '_') + '.csv', 'text/csv')
        st.dataframe(filtered, use_container_width=True, hide_index=True)
    else:
        st.info('No reviews have been submitted yet.')

elif page == 'Reviewer access':
    st.title('Manage reviewer accounts')
    st.write('Create individual accounts, reset passwords and enable or disable reviewer access. Account changes apply to both versions of the portal.')
    try:
        accounts = client().call('GET', '/api/reviewers')
    except PortalError as exc:
        show_error(exc)
        st.stop()
    pending_requests = {account['id']: account['email'] for account in accounts if account.get('pending')}
    reviewers = [account for account in accounts if not account.get('pending')]

    st.subheader('Pending access requests')
    message = st.session_state.pop('reviewer_access_message', None)
    if message:
        st.success(message)
    if pending_requests:
        st.write('Ask the reviewer to send the reference from their email address before granting access.')
        with st.form('approve_reviewer', clear_on_submit=True):
            request_id = st.selectbox('Pending reviewer email', list(pending_requests), format_func=pending_requests.get)
            reference = st.text_input('Request reference', max_chars=16)
            approve = st.form_submit_button('Grant access', type='primary')
        if approve:
            try:
                client().call('POST', '/api/reviewers', dict(action='approve', id=request_id, reference=reference.strip().upper()))
            except PortalError as exc:
                show_error(exc)
            else:
                st.session_state['reviewer_access_message'] = 'Reviewer approved. They can now sign in with the password they chose.'
                st.rerun()
    else:
        st.info('No pending access requests.')

    with st.expander('Add a reviewer'):
        with st.form('create_reviewer', clear_on_submit=True):
            name = st.text_input('Reviewer name', max_chars=200)
            email = st.text_input('Reviewer email', max_chars=254)
            password = st.text_input('Initial password — at least 12 characters', type='password', max_chars=128)
            create = st.form_submit_button('Create reviewer account', type='primary')
        if create:
            try:
                client().call('POST', '/api/reviewers', dict(action='create', name=name, email=email.strip().lower(), password=password))
            except PortalError as exc:
                show_error(exc)
            else:
                st.session_state['reviewer_access_message'] = 'Reviewer created. Share the sign-in details directly with the reviewer.'
                st.rerun()
    if reviewers:
        reviewer = st.selectbox('Reviewer account', reviewers, format_func=lambda r: r['name'] + ' · ' + r['email'] + (' · active' if r['enabled'] else ' · disabled'))
        with st.form('reset_reviewer', clear_on_submit=True):
            new_password = st.text_input('New password — at least 12 characters', type='password', max_chars=128)
            reset = st.form_submit_button('Reset password')
        if reset:
            try:
                client().call('POST', '/api/reviewers', dict(action='reset', id=reviewer['id'], password=new_password))
                st.success('Password changed. Previous reviewer sessions are invalid.')
            except PortalError as exc:
                show_error(exc)
        action = 'disable' if reviewer['enabled'] else 'enable'
        if st.button('Disable reviewer access' if reviewer['enabled'] else 'Enable reviewer access'):
            try:
                client().call('POST', '/api/reviewers', dict(action=action, id=reviewer['id']))
                st.rerun()
            except PortalError as exc:
                show_error(exc)
    else:
        st.info('No reviewer accounts have been created yet.')

st.divider()
st.caption('BUILD BACK BETTER · Main Framework · 21 compliance tools · 3 pilot studies')
