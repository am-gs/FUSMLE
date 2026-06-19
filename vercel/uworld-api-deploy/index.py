from flask import Flask, request, jsonify, make_response, send_from_directory
from flask_cors import CORS
import datetime
import json
import os
import re
import statistics
import bcrypt
from database import init_db, create_user, get_user_by_email, get_user_by_id, create_session, validate_session, delete_session, delete_user_sessions, update_user_name, update_user_password
from database import get_user_progress, update_user_progress, create_test_session, get_test_session, get_user_test_sessions
from database import record_test_answer, get_test_answers, update_test_session
from qbank_data import load_questions, get_subject_counts, get_system_counts, generate_test, get_question_by_id
from nbme120 import generate_nbme120, generate_test1, generate_test2
from test2_render_flags import TEST2_RENDER_FLAGS
from free120_questions import FREE120_QUESTIONS

_ENHANCED_EXPLANATIONS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nbme120_enhanced_explanations.json')
try:
    with open(_ENHANCED_EXPLANATIONS_PATH, encoding='utf-8') as _fh:
        _ENHANCED_EXPLANATIONS = json.load(_fh).get('records', {})
except (OSError, ValueError):
    _ENHANCED_EXPLANATIONS = {}


def get_enhanced_explanation(question_id):
    """Return the SOTA enhanced explanation for an NBME 120 sample question, if present."""
    if not question_id:
        return None
    match = re.match(r'nbme120_q0*(\d+)$', str(question_id))
    if not match:
        return None
    record = _ENHANCED_EXPLANATIONS.get(str(int(match.group(1))))
    if not record or not record.get('sections'):
        return None
    return {
        'source': 'NBME 120 April sample — enhanced breakdown',
        'sections': record['sections'],
        'answerLetterConflict': record.get('answerLetterConflict', False),
        'enhancedAnswerLetter': record.get('correctAnswerLetter'),
        'qbankCorrectLetter': record.get('qbankCorrectLetter'),
    }


# ---------------------------------------------------------------------------
# OpenEvidence-sourced Test 2 explanations + per-question psychometrics.
_OE_EXPLANATIONS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test2_openevidence_explanations.json')
try:
    with open(_OE_EXPLANATIONS_PATH, encoding='utf-8') as _fh:
        _OE_EXPLANATIONS = json.load(_fh)
except (OSError, ValueError):
    _OE_EXPLANATIONS = {}


def get_openevidence_report(question_id):
    """Return the OpenEvidence deep-dive report + exam metrics for a Test 2 qid."""
    if not question_id:
        return None
    record = _OE_EXPLANATIONS.get(str(question_id))
    if not record or not record.get('narrativeHtml'):
        return None
    return {
        'source': 'OpenEvidence — exam deep dive',
        'oeNum': record.get('oeNum'),
        'title': record.get('title'),
        'narrativeHtml': record['narrativeHtml'],
        'metrics': record.get('metrics', {}),
    }


def _pct_correct_from_pvalue(pvalue):
    """NBME p-value is the proportion answering correctly. Return integer percent."""
    try:
        return int(round(float(pvalue) * 100))
    except (TypeError, ValueError):
        return None


def _performance_badge(row, oe, median_time, fast_threshold, slow_threshold):
    """Build a motivational, performance-aware badge from result + OE psychometrics."""
    is_correct = _is_correct_value(row.get('isCorrect'))
    is_wrong = _is_wrong_value(row.get('isCorrect'))
    if not is_correct and not is_wrong:
        return None
    metrics = (oe or {}).get('metrics') or {}
    diff = (metrics.get('difficulty') or row.get('difficulty') or '').lower()
    pct = _pct_correct_from_pvalue(metrics.get('pValue'))
    is_hard = ('hard' in diff) or (pct is not None and pct <= 45)
    is_easy = ('easy' in diff) or (pct is not None and pct >= 75)
    t = _coerce_number(row.get('timeSpent'))
    fast = t is not None and median_time and t <= fast_threshold
    slow = t is not None and median_time and t >= slow_threshold
    pct_phrase = f"only ~{pct}% of test-takers get this right" if (pct is not None and pct <= 55) else (
        f"~{pct}% get this right" if pct is not None else None)

    if is_correct and is_hard:
        return {'tone': 'celebrate', 'emoji': '🌟', 'title': 'Clutch — hard item nailed',
                'text': 'You locked in a genuinely tough question' + (f' — {pct_phrase}.' if pct_phrase else '.')
                        + (' Fast, too. ⚡' if fast else '')}
    if is_correct and is_easy and fast:
        return {'tone': 'speed', 'emoji': '⚡', 'title': 'Fast & accurate',
                'text': 'Quick, confident, and correct on a high-yield gimme. That is exactly the pace you want on the easy ones to bank time for the hard ones.'}
    if is_correct and fast:
        return {'tone': 'speed', 'emoji': '⚡', 'title': 'Efficient',
                'text': 'Answered well under your median time and got it right — efficient decisioning.'}
    if is_correct:
        return {'tone': 'solid', 'emoji': '✅', 'title': 'Solid',
                'text': 'Correct.' + (f' {pct_phrase[0].upper()+pct_phrase[1:]}.' if pct_phrase else '')}
    if is_wrong and is_easy and fast:
        return {'tone': 'careless', 'emoji': '⏱️', 'title': 'Slow down — avoidable miss',
                'text': 'Quick miss on an item most people get. This is a reread/anchoring slip, not a knowledge gap — the cheapest points to win back.'}
    if is_wrong and is_hard:
        return {'tone': 'tough', 'emoji': '💪', 'title': 'Hard item — expected stretch',
                'text': 'A legitimately difficult question' + (f' ({pct_phrase}).' if pct_phrase else '.')
                        + ' Study the pattern below; this is high-leverage learning, not a red flag.'}
    if is_wrong and slow:
        return {'tone': 'pace', 'emoji': '🐢', 'title': 'Long deliberation, still missed',
                'text': 'You spent well over your median here and still missed it — a signal to flag this concept for focused review rather than grinding in the moment.'}
    return {'tone': 'review', 'emoji': '📌', 'title': 'Review target',
            'text': 'Missed — walk the reasoning chain below so the next encounter is automatic.'}

