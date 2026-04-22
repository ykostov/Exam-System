from functools import wraps
from datetime import datetime, timezone

from bson import ObjectId
from django.contrib.auth.hashers import make_password, check_password
from django.contrib import messages
from django.shortcuts import render, redirect
from pymongo.errors import DuplicateKeyError, WriteError

from .db import (
    db,
    get_exam_statistics,
    get_pass_fail_rates,
    get_student_performance,
    get_question_difficulty,
    get_integrity_report,
    get_top_students,
)


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def login_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if 'user_id' not in request.session:
            messages.warning(request, 'Please log in first.')
            return redirect('login')
        return view(request, *args, **kwargs)
    return wrapper


def admin_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if 'user_id' not in request.session:
            return redirect('login')
        if request.session.get('role') != 'admin':
            messages.error(request, 'Admin access required.')
            return redirect('dashboard')
        return view(request, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Auth views
# ---------------------------------------------------------------------------

def home(request):
    if 'user_id' in request.session:
        if request.session.get('role') == 'admin':
            return redirect('admin_dashboard')
        return redirect('dashboard')
    return render(request, 'home.html')


def register(request):
    if request.method == 'GET':
        return render(request, 'register.html')

    username = request.POST.get('username', '').strip()
    email = request.POST.get('email', '').strip()
    password = request.POST.get('password', '')
    role = request.POST.get('role', 'student')

    if not username or not email or not password:
        messages.error(request, 'All fields are required.')
        return render(request, 'register.html')

    if role not in ('student', 'admin'):
        role = 'student'

    try:
        result = db.users.insert_one({
            'username': username,
            'email': email,
            'password_hash': make_password(password),
            'role': role,
            'created_at': datetime.now(timezone.utc),
        })
    except DuplicateKeyError:
        messages.error(request, 'Username or email already taken.')
        return render(request, 'register.html')
    except WriteError as e:
        messages.error(request, f'Validation error: {e}')
        return render(request, 'register.html')

    request.session['user_id'] = str(result.inserted_id)
    request.session['username'] = username
    request.session['role'] = role
    messages.success(request, 'Account created successfully!')
    return redirect('admin_dashboard' if role == 'admin' else 'dashboard')


def login_view(request):
    if request.method == 'GET':
        return render(request, 'login.html')

    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '')

    user = db.users.find_one({'username': username})
    if not user or not check_password(password, user['password_hash']):
        messages.error(request, 'Invalid username or password.')
        return render(request, 'login.html')

    request.session['user_id'] = str(user['_id'])
    request.session['username'] = user['username']
    request.session['role'] = user['role']

    if user['role'] == 'admin':
        return redirect('admin_dashboard')
    return redirect('dashboard')


def logout_view(request):
    request.session.flush()
    messages.info(request, 'You have been logged out.')
    return redirect('home')


# ---------------------------------------------------------------------------
# Student views
# ---------------------------------------------------------------------------

@login_required
def dashboard(request):
    user_id = request.session['user_id']

    # Active exams the student hasn't submitted yet
    active_exams = list(db.exams.find({'is_active': True}))

    submitted_exam_ids = [
        a['exam_id']
        for a in db.attempts.find(
            {'user_id': ObjectId(user_id), 'is_submitted': True},
            {'exam_id': 1}
        )
    ]

    # Separate into available and completed
    available = [e for e in active_exams if e['_id'] not in submitted_exam_ids]
    completed = [e for e in active_exams if e['_id'] in submitted_exam_ids]

    # Check for in-progress attempts
    in_progress = db.attempts.find_one({
        'user_id': ObjectId(user_id),
        'is_submitted': False
    })

    performance = get_student_performance(user_id)

    return render(request, 'student/dashboard.html', {
        'available_exams': available,
        'completed_exams': completed,
        'in_progress': in_progress,
        'performance': performance,
    })


