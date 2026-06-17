from flask import Flask, request, jsonify, make_response, send_from_directory
from flask_cors import CORS
import datetime
import json
import os
import bcrypt
from database import init_db, create_user, get_user_by_email, get_user_by_id, create_session, validate_session, delete_session, delete_user_sessions, update_user_name, update_user_password
from database import get_user_progress, update_user_progress, create_test_session, get_test_session, get_user_test_sessions
from database import record_test_answer, get_test_answers, update_test_session
from qbank_data import load_questions, get_subject_counts, get_system_counts, generate_test, get_question_by_id
from nbme120 import generate_nbme120, generate_test1
from free120_questions import FREE120_QUESTIONS

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
    
    # Don't include correct answer in question payload
    safe_question = {
        'id': question['id'],
        'text': question['text'],
        'options': question['options'],
        'subject': question['subject'],
        'system': question.get('system', ''),
        'image_url': question.get('image_url', ''),
        'imageUrls': question.get('imageUrls', []),
        'image_assets': question.get('image_assets', []),
        'tables': question.get('tables', []),
        'option_table': question.get('option_table'),
        'explanation': question.get('explanation', ''),
        'hint': question.get('hint', '')
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
            'block': idx // 20 + 1 if test_session['mode'] in ('nbme120', 'free120') else None,
            'blockQuestion': idx % 20 + 1 if test_session['mode'] in ('nbme120', 'free120') else None,
            'questionId': question_id,
            'subject': question.get('subject', ''),
            'system': question.get('system', ''),
            'text': question.get('text', ''),
            'options': question.get('options', []),
            'optionTable': question.get('option_table'),
            'tables': question.get('tables', []),
            'imageUrls': question.get('imageUrls', []) or ([question['image_url']] if question.get('image_url') else []),
            'selectedOption': selected,
            'correctAnswer': question.get('correct_answer'),
            'isCorrect': answer.get('is_correct') if answer else None,
            'explanation': question.get('explanation', ''),
        })
    return jsonify({
        'testSessionId': test_id,
        'mode': test_session['mode'],
        'totalQuestions': len(question_ids),
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
        block_mode = session['mode'] in ('free120', 'nbme120', 'test1')
        resume_block = (next_index // 20) + 1 if block_mode else None
        if block_mode:
            exam_param = '&exam=free120' if session['mode'] == 'free120' else ('&exam=test1' if session['mode'] == 'test1' else '')
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