app = Flask(__name__)
CORS(app, supports_credentials=False, origins=["*"])



# Secret key for JWT
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Initialize database
init_db()

def get_current_session():
    auth_header = request.headers.get('Authorization', '')
    header_token = auth_header.split(' ', 1)[1].strip() if auth_header.startswith('Bearer ') else ''
    cookie_token = request.cookies.get('token', '')
    checked = set()
    for token in (header_token, cookie_token):
        if not token or token in checked:
            continue
        checked.add(token)
        session = validate_session(token)
        if session:
            return token, session
    return '', None

# Helper function to get user from token
def get_current_user():
    _, session = get_current_session()
    if not session:
        return None
    return get_user_by_id(session['user_id'])

def public_user(user):
    name = user.get('name') or ''
    return {
        'id': user['id'],
        'email': user['email'],
        'name': name,
        'firstName': name.split()[0] if name else '',
        'lastName': ' '.join(name.split()[1:]) if name and ' ' in name else ''
    }

def normalize_email(email):
    return (email or '').strip().lower()

def auth_response(user, status=200):
    token = create_session(user['id'])
    response = make_response(jsonify({'token': token, 'user': public_user(user)}), status)
    response.set_cookie('token', token, httponly=True, samesite='Lax', secure=True, max_age=604800)
    return response

# Auth endpoints
@app.route('/api/auth', methods=['POST'])
@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    data = request.get_json(silent=True) or {}
    email = normalize_email(data.get('email'))
    password = data.get('password') or ''
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
    user = get_user_by_email(email)
    if not user or not bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
        return jsonify({'error': 'Invalid email or password'}), 401
    return auth_response(user)

@app.route('/api/register', methods=['POST'])
def auth_register():
    data = request.get_json(silent=True) or {}
    email = normalize_email(data.get('email'))
    password = data.get('password') or ''
    name = (data.get('name') or data.get('firstName') or '').strip()
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400
    if get_user_by_email(email):
        return jsonify({'error': 'Account already exists'}), 409
    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    user_id = create_user(email, password_hash, name)
    user = get_user_by_id(user_id)
    return auth_response(user, status=201)

@app.route('/api/session', methods=['GET'])
def auth_session():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    return jsonify({
        'user': {
            'id': user['id'],
            'email': user['email'],
            'name': user.get('name') or ''
        }
    })

@app.route('/api/logout', methods=['POST'])
def auth_logout():
    token, _ = get_current_session()
    if not token:
        auth_header = request.headers.get('Authorization', '')
        token = auth_header.split(' ', 1)[1].strip() if auth_header.startswith('Bearer ') else ''
        token = token or request.cookies.get('token', '')
    if token:
        try:
            delete_session(token)
        except Exception:
            pass
    response = make_response(jsonify({'ok': True}))
    response.set_cookie('token', '', expires=0, httponly=True, samesite='Lax', secure=True)
    return response

@app.route('/api/account/profile', methods=['POST'])
def account_update_profile():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Name is required'}), 400
    if len(name) > 100:
        return jsonify({'error': 'Name must be 100 characters or fewer'}), 400
    update_user_name(user['id'], name)
    updated = get_user_by_id(user['id'])
    return jsonify({'user': public_user(updated)})

@app.route('/api/account/password', methods=['POST'])
def account_change_password():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json(silent=True) or {}
    current_password = data.get('currentPassword') or ''
    new_password = data.get('newPassword') or ''
    if not current_password or not new_password:
        return jsonify({'error': 'Current and new password are required'}), 400
    if len(new_password) < 8:
        return jsonify({'error': 'New password must be at least 8 characters'}), 400
    if not bcrypt.checkpw(current_password.encode('utf-8'), user['password_hash'].encode('utf-8')):
        return jsonify({'error': 'Current password is incorrect'}), 401
    new_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    update_user_password(user['id'], new_hash)
    # Security: revoke every other session for this account so a stolen token
    # cannot survive a password rotation. Keep the caller's current session.
    current_token, _ = get_current_session()
    try:
        delete_user_sessions(user['id'], keep_session_id=current_token or None)
    except Exception:
        pass
    return jsonify({'ok': True})

@app.route('/api/forgot-password', methods=['POST'])
def auth_forgot_password():
    data = request.get_json(silent=True) or {}
    email = data.get('email')
    
    if not email:
        return jsonify({'error': 'Email required'}), 400
    
    # In a real app, send reset email. For now, just return success.
    return jsonify({'message': 'If an account exists with this email, you will receive a password reset link.'})

