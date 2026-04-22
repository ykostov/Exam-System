"""
Management command to populate the database with sample data for testing.

Usage:  python manage.py seed_data
        python manage.py seed_data --clear   (drop all collections first)
"""

from datetime import datetime, timedelta, timezone

from bson import ObjectId
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand

from exams.db import db, setup_collections


class Command(BaseCommand):
    help = 'Seed MongoDB with sample exams, questions, users, and attempts'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear', action='store_true',
            help='Drop all collections before seeding',
        )

    def handle(self, *args, **options):
        if options['clear']:
            for name in ('users', 'exams', 'questions', 'attempts'):
                db.drop_collection(name)
            self.stdout.write('Dropped all collections.')

        setup_collections()
        self.stdout.write('Collections set up with schema validation.')

        now = datetime.now(timezone.utc)

        # ---- Users -------------------------------------------------------
        admin = db.users.find_one({'username': 'admin'})
        if not admin:
            admin_id = db.users.insert_one({
                'username': 'admin',
                'email': 'admin@exam.com',
                'password_hash': make_password('admin123'),
                'role': 'admin',
                'created_at': now,
            }).inserted_id
        else:
            admin_id = admin['_id']

        students = []
        for i, (name, email) in enumerate([
            ('ivan', 'ivan@student.com'),
            ('maria', 'maria@student.com'),
            ('georgi', 'georgi@student.com'),
            ('elena', 'elena@student.com'),
            ('dimitar', 'dimitar@student.com'),
        ]):
            existing = db.users.find_one({'username': name})
            if existing:
                students.append(existing['_id'])
            else:
                sid = db.users.insert_one({
                    'username': name,
                    'email': email,
                    'password_hash': make_password('pass123'),
                    'role': 'student',
                    'created_at': now - timedelta(days=10 - i),
                }).inserted_id
                students.append(sid)

        self.stdout.write(f'Users ready: 1 admin + {len(students)} students')

        # ---- Exams --------------------------------------------------------
        exams_data = [
            {
                'title': 'Python Fundamentals',
                'description': 'Basic Python concepts — variables, loops, functions.',
                'duration_minutes': 15,
                'passing_score': 60,
                'questions': [
                    ('What is the output of print(type(42))?',
                     ["<class 'int'>", "<class 'str'>", "<class 'float'>", "<class 'bool'>"], 0, 10),
                    ('Which keyword defines a function in Python?',
                     ['func', 'def', 'function', 'lambda'], 1, 10),
                    ('What does len([1, 2, 3]) return?',
                     ['1', '2', '3', '4'], 2, 10),
                    ('Which of these is a mutable type?',
                     ['str', 'tuple', 'list', 'int'], 2, 10),
                    ('How do you start a comment in Python?',
                     ['//', '#', '/*', '--'], 1, 10),
                ],
            },
            {
                'title': 'Database Concepts',
                'description': 'SQL, NoSQL, indexing, and normalization.',
                'duration_minutes': 20,
                'passing_score': 50,
                'questions': [
                    ('Which is a NoSQL database?',
                     ['PostgreSQL', 'MySQL', 'MongoDB', 'Oracle'], 2, 10),
                    ('What does ACID stand for?',
                     ['Atomicity Consistency Isolation Durability',
                      'Advanced Computed Index Design',
                      'Aggregated Conditional Index Data',
                      'Atomic Computed Isolation Design'], 0, 10),
                    ('What is an index used for?',
                     ['Encryption', 'Faster queries', 'Data backup', 'Schema design'], 1, 10),
                    ('What is normalization?',
                     ['Adding redundancy', 'Reducing redundancy',
                      'Encrypting data', 'Compressing data'], 1, 10),
                ],
            },
            {
                'title': 'Web Development Basics',
                'description': 'HTML, CSS, HTTP, and REST.',
                'duration_minutes': 10,
                'passing_score': 70,
                'questions': [
                    ('What does HTTP stand for?',
                     ['HyperText Transfer Protocol', 'High Tech Transfer Protocol',
                      'HyperText Transmission Path', 'Home Tool Transfer Protocol'], 0, 10),
                    ('Which HTTP method is idempotent?',
                     ['POST', 'GET', 'PATCH', 'None of these'], 1, 10),
                    ('What does CSS stand for?',
                     ['Computer Style Sheets', 'Cascading Style Sheets',
                      'Creative Style System', 'Cascading System Styles'], 1, 10),
                ],
            },
        ]

        import random
        random.seed(42)

        for edata in exams_data:
            existing_exam = db.exams.find_one({'title': edata['title']})
            if existing_exam:
                self.stdout.write(f'  Exam "{edata["title"]}" already exists, skipping.')
                continue

            exam_id = db.exams.insert_one({
                'title': edata['title'],
                'description': edata['description'],
                'duration_minutes': edata['duration_minutes'],
                'passing_score': edata['passing_score'],
                'is_active': True,
                'created_by': admin_id,
                'created_at': now - timedelta(days=7),
            }).inserted_id

            q_ids = []
            for text, options, correct, points in edata['questions']:
                qid = db.questions.insert_one({
                    'exam_id': exam_id,
                    'text': text,
                    'options': options,
                    'correct_option': correct,
                    'points': points,
                }).inserted_id
                q_ids.append((qid, correct, len(options)))

            self.stdout.write(
                f'  Exam "{edata["title"]}" — {len(q_ids)} questions'
            )

            # Generate sample attempts for each student
            for sid in students:
                # ~80% chance the student took this exam
                if random.random() > 0.8:
                    continue

                answers = []
                for qid, correct_opt, num_opts in q_ids:
                    # ~60% chance of answering correctly
                    if random.random() < 0.6:
                        selected = correct_opt
                    else:
                        selected = random.randint(0, num_opts - 1)
                    answers.append({
                        'question_id': qid,
                        'selected_option': selected,
                    })

                # Calculate score
                total_pts = len(q_ids) * 10
                earned = sum(
                    10 for a, (qid, correct_opt, _) in zip(answers, q_ids)
                    if a['selected_option'] == correct_opt
                )
                score = int(round(earned / total_pts * 100))

                duration_s = random.randint(
                    edata['duration_minutes'] * 10,
                    edata['duration_minutes'] * 55,
                )
                started = now - timedelta(
                    days=random.randint(1, 5),
                    hours=random.randint(0, 12),
                )
                time_exceeded = random.random() < 0.05  # 5% chance

                db.attempts.insert_one({
                    'user_id': sid,
                    'exam_id': exam_id,
                    'started_at': started,
                    'finished_at': started + timedelta(seconds=duration_s),
                    'answers': answers,
                    'score': score,
                    'is_submitted': True,
                    'time_exceeded': time_exceeded,
                })

        total = db.attempts.count_documents({'is_submitted': True})
        self.stdout.write(self.style.SUCCESS(
            f'\nDone! {total} submitted attempts in the database.'
        ))