@login_required
def start_exam(request, exam_id):
    if request.method != 'POST':
        return redirect('dashboard')

    user_id = ObjectId(request.session['user_id'])
    eid = ObjectId(exam_id)

    exam = db.exams.find_one({'_id': eid, 'is_active': True})
    if not exam:
        messages.error(request, 'Exam not found or inactive.')
        return redirect('dashboard')

    # Integrity: check for existing unsubmitted attempt (resume it)
    existing = db.attempts.find_one({
        'user_id': user_id, 'exam_id': eid, 'is_submitted': False
    })
    if existing:
        return redirect('take_exam', attempt_id=str(existing['_id']))

    # Integrity: prevent retakes
    already_done = db.attempts.find_one({
        'user_id': user_id, 'exam_id': eid, 'is_submitted': True
    })
    if already_done:
        messages.info(request, 'You have already completed this exam.')
        return redirect('exam_result', attempt_id=str(already_done['_id']))

    # Create new attempt
    result = db.attempts.insert_one({
        'user_id': user_id,
        'exam_id': eid,
        'started_at': datetime.now(timezone.utc),
        'finished_at': None,
        'answers': [],
        'score': None,
        'is_submitted': False,
        'time_exceeded': False,
    })
    return redirect('take_exam', attempt_id=str(result.inserted_id))


@login_required
def take_exam(request, attempt_id):
    user_id = ObjectId(request.session['user_id'])
    attempt = db.attempts.find_one({
        '_id': ObjectId(attempt_id), 'user_id': user_id
    })
    if not attempt:
        messages.error(request, 'Attempt not found.')
        return redirect('dashboard')

    if attempt['is_submitted']:
        return redirect('exam_result', attempt_id=attempt_id)

    exam = db.exams.find_one({'_id': attempt['exam_id']})
    questions = list(db.questions.find({'exam_id': exam['_id']}))

    # Calculate remaining time
    now = datetime.now(timezone.utc)
    started = attempt['started_at']
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    elapsed = (now - started).total_seconds()
    allowed = exam['duration_minutes'] * 60
    remaining = max(0, int(allowed - elapsed))

    # Auto-submit if time is up
    if remaining <= 0:
        _auto_submit(attempt, exam, questions)
        return redirect('exam_result', attempt_id=attempt_id)

    return render(request, 'student/take_exam.html', {
        'attempt': attempt,
        'exam': exam,
        'questions': questions,
        'remaining_seconds': remaining,
    })


@login_required
def submit_exam(request, attempt_id):
    if request.method != 'POST':
        return redirect('dashboard')

    user_id = ObjectId(request.session['user_id'])
    attempt = db.attempts.find_one({
        '_id': ObjectId(attempt_id),
        'user_id': user_id,
        'is_submitted': False,
    })
    if not attempt:
        messages.error(request, 'Invalid attempt.')
        return redirect('dashboard')

    exam = db.exams.find_one({'_id': attempt['exam_id']})
    questions = list(db.questions.find({'exam_id': exam['_id']}))

    # Collect answers from POST
    answers = []
    for q in questions:
        key = f'question_{q["_id"]}'
        val = request.POST.get(key)
        if val is not None:
            answers.append({
                'question_id': q['_id'],
                'selected_option': int(val),
            })

    # Integrity: check time
    now = datetime.now(timezone.utc)
    started = attempt['started_at']
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    elapsed = (now - started).total_seconds()
    allowed = exam['duration_minutes'] * 60
    time_exceeded = elapsed > (allowed + 5)  # 5-second grace

    # Calculate score
    score = _calculate_score(answers, questions)

    db.attempts.update_one({'_id': attempt['_id']}, {'$set': {
        'answers': answers,
        'finished_at': now,
        'score': score,
        'is_submitted': True,
        'time_exceeded': time_exceeded,
    }})

    return redirect('exam_result', attempt_id=attempt_id)


@login_required
def exam_result(request, attempt_id):
    user_id = ObjectId(request.session['user_id'])
    attempt = db.attempts.find_one({
        '_id': ObjectId(attempt_id), 'user_id': user_id, 'is_submitted': True
    })
    if not attempt:
        messages.error(request, 'Result not found.')
        return redirect('dashboard')

    exam = db.exams.find_one({'_id': attempt['exam_id']})
    questions = list(db.questions.find({'exam_id': exam['_id']}))

    # Build answer map for the template
    answer_map = {
        str(a['question_id']): a['selected_option']
        for a in attempt.get('answers', [])
    }

    passed = attempt['score'] is not None and attempt['score'] >= exam['passing_score']

    return render(request, 'student/result.html', {
        'attempt': attempt,
        'exam': exam,
        'questions': questions,
        'answer_map': answer_map,
        'passed': passed,
    })


# ---------------------------------------------------------------------------
# Admin views
# ---------------------------------------------------------------------------