# QBank endpoints
@app.route('/api/qbank/info', methods=['GET'])
def qbank_info():
    # Return subject and system counts
    subject_counts = get_subject_counts()
    system_counts = get_system_counts()
    
    available_forms = ['NBME 27', 'NBME 28', 'NBME 29', 'Form 30', 'Form 31',
                       'NBME 120', 'Step 1 Sample Exam']
    
    # Total questions from qbank_data
    questions = load_questions()
    
    return jsonify({
        'totalQuestions': len(questions),
        'subjects': subject_counts,
        'systems': system_counts,
        'availableForms': available_forms,
        'free120': {
            'sourceForm': 'free120_2021',
            'totalQuestions': len(FREE120_QUESTIONS),
            'printedPdfQuestions': len(FREE120_QUESTIONS)
        }
    })

@app.route('/api/qbank/generate-test', methods=['POST'])
def qbank_generate_test():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json(silent=True) or {}
    mode = data.get('mode') or data.get('testMode', 'tutor')
    total_questions = data.get('totalQuestions') or data.get('questionCount', 40)
    try:
        total_questions = int(total_questions)
    except (TypeError, ValueError):
        return jsonify({'error': 'totalQuestions must be an integer'}), 400
    subjects = data.get('subjects', [])
    systems = data.get('systems', [])
    
    # Generate test with question IDs
    question_ids = generate_test(total_questions, subjects, systems)
    
    # Create test session in DB
    test_session_id = create_test_session(
        user_id=user['id'],
        mode=mode,
        question_ids=question_ids,
        total_questions=total_questions
    )
    
    return jsonify({
        'testSessionId': test_session_id,
        'mode': mode,
        'totalQuestions': total_questions,
        'questionIds': question_ids
    })

# NBME 120 endpoint
@app.route('/api/qbank/generate-nbme120', methods=['POST'])
def qbank_generate_nbme120():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    result = generate_nbme120()
    all_ids = result['questionIds']
    
    test_session_id = create_test_session(
        user_id=user['id'],
        mode='nbme120',
        question_ids=all_ids,
        total_questions=120,
        block_info=result['blocks']
    )
    
    result['testSessionId'] = test_session_id
    return jsonify(result)

@app.route('/api/qbank/generate-test1', methods=['POST'])
def qbank_generate_test1():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    result = generate_test1()
    all_ids = result['questionIds']

    test_session_id = create_test_session(
        user_id=user['id'],
        mode='test1',
        question_ids=all_ids,
        total_questions=len(all_ids),
        block_info=result['blocks']
    )

    result['testSessionId'] = test_session_id
    return jsonify(result)


@app.route('/api/qbank/generate-test2', methods=['POST'])
def qbank_generate_test2():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    result = generate_test2()
    all_ids = result['questionIds']

    test_session_id = create_test_session(
        user_id=user['id'],
        mode='test2',
        question_ids=all_ids,
        total_questions=len(all_ids),
        block_info=result['blocks']
    )

    result['testSessionId'] = test_session_id
    return jsonify(result)

@app.route('/api/qbank/generate-free120', methods=['POST'])
def qbank_generate_free120():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    question_ids = [question['id'] for question in FREE120_QUESTIONS]
    test_session_id = create_test_session(
        user_id=user['id'],
        mode='free120',
        question_ids=question_ids,
        total_questions=len(question_ids),
        block_info=[]
    )
    return jsonify({
        'format': 'free120',
        'testSessionId': test_session_id,
        'totalQuestions': len(question_ids),
        'questionIds': question_ids,
        'sourceForm': 'free120_2021'
    })

@app.route('/api/qbank/test/<int:test_id>/question/<int:question_idx>', methods=['GET'])
def qbank_get_question(test_id, question_idx):
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    # Verify test belongs to user
    test_session = get_test_session(test_id)
    if not test_session or test_session['user_id'] != user['id']:
        return jsonify({'error': 'Test not found'}), 404
    
    question_ids = json.loads(test_session['question_ids'])
    total = len(question_ids)
    
    if question_idx < 0 or question_idx >= total:
        return jsonify({'error': 'Question index out of range'}), 400
    
    question_id = question_ids[question_idx]
    question = get_question_by_id(question_id)
    
    if not question:
        return jsonify({'error': 'Question not found'}), 404
    
    rendering_flag = None
    image_url = question.get('image_url', '')
    image_urls = question.get('imageUrls', [])
    image_assets = question.get('image_assets', [])
    if test_session.get('mode') == 'test2' and question_id in TEST2_RENDER_FLAGS:
        rendering_flag = TEST2_RENDER_FLAGS[question_id]
        if rendering_flag.get('suppressImages'):
            image_url = ''
            image_urls = []
            image_assets = []

    # Don't include correct answer in question payload
    safe_question = {
        'id': question['id'],
        'text': question['text'],
        'options': question['options'],
        'subject': question['subject'],
        'system': question.get('system', ''),
        'image_url': image_url,
        'imageUrls': image_urls,
        'image_assets': image_assets,
        'tables': question.get('tables', []),
        'option_table': question.get('option_table'),
        'explanation': question.get('explanation', ''),
        'hint': question.get('hint', ''),
        'rendering_flag': rendering_flag,
    }
    
    return jsonify({
        'index': question_idx,
        'total': total,
        'question': safe_question
    })

