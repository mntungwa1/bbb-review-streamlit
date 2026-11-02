import sys
from pathlib import Path
import copy
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
class FakeClient:
    def __init__(self): self.writes = []
    def call(self, method, path, data=None):
        if method == 'GET': return None
        self.writes.append((method, path, copy.deepcopy(data)))
        return {'id': 'test'}
from streamlit.testing.v1 import AppTest
app=AppTest.from_file(str(ROOT / 'app.py'), default_timeout=15)
app.secrets['DOCUMENT_CONFIG_JSON']=__import__('json').dumps(dict(documentIds=['Main Framework'] + [f'BBB-{i:03d}' for i in range(1,22)], tools=[dict(id=f'BBB-{i:03d}', title=f'Tool {i}') for i in range(1,22)], pilots=[], **{k:'https://example.org' for k in ['annexureUrl','frameworkUrl','folderUrl','supportUrl']}))
app.session_state['role']='reviewer'
app.session_state['reviewer_email']='reviewer@example.invalid'
app.session_state['portal_client']=FakeClient()
app.run()
def check():
 assert not app.exception, [e.message for e in app.exception]
def go(page):
 app.radio[0].set_value(page).run();check()
go('21 Tools')
app.selectbox(key='tool_to_review').set_value('BBB-003').run();check()
next(b for b in app.button if b.label=='Review selected tool').click().run();check()
assert app.radio[0].value=='Submit a review'
assert app.selectbox(key='review_document').value=='BBB-003'
go('21 Tools')
app.selectbox(key='tool_to_review').set_value('BBB-017').run();check()
go('Submit a review')
assert app.selectbox(key='review_document').value=='BBB-017'
go('21 Tools')
app.button(key='review_BBB-021').click().run();check()
assert app.selectbox(key='review_document').value=='BBB-021'
app.selectbox(key='review_document').set_value('BBB-005').run();check()
go('Overview');go('Submit a review')
assert app.selectbox(key='review_document').value=='BBB-005'
app.text_input[0].set_value('Test Reviewer')
app.text_area[0].set_value('Clarify implementation')
next(b for b in app.button if b.label=='Submit review').click().run();check()
writes=app.session_state['portal_client'].writes
assert writes[-1][2]['document']=='BBB-005',writes
print('PASS: direct tool review, dropdown selection with sidebar navigation, switching tools, returning to the form, submitted document reference')

assert app.selectbox(key='review_document').value == 'BBB-005'