@admin_required
def admin_dashboard(request):
    stats = get_exam_statistics()
    exams = list(db.exams.find().sort('created_at', -1))
    total_students = db.users.count_documents({'role': 'student'})
    total_attempts = db.attempts.count_documents({'is_submitted': True})

    avg_by_exam = {str(s['_id']): s.get('avg_score') for s in stats}
    for exam in exams:
        exam['avg_score'] = avg_by_exam.get(str(exam['_id']))

    return render(request, 'admin/dashboard.html', {
        'stats': stats,
        'exams': exams,
        'total_students': total_students,
        'total_attempts': total_attempts,
    })


@admin_required
def create_exam(request):
    if request.method == 'GET':
        return render(request, 'admin/create_exam.html')

    title = request.POST.get('title', '').strip()
    description = request.POST.get('description', '').strip()
    duration = request.POST.get('duration_minutes', '30')
    passing = request.POST.get('passing_score', '60')

    if not title:
        messages.error(request, 'Title is required.')
        return render(request, 'admin/create_exam.html')

    try:
        exam_result = db.exams.insert_one({
            'title': title,
            'description': description,
            'duration_minutes': int(duration),
            'passing_score': int(passing),
            'is_active': False,
            'created_by': ObjectId(request.session['user_id']),
            'created_at': datetime.now(timezone.utc),
        })
    except (WriteError, ValueError) as e:
        messages.error(request, f'Error creating exam: {e}')
        return render(request, 'admin/create_exam.html')

    exam_id = exam_result.inserted_id

    # Parse questions from the dynamic form
    idx = 0
    while True:
        text = request.POST.get(f'q_{idx}_text', '').strip()
        if not text:
            break

        options = []
        opt_idx = 0
        while True:
            opt = request.POST.get(f'q_{idx}_opt_{opt_idx}', '').strip()
            if not opt:
                break
            options.append(opt)
            opt_idx += 1

        correct = request.POST.get(f'q_{idx}_correct', '0')
        points = request.POST.get(f'q_{idx}_points', '10')

        if len(options) >= 2:
            try:
                db.questions.insert_one({
                    'exam_id': exam_id,
                    'text': text,
                    'options': options,
                    'correct_option': int(correct),
                    'points': int(points),
                })
            except WriteError as e:
                messages.warning(request, f'Question "{text[:30]}..." skipped: {e}')
        idx += 1

    messages.success(request, f'Exam "{title}" created with {idx} question(s).')
    return redirect('exam_detail', exam_id=str(exam_id))


@admin_required
def exam_detail(request, exam_id):
    exam = db.exams.find_one({'_id': ObjectId(exam_id)})
    if not exam:
        messages.error(request, 'Exam not found.')
        return redirect('admin_dashboard')

    questions = list(db.questions.find({'exam_id': exam['_id']}))
    difficulty = get_question_difficulty(exam_id)

    return render(request, 'admin/exam_detail.html', {
        'exam': exam,
        'questions': questions,
        'difficulty': difficulty,
    })


@admin_required
def toggle_exam(request, exam_id):
    if request.method == 'POST':
        exam = db.exams.find_one({'_id': ObjectId(exam_id)})
        if exam:
            db.exams.update_one(
                {'_id': exam['_id']},
                {'$set': {'is_active': not exam['is_active']}}
            )
    return redirect('exam_detail', exam_id=exam_id)


@admin_required
def reports(request):
    integrity = get_integrity_report()
    for row in integrity:
        row['status'] = row.pop('_id')

    return render(request, 'admin/reports.html', {
        'exam_stats': get_exam_statistics(),
        'pass_fail': get_pass_fail_rates(),
        'integrity': integrity,
        'top_students': get_top_students(),
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _calculate_score(answers, questions):
    """Calculate percentage score."""
    if not questions:
        return 0
    q_map = {q['_id']: q for q in questions}
    total_points = sum(q['points'] for q in questions)
    earned = 0
    for ans in answers:
        q = q_map.get(ans['question_id'])
        if q and ans['selected_option'] == q['correct_option']:
            earned += q['points']
    return int(round(earned / total_points * 100)) if total_points else 0


def _auto_submit(attempt, exam, questions):
    """Auto-submit when time runs out."""
    db.attempts.update_one({'_id': attempt['_id']}, {'$set': {
        'finished_at': datetime.now(timezone.utc),
        'score': _calculate_score(attempt.get('answers', []), questions),
        'is_submitted': True,
        'time_exceeded': True,
    }})