@app.route('/api/qbank/test/<int:test_id>/submit', methods=['POST'])
def qbank_submit_answer(test_id):
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json(silent=True) or {}
    question_id = data.get('questionId')
    selected_option = data.get('selectedOption')
    time_spent = data.get('timeSpent', 0)
    
    if not question_id or selected_option is None:
        return jsonify({'error': 'Missing questionId or selectedOption'}), 400

    test_session = get_test_session(test_id)
    if not test_session or test_session['user_id'] != user['id']:
        return jsonify({'error': 'Test not found'}), 404

    session_question_ids = json.loads(test_session['question_ids'])
    if question_id not in session_question_ids:
        return jsonify({'error': 'Question does not belong to this test session'}), 400
    
    # Get question
    question = get_question_by_id(question_id)
    if not question:
        return jsonify({'error': 'Question not found'}), 404
    
    # Check answer
    correct_answer = question.get('correct_answer')
    is_correct = selected_option == correct_answer
    
    # Update user progress
    update_user_progress(
        user_id=user['id'],
        question_id=question_id,
        is_correct=is_correct,
        time_spent=time_spent,
        subject=question['subject'],
        system=question.get('system', '')
    )
    record_test_answer(
        test_session_id=test_id,
        user_id=user['id'],
        question_id=question_id,
        selected_option=selected_option,
        is_correct=is_correct,
        time_spent=time_spent,
    )
    current_question = session_question_ids.index(question_id) + 1
    completed = len(get_test_answers(test_id)) >= len(session_question_ids)
    update_test_session(test_id, current_question=current_question, completed=completed)
    
    return jsonify({
        'correct': is_correct,
        'correctAnswer': correct_answer,
        'explanation': question.get('explanation', ''),
        'isCorrect': is_correct
    })

@app.route('/api/qbank/test/<int:test_id>/state', methods=['GET'])
def qbank_test_state(test_id):
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    test_session = get_test_session(test_id)
    if not test_session or test_session['user_id'] != user['id']:
        return jsonify({'error': 'Test not found'}), 404
    question_ids = json.loads(test_session['question_ids'])
    answers = get_test_answers(test_id)
    return jsonify({
        'testSessionId': test_id,
        'mode': test_session['mode'],
        'questionIds': question_ids,
        'totalQuestions': test_session['total_questions'],
        'currentQuestion': test_session.get('current_question') or 0,
        'completed': bool(test_session.get('completed')),
        'blocks': json.loads(test_session['block_info']) if test_session.get('block_info') else [],
        'answers': answers,
    })

def _safe_pct(numerator, denominator):
    return round((numerator / denominator) * 100, 1) if denominator else 0.0

def _stem_word_count(text):
    return len((text or '').replace('\n', ' ').split())

def _is_correct_value(value):
    return value in (True, 1, '1')

def _is_wrong_value(value):
    return value in (False, 0, '0')

def _coerce_number(value):
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None

def _stem_bucket(word_count):
    if word_count < 40:
        return 'short'
    if word_count < 90:
        return 'medium'
    if word_count < 160:
        return 'long'
    return 'very_long'

def _simplify_explanation(raw_text):
    text = (raw_text or '').replace('<br><br>', '\n\n').replace('<br>', '\n')
    text = re.sub(r'^\s*©.*$', '', text, flags=re.MULTILINE)
    text = text.replace('**', '')
    text = re.sub(r'\n{3,}', '\n\n', text).strip()

    split_markers = [
        'Incorrect Answers:',
        'Why the Other Choices Are Wrong',
        'Distractors:',
        'Educational Objective:',
        'Key Takeaway',
        'Video Review:',
    ]
    core = text
    for marker in split_markers:
        if marker in core:
            core = core.split(marker, 1)[0].strip()

    parts = [part.strip() for part in re.split(r'\n\s*\n', core) if part.strip()]
    if len(parts) > 2:
        core = '\n\n'.join(parts[:2]).strip()
    else:
        core = core.strip()
    summary = parts[0] if parts else (text or 'No explanation available.')
    summary = summary.split('. ', 1)[0].strip()
    if summary and not summary.endswith('.'):
        summary += '.'
    return {
        'summary': summary or 'No explanation available.',
        'full': text or 'No explanation available.',
        'core': core or text or 'No explanation available.',
    }

def _insight_tone(is_correct, time_spent, median_time):
    if _is_correct_value(is_correct) and time_spent is not None and time_spent <= max(12, int(median_time * 0.45)):
        return {
            'label': 'Clean hit',
            'style': 'green',
            'message': 'You recognized the pattern quickly and closed without drama.',
        }
    if _is_correct_value(is_correct) and time_spent is not None and time_spent >= max(90, int(median_time * 1.6)):
        return {
            'label': 'Got it, but had to wrestle it',
            'style': 'blue',
            'message': 'Correct answer, but it took extra time. Good to review so this becomes cheaper next time.',
        }
    if _is_wrong_value(is_correct) and time_spent is not None and time_spent <= max(12, int(median_time * 0.45)):
        return {
            'label': 'Likely rushed',
            'style': 'red',
            'message': 'This looks more like a speed miss than a total knowledge miss.',
        }
    if _is_wrong_value(is_correct) and time_spent is not None and time_spent >= max(90, int(median_time * 1.6)):
        return {
            'label': 'You were in the neighborhood',
            'style': 'amber',
            'message': 'Long dwell time usually means partial recognition. The last step in the reasoning chain is what needs tightening.',
        }
    if is_correct is None:
        return {
            'label': 'Left on the table',
            'style': 'slate',
            'message': 'No submitted answer here, so this is a pure opportunity-cost item.',
        }
    if _is_correct_value(is_correct):
        return {
            'label': 'Solid keep',
            'style': 'green',
            'message': 'Correct. Keep the pattern, not just the letter.',
        }
    return {
        'label': 'Teachable miss',
        'style': 'amber',
        'message': 'This is worth a quick cleanup pass rather than a dramatic content overhaul.',
    }

def _coaching_note(row, explanation, median_time):
    system = row.get('system') or 'this domain'
    subject = row.get('subject') or system
    time_spent = row.get('timeSpent') or 0
    if row.get('isCorrect') is None:
        return f"Next time, make sure {subject} items do not become omissions. Even a best-guess answer is better than donating the point to the void."
    if _is_wrong_value(row.get('isCorrect')) and time_spent <= max(12, int(median_time * 0.45)):
        return f"Slow down just enough to name the discriminator before clicking. {system} misses here look more impulsive than blind."
    if _is_wrong_value(row.get('isCorrect')) and time_spent >= max(90, int(median_time * 1.6)):
        return f"You were close. Rebuild the reasoning chain for {system} questions from the last line backward until the answer feels inevitable."
    if _is_correct_value(row.get('isCorrect')) and time_spent >= max(90, int(median_time * 1.6)):
        return f"Correct, but expensive. Review this one so the same {system} pattern costs less time on the next pass."
    return f"Keep the core rule from this {subject} item in active memory; the pattern is more valuable than memorizing the exact stem."

def _build_review_summary(mode, rows):
    answered_rows = [row for row in rows if row.get('isCorrect') is not None]
    correct_rows = [row for row in rows if _is_correct_value(row.get('isCorrect'))]
    wrong_rows = [row for row in rows if _is_wrong_value(row.get('isCorrect'))]
    total = len(rows)
    answered = len(answered_rows)
    correct = len(correct_rows)
    wrong = len(wrong_rows)
    omitted = total - answered
    score = round((correct / answered) * 100) if answered else 0
    completion = _safe_pct(answered, total)

    time_values = []
    for row in answered_rows:
        coerced = _coerce_number(row.get('timeSpent'))
        if coerced is not None:
            row['timeSpent'] = int(round(coerced))
            time_values.append(row['timeSpent'])
    median_time = int(statistics.median(time_values)) if time_values else 0
    fast_threshold = max(12, int(median_time * 0.45)) if median_time else 12
    slow_threshold = max(90, int(median_time * 1.6)) if median_time else 90

    def aggregate(key, limit=5):
        buckets = {}
        for row in answered_rows:
            name = row.get(key) or 'Unlabeled'
            bucket = buckets.setdefault(name, {'name': name, 'correct': 0, 'answered': 0})
            bucket['answered'] += 1
            if _is_correct_value(row.get('isCorrect')):
                bucket['correct'] += 1
        values = []
        for bucket in buckets.values():
            bucket['missed'] = bucket['answered'] - bucket['correct']
            bucket['accuracy'] = _safe_pct(bucket['correct'], bucket['answered'])
            values.append(bucket)
        strong = [item for item in sorted(values, key=lambda item: (-item['accuracy'], -item['answered'], item['name'])) if item['correct'] > 0][:limit]
        focus_candidates = [item for item in values if item['missed'] > 0]
        focus = sorted(focus_candidates or values, key=lambda item: (item['accuracy'], -item['missed'], -item['answered'], item['name']))[:limit]
        return strong, focus

    strong_systems, focus_systems = aggregate('system')
    strong_subjects, focus_subjects = aggregate('subject')

    # Difficulty calibration: accuracy by labeled question difficulty.
    difficulty_breakdown = []
    for level in ('easy', 'medium', 'hard'):
        sub = [r for r in answered_rows if (r.get('difficulty') or 'unknown') == level]
        if sub:
            corr = sum(1 for r in sub if _is_correct_value(r.get('isCorrect')))
            difficulty_breakdown.append({
                'level': level,
                'correct': corr,
                'answered': len(sub),
                'accuracy': _safe_pct(corr, len(sub)),
            })
    # High-yield vs standard performance.
    hy_rows = [r for r in answered_rows if r.get('highYield')]
    hy_correct = sum(1 for r in hy_rows if _is_correct_value(r.get('isCorrect')))
    high_yield_stat = {
        'answered': len(hy_rows),
        'correct': hy_correct,
        'accuracy': _safe_pct(hy_correct, len(hy_rows)),
    }

    word_buckets = {
        'short': {'label': 'Short stems', 'correct': 0, 'answered': 0},
        'medium': {'label': 'Medium stems', 'correct': 0, 'answered': 0},
        'long': {'label': 'Long stems', 'correct': 0, 'answered': 0},
        'very_long': {'label': 'Very long stems', 'correct': 0, 'answered': 0},
    }
    media = {'answered': 0, 'correct': 0}
    text_only = {'answered': 0, 'correct': 0}
    blocks = {}
    near_misses = []
    rapid_misses = []
    celebrations = []
    badge_counts = {}

    for row in rows:
        wc = _stem_word_count(row.get('text', ''))
        bucket_key = _stem_bucket(wc)
        row['wordCount'] = wc
        row['wordBucket'] = bucket_key
        row['isMediaQuestion'] = bool(row.get('imageUrls') or row.get('tables') or row.get('optionTable'))
        explanation = _simplify_explanation(row.get('explanation', ''))
        row['explanationSummary'] = explanation['summary']
        row['explanationCore'] = explanation['core']
        row['explanationFull'] = explanation['full']
        row['insightTone'] = _insight_tone(row.get('isCorrect'), row.get('timeSpent'), median_time)
        row['coachingNote'] = _coaching_note(row, explanation, median_time)
        badge = _performance_badge(row, row.get('oeReport'), median_time, fast_threshold, slow_threshold)
        row['performanceBadge'] = badge
        if badge:
            badge_counts[badge['tone']] = badge_counts.get(badge['tone'], 0) + 1
            if badge['tone'] == 'celebrate':
                celebrations.append({
                    'questionId': row.get('questionId'),
                    'block': row.get('block'),
                    'blockQuestion': row.get('blockQuestion'),
                    'system': row.get('system') or 'Unlabeled',
                    'title': (row.get('oeReport') or {}).get('title') or row.get('subject') or 'Hard item',
                    'pctCorrect': _pct_correct_from_pvalue(((row.get('oeReport') or {}).get('metrics') or {}).get('pValue')),
                })

        if row.get('isCorrect') is not None:
            word_buckets[bucket_key]['answered'] += 1
            if _is_correct_value(row.get('isCorrect')):
                word_buckets[bucket_key]['correct'] += 1
            media_bucket = media if row['isMediaQuestion'] else text_only
            media_bucket['answered'] += 1
            if _is_correct_value(row.get('isCorrect')):
                media_bucket['correct'] += 1

        if row.get('block'):
            block = blocks.setdefault(row['block'], {'block': row['block'], 'correct': 0, 'answered': 0, 'total': 0})
            block['total'] += 1
            if row.get('isCorrect') is not None:
                block['answered'] += 1
                if _is_correct_value(row.get('isCorrect')):
                    block['correct'] += 1

        if _is_wrong_value(row.get('isCorrect')) and row.get('timeSpent') is not None:
            candidate = {
                'questionId': row.get('questionId'),
                'system': row.get('system') or 'Unlabeled',
                'subject': row.get('subject') or 'Unlabeled',
                'timeSpent': row.get('timeSpent'),
                'block': row.get('block'),
                'prompt': row.get('text', '')[:180].strip(),
                'correctAnswer': row.get('correctAnswer'),
                'selectedOption': row.get('selectedOption'),
            }
            if row['timeSpent'] >= slow_threshold:
                near_misses.append(candidate)
            if row['timeSpent'] <= fast_threshold:
                rapid_misses.append(candidate)

    block_stats = []
    for block in sorted(blocks.values(), key=lambda item: item['block']):
        block['accuracy'] = _safe_pct(block['correct'], block['answered'])
        block_stats.append(block)

    strongest_block = max(block_stats, key=lambda item: item['accuracy'], default=None)
    weakest_block = min(block_stats, key=lambda item: item['accuracy'], default=None)

    media['accuracy'] = _safe_pct(media['correct'], media['answered'])
    text_only['accuracy'] = _safe_pct(text_only['correct'], text_only['answered'])
    word_stats = []
    for key in ('short', 'medium', 'long', 'very_long'):
        bucket = word_buckets[key]
        if bucket['answered']:
            word_stats.append({
                'bucket': bucket['label'],
                'correct': bucket['correct'],
                'answered': bucket['answered'],
                'accuracy': _safe_pct(bucket['correct'], bucket['answered']),
            })

    if block_stats:
        block_accuracies = [block['accuracy'] for block in block_stats]
        spread = max(block_accuracies) - min(block_accuracies)
        stability = round(max(0.0, 100 - spread), 1)
        first_half = block_accuracies[:max(1, len(block_accuracies)//2)]
        second_half = block_accuracies[max(1, len(block_accuracies)//2):] or block_accuracies[-1:]
        endurance_delta = statistics.mean(second_half) - statistics.mean(first_half)
        endurance = round(max(0.0, min(100.0, 70 + endurance_delta)), 1)
    else:
        stability = 0.0
        endurance = 0.0

    readiness = round(min(100.0, 0.55 * score + 0.2 * completion + 0.15 * stability + 0.1 * max(media['accuracy'], text_only['accuracy'])), 1)

    priority_buckets = {}
    for row in answered_rows:
        key = f"{row.get('system') or 'Unlabeled'}__{row.get('subject') or 'Unlabeled'}"
        bucket = priority_buckets.setdefault(key, {
            'system': row.get('system') or 'Unlabeled',
            'subject': row.get('subject') or 'Unlabeled',
            'correct': 0,
            'answered': 0,
        })
        bucket['answered'] += 1
        if _is_correct_value(row.get('isCorrect')):
            bucket['correct'] += 1
    study_priorities = []
    for bucket in priority_buckets.values():
        bucket['missed'] = bucket['answered'] - bucket['correct']
        bucket['accuracy'] = _safe_pct(bucket['correct'], bucket['answered'])
        study_priorities.append(bucket)
    actionable_priorities = [item for item in study_priorities if item['missed'] > 0]
    study_priorities = sorted(actionable_priorities or study_priorities, key=lambda item: (item['accuracy'], -item['missed'], -item['answered'], item['system']))[:8]

    exam_label = {
        'free120': 'Sample exam review',
        'nbme120': 'NBME 120 review',
        'test1': 'Test 1 review',
        'test2': 'Test 2 review',
    }.get(mode, 'Exam review')
    tone = 'encouraging' if score >= 65 else ('mixed' if score >= 50 else 'urgent')
    conversational_headline = (
        f"{exam_label}: {correct} right out of {answered} answered ({score}%). "
        + (
            "There is real traction here, but the misses are concentrated enough to be fixable."
            if tone == 'encouraging' else
            "Some pieces are working, but the weak spots are still expensive."
            if tone == 'mixed' else
            "The misses cluster into a repairable set of patterns, which is better than chaos."
        )
    )

    return {
        'answered': answered,
        'correct': correct,
        'wrong': wrong,
        'omitted': omitted,
        'score': score,
        'completion': completion,
        'readiness': readiness,
        'stability': stability,
        'endurance': endurance,
        'medianTime': median_time,
        'fastThreshold': fast_threshold,
        'slowThreshold': slow_threshold,
        'media': media,
        'textOnly': text_only,
        'blockStats': block_stats,
        'strongestBlock': strongest_block,
        'weakestBlock': weakest_block,
        'strongSystems': strong_systems,
        'focusSystems': focus_systems,
        'strongSubjects': strong_subjects,
        'focusSubjects': focus_subjects,
        'difficultyBreakdown': difficulty_breakdown,
        'highYield': high_yield_stat,
        'wordStats': word_stats,
        'studyPriorities': study_priorities,
        'nearMisses': near_misses[:8],
        'rapidMisses': rapid_misses[:8],
        'celebrations': sorted(celebrations, key=lambda c: (c['pctCorrect'] if c['pctCorrect'] is not None else 999))[:8],
        'badgeCounts': badge_counts,
        'conversationalHeadline': conversational_headline,
        'tone': tone,
    }

@app.route('/api/qbank/test/<int:test_id>/review', methods=['GET'])
def qbank_test_review(test_id):
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    test_session = get_test_session(test_id)
    if not test_session or test_session['user_id'] != user['id']:
        return jsonify({'error': 'Test not found'}), 404
    question_ids = json.loads(test_session['question_ids'])
    answers_by_question = {answer['question_id']: answer for answer in get_test_answers(test_id)}
    rows = []
    for idx, question_id in enumerate(question_ids):
        question = get_question_by_id(question_id)
        if not question:
            continue
        answer = answers_by_question.get(str(question_id)) or {}
        selected = answer.get('selected_option')
        rows.append({
            'index': idx,
            'block': idx // 20 + 1 if test_session['mode'] in ('nbme120', 'free120', 'test1', 'test2') else None,
            'blockQuestion': idx % 20 + 1 if test_session['mode'] in ('nbme120', 'free120', 'test1', 'test2') else None,
            'questionId': question_id,
            'subject': question.get('subject', ''),
            'system': question.get('system', '') or question.get('organ_system', ''),
            'discipline': question.get('discipline', ''),
            'difficulty': question.get('difficulty_band') or question.get('difficulty') or 'unknown',
            'highYield': bool(question.get('high_yield')),
            'text': question.get('text', ''),
            'options': question.get('options', []),
            'optionTable': question.get('option_table'),
            'tables': question.get('tables', []),
            'imageUrls': question.get('imageUrls', []) or ([question['image_url']] if question.get('image_url') else []),
            'selectedOption': selected,
            'correctAnswer': question.get('correct_answer'),
            'isCorrect': answer.get('is_correct') if answer else None,
            'timeSpent': answer.get('time_spent') if answer else None,
            'answeredAt': answer.get('answered_at') if answer else None,
            'explanation': question.get('explanation', ''),
        })
        rows[-1]['enhancedExplanation'] = get_enhanced_explanation(question_id)
        rows[-1]['oeReport'] = get_openevidence_report(question_id) if test_session['mode'] == 'test2' else None
    summary = _build_review_summary(test_session['mode'], rows)
    return jsonify({
        'testSessionId': test_id,
        'mode': test_session['mode'],
        'totalQuestions': len(question_ids),
        'summary': summary,
        'rows': rows,
    })

@app.route('/api/qbank/history', methods=['GET'])
def qbank_history():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    labels = {
        'free120': 'Step 1 Sample Exam',
        'nbme120': 'NBME 120 Simulation',
        'test1': 'Test 1',
        'test2': 'Test 2',
        'timed': 'Custom Test (Timed)',
        'tutor': 'Custom Test (Tutor)',
    }
    sessions = get_user_test_sessions(user['id'])
    history = []
    for session in sessions:
        answers = get_test_answers(session['id'])
        answered = len(answers)
        if answered == 0:
            continue  # only surface exams that were actually taken
        correct = sum(1 for a in answers if a.get('is_correct') in (True, 1, '1'))
        total = session.get('total_questions') or 0
        question_ids = json.loads(session['question_ids'])
        answered_ids = {str(a.get('question_id')) for a in answers}
        next_index = next((idx for idx, qid in enumerate(question_ids) if str(qid) not in answered_ids), len(question_ids) - 1)
        completed = bool(session.get('completed')) or answered >= total
        block_mode = session['mode'] in ('free120', 'nbme120', 'test1', 'test2')
        resume_block = (next_index // 20) + 1 if block_mode else None
        if block_mode:
            exam_param = '&exam=free120' if session['mode'] == 'free120' else ('&exam=test2' if session['mode'] == 'test2' else ('&exam=test1' if session['mode'] == 'test1' else ''))
            resume_url = f"qbank.html?session={session['id']}&block={resume_block}&mode=timed&time=30&question={next_index}{exam_param}"
            resume_label = f"Resume Block {resume_block}"
        else:
            resume_url = f"qbank.html?session={session['id']}&mode={session['mode']}&question={next_index}"
            resume_label = 'Resume Test'
        history.append({
            'id': session['id'],
            'mode': session['mode'],
            'label': labels.get(session['mode'], 'Practice Test'),
            'totalQuestions': total,
            'answered': answered,
            'correct': correct,
            'score': round(correct / answered * 100) if answered else 0,
            'completed': completed,
            'currentQuestion': session.get('current_question') or 0,
            'nextQuestionIndex': next_index,
            'resumeBlock': resume_block,
            'resumeUrl': None if completed else resume_url,
            'resumeLabel': None if completed else resume_label,
            'createdAt': session.get('created_at'),
            'completedAt': session.get('completed_at'),
        })
    return jsonify({'sessions': history})

# Stats endpoints
@app.route('/api/stats/overview', methods=['GET'])
def stats_overview():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    progress = get_user_progress(user['id'])
    
    # Calculate stats
    total_answered = len(progress)
    correct_answers = sum(1 for p in progress if p['is_correct'])
    accuracy = (correct_answers / total_answered * 100) if total_answered > 0 else 0
    
    # Time spent
    total_time_spent = sum(p['time_spent'] for p in progress)
    
    # Subjects accuracy
    subject_stats = {}
    for p in progress:
        subject = p['subject']
        if subject not in subject_stats:
            subject_stats[subject] = {'answered': 0, 'correct': 0}
        subject_stats[subject]['answered'] += 1
        if p['is_correct']:
            subject_stats[subject]['correct'] += 1
    
    for subject, stat in subject_stats.items():
        stat['accuracy'] = (stat['correct'] / stat['answered'] * 100) if stat['answered'] > 0 else 0
    
    return jsonify({
        'totalAnswered': total_answered,
        'correctAnswers': correct_answers,
        'accuracy': round(accuracy, 1),
        'totalTimeSpent': total_time_spent,
        'subjectStats': subject_stats,
        'recentActivity': progress[:10]
    })

# Image serving endpoint
@app.route('/api/images/<form>/<filename>')
def serve_image(form, filename):
    return send_from_directory(os.path.join(os.path.dirname(__file__), 'images_webp', form), filename)

@app.route('/api/qbank/browse', methods=['GET'])
def qbank_browse():
    """Read-only qbank browser feed: filter/search the curated pool with
    metadata, answer key, explanation, and image URLs for viewing."""
    questions = load_questions()
    form = (request.args.get('form') or '').strip()
    system = (request.args.get('system') or '').strip()
    difficulty = (request.args.get('difficulty') or '').strip()
    has_image = request.args.get('has_image')
    search = (request.args.get('q') or '').strip().lower()
    try:
        limit = min(200, max(1, int(request.args.get('limit', 50))))
        offset = max(0, int(request.args.get('offset', 0)))
    except ValueError:
        limit, offset = 50, 0

    def sys_of(q):
        return q.get('system') or q.get('organ_system') or ''

    def matches(q):
        if form and q.get('form') != form:
            return False
        if system and sys_of(q) != system:
            return False
        if difficulty and (q.get('difficulty_band') or q.get('difficulty')) != difficulty:
            return False
        if has_image in ('1', 'true', 'yes') and not q.get('imageUrls'):
            return False
        if has_image in ('0', 'false', 'no') and q.get('imageUrls'):
            return False
        if search:
            hay = (q.get('text', '') + ' ' + q.get('id', '') + ' ' + sys_of(q)).lower()
            if search not in hay:
                return False
        return True

    filtered = [q for q in questions if matches(q)]
    total = len(filtered)
    page = filtered[offset:offset + limit]

    def shape(q):
        opts = q.get('options', []) or []
        ca = q.get('correct_answer')
        correct_letter = correct_text = None
        if isinstance(ca, int) and 1 <= ca <= len(opts):
            correct_letter = opts[ca - 1].get('letter') or chr(64 + ca)
            correct_text = opts[ca - 1].get('text')
        return {
            'id': q.get('id'),
            'form': q.get('form'),
            'system': sys_of(q),
            'subject': q.get('subject'),
            'discipline': q.get('discipline'),
            'difficulty': q.get('difficulty_band') or q.get('difficulty') or 'unknown',
            'highYield': bool(q.get('high_yield')),
            'stem': q.get('text', ''),
            'options': opts,
            'optionTable': q.get('option_table'),
            'correctAnswer': ca if isinstance(ca, int) else None,
            'correctLetter': correct_letter,
            'correctText': correct_text,
            'explanation': q.get('explanation', ''),
            'imageUrls': q.get('imageUrls', []) or ([q['image_url']] if q.get('image_url') else []),
            'hasImage': bool(q.get('imageUrls')),
            'hasTable': bool(q.get('tables') or q.get('option_table')),
            'sourcePdfPage': q.get('source_pdf_page'),
            'pdfVerified': bool(q.get('pdf_verified')),
            'examReady': bool(q.get('exam_ready', True)),
        }

    forms = sorted({q.get('form') for q in questions if q.get('form')})
    systems = sorted({sys_of(q) for q in questions if sys_of(q)})
    return jsonify({
        'total': total,
        'limit': limit,
        'offset': offset,
        'items': [shape(q) for q in page],
        'facets': {'forms': forms, 'systems': systems, 'difficulties': ['easy', 'medium', 'hard', 'unknown']},
    })


@app.route('/api/images_crop/<filename>')
def serve_cropped_image(filename):
    response = send_from_directory(os.path.join(os.path.dirname(__file__), 'images_crop'), filename, mimetype='image/webp')
    response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    return response

@app.route('/api/images_pages/<form>/<filename>')
def serve_page_image(form, filename):
    response = send_from_directory(os.path.join(os.path.dirname(__file__), 'images_pages', form), filename, mimetype='image/webp')
    response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    return response

# Health check
@app.route('/')
def health():
    return jsonify({'status': 'ok', 'service': 'uworld-api'})

# Vercel requires `handler` variable
handler = app
