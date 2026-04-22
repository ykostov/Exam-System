"""
MongoDB database layer for the Online Examination System.

Demonstrates three key database concepts:
  1. SCHEMA CONSTRAINTS  — $jsonSchema validators on every collection
  2. CONDITIONAL QUERIES — $cond, $switch, $ifNull in aggregation stages
  3. AGGREGATION          — $group, $lookup, $unwind, $addFields, $project
"""

from django.conf import settings
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------
_client = MongoClient(settings.MONGO_URI)
db = _client[settings.MONGO_DB_NAME]


# ---------------------------------------------------------------------------
# 1. SCHEMA CONSTRAINTS — enforced by MongoDB on every insert / update
# ---------------------------------------------------------------------------

def setup_collections():
    """Create collections with JSON Schema validation.

    MongoDB rejects documents that violate these constraints, guaranteeing
    data integrity at the database level — no application-level checks needed.
    """
    existing = db.list_collection_names()

    # ---- users -----------------------------------------------------------
    if 'users' not in existing:
        db.create_collection('users', validator={
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["username", "email", "password_hash", "role",
                             "created_at"],
                "properties": {
                    "username": {
                        "bsonType": "string",
                        "minLength": 3,
                        "maxLength": 50,
                        "description": "Unique username, 3-50 chars"
                    },
                    "email": {
                        "bsonType": "string",
                        "pattern": r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$",
                        "description": "Valid e-mail address"
                    },
                    "password_hash": {
                        "bsonType": "string",
                        "description": "Hashed password (Django PBKDF2)"
                    },
                    "role": {
                        "enum": ["student", "admin"],
                        "description": "Account role"
                    },
                    "created_at": {
                        "bsonType": "date"
                    }
                }
            }
        })
        db.users.create_index("username", unique=True)
        db.users.create_index("email", unique=True)

    # ---- exams -----------------------------------------------------------
    if 'exams' not in existing:
        db.create_collection('exams', validator={
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["title", "created_by", "duration_minutes",
                             "passing_score", "is_active", "created_at"],
                "properties": {
                    "title": {
                        "bsonType": "string",
                        "minLength": 1,
                        "maxLength": 200
                    },
                    "description": {
                        "bsonType": "string"
                    },
                    "duration_minutes": {
                        "bsonType": "int",
                        "minimum": 1,
                        "maximum": 480,
                        "description": "Duration 1-480 minutes"
                    },
                    "passing_score": {
                        "bsonType": "int",
                        "minimum": 0,
                        "maximum": 100,
                        "description": "Minimum % to pass"
                    },
                    "is_active": {
                        "bsonType": "bool"
                    },
                    "created_by": {
                        "bsonType": "objectId"
                    },
                    "created_at": {
                        "bsonType": "date"
                    }
                }
            }
        })

    # ---- questions -------------------------------------------------------
    if 'questions' not in existing:
        db.create_collection('questions', validator={
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["exam_id", "text", "options",
                             "correct_option", "points"],
                "properties": {
                    "exam_id": {
                        "bsonType": "objectId"
                    },
                    "text": {
                        "bsonType": "string",
                        "minLength": 1
                    },
                    "options": {
                        "bsonType": "array",
                        "minItems": 2,
                        "maxItems": 6,
                        "items": {"bsonType": "string"},
                        "description": "2-6 answer options"
                    },
                    "correct_option": {
                        "bsonType": "int",
                        "minimum": 0,
                        "description": "0-based index of correct answer"
                    },
                    "points": {
                        "bsonType": "int",
                        "minimum": 1,
                        "maximum": 100
                    }
                }
            }
        })
        db.questions.create_index("exam_id")

    # ---- attempts --------------------------------------------------------
    if 'attempts' not in existing:
        db.create_collection('attempts', validator={
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["user_id", "exam_id", "started_at",
                             "is_submitted"],
                "properties": {
                    "user_id": {
                        "bsonType": "objectId"
                    },
                    "exam_id": {
                        "bsonType": "objectId"
                    },
                    "started_at": {
                        "bsonType": "date"
                    },
                    "finished_at": {
                        "bsonType": ["date", "null"]
                    },
                    "answers": {
                        "bsonType": "array",
                        "items": {
                            "bsonType": "object",
                            "required": ["question_id", "selected_option"],
                            "properties": {
                                "question_id": {"bsonType": "objectId"},
                                "selected_option": {"bsonType": "int"}
                            }
                        }
                    },
                    "score": {
                        "bsonType": ["int", "null"],
                        "minimum": 0
                    },
                    "is_submitted": {
                        "bsonType": "bool"
                    },
                    "time_exceeded": {
                        "bsonType": "bool"
                    }
                }
            }
        })
        db.attempts.create_index([("user_id", 1), ("exam_id", 1)])


# ---------------------------------------------------------------------------
# 2. CONDITIONAL QUERIES + 3. AGGREGATION PIPELINES
# ---------------------------------------------------------------------------

def get_exam_statistics():
    """AGGREGATION: per-exam statistics — avg / min / max scores, attempt count.

    Pipeline stages: $match -> $group -> $lookup -> $unwind -> $project -> $sort
    """
    pipeline = [
        {"$match": {"is_submitted": True}},
        {"$group": {
            "_id": "$exam_id",
            "total_attempts": {"$sum": 1},
            "avg_score": {"$avg": "$score"},
            "max_score": {"$max": "$score"},
            "min_score": {"$min": "$score"},
        }},
        # Join with exams collection to get title
        {"$lookup": {
            "from": "exams",
            "localField": "_id",
            "foreignField": "_id",
            "as": "exam_info"
        }},
        {"$unwind": "$exam_info"},
        {"$project": {
            "exam_title": "$exam_info.title",
            "passing_score": "$exam_info.passing_score",
            "total_attempts": 1,
            "avg_score": {"$round": ["$avg_score", 1]},
            "max_score": 1,
            "min_score": 1,
        }},
        {"$sort": {"total_attempts": -1}}
    ]
    return list(db.attempts.aggregate(pipeline))


def get_pass_fail_rates():
    """AGGREGATION + CONDITIONAL: pass / fail counts per exam.

    Uses $cond to classify each attempt as 'passed' or 'failed' by comparing
    the attempt score against the exam's passing_score.
    """
    pipeline = [
        {"$match": {"is_submitted": True}},
        # Join to get the exam's passing threshold
        {"$lookup": {
            "from": "exams",
            "localField": "exam_id",
            "foreignField": "_id",
            "as": "exam_info"
        }},
        {"$unwind": "$exam_info"},

        # --- CONDITIONAL QUERY ($cond) ---
        {"$addFields": {
            "result": {
                "$cond": {
                    "if": {"$gte": ["$score", "$exam_info.passing_score"]},
                    "then": "passed",
                    "else": "failed"
                }
            }
        }},

        # Two-stage grouping to pivot pass/fail into a single document per exam
        {"$group": {
            "_id": {"exam_id": "$exam_id", "result": "$result"},
            "count": {"$sum": 1},
            "exam_title": {"$first": "$exam_info.title"}
        }},
        {"$group": {
            "_id": "$_id.exam_id",
            "exam_title": {"$first": "$exam_title"},
            "results": {
                "$push": {"status": "$_id.result", "count": "$count"}
            },
            "total": {"$sum": "$count"}
        }},
        {"$sort": {"total": -1}}
    ]
    return list(db.attempts.aggregate(pipeline))


def get_student_performance(user_id):
    """AGGREGATION + CONDITIONAL: grade + pass/fail per attempt for one student.

    Uses $switch to map numeric scores to letter grades and $cond for pass/fail.
    """
    pipeline = [
        {"$match": {
            "user_id": ObjectId(user_id),
            "is_submitted": True
        }},
        {"$lookup": {
            "from": "exams",
            "localField": "exam_id",
            "foreignField": "_id",
            "as": "exam_info"
        }},
        {"$unwind": "$exam_info"},

        # --- CONDITIONAL QUERIES ($switch + $cond) ---
        {"$addFields": {
            "grade": {
                "$switch": {
                    "branches": [
                        {"case": {"$gte": ["$score", 90]}, "then": "A"},
                        {"case": {"$gte": ["$score", 80]}, "then": "B"},
                        {"case": {"$gte": ["$score", 70]}, "then": "C"},
                        {"case": {"$gte": ["$score", 60]}, "then": "D"},
                    ],
                    "default": "F"
                }
            },
            "passed": {
                "$cond": {
                    "if": {"$gte": ["$score", "$exam_info.passing_score"]},
                    "then": True,
                    "else": False
                }
            },
            "exam_title": "$exam_info.title"
        }},
        {"$sort": {"started_at": -1}}
    ]
    return list(db.attempts.aggregate(pipeline))


def get_question_difficulty(exam_id):
    """AGGREGATION + CONDITIONAL: per-question correct-answer rate & difficulty label.

    Unwinds answers, joins with questions, and uses $cond to flag correct
    answers, then $switch to classify difficulty.
    """
    pipeline = [
        {"$match": {
            "exam_id": ObjectId(exam_id),
            "is_submitted": True
        }},
        {"$unwind": "$answers"},
        {"$lookup": {
            "from": "questions",
            "localField": "answers.question_id",
            "foreignField": "_id",
            "as": "q"
        }},
        {"$unwind": "$q"},

        # --- CONDITIONAL ($cond): is the selected answer correct? ---
        {"$addFields": {
            "is_correct": {
                "$cond": {
                    "if": {"$eq": ["$answers.selected_option",
                                   "$q.correct_option"]},
                    "then": 1,
                    "else": 0
                }
            }
        }},

        {"$group": {
            "_id": "$answers.question_id",
            "question_text": {"$first": "$q.text"},
            "total_answers": {"$sum": 1},
            "correct_answers": {"$sum": "$is_correct"},
            "points": {"$first": "$q.points"}
        }},

        {"$addFields": {
            "correct_rate": {
                "$round": [
                    {"$multiply": [
                        {"$divide": ["$correct_answers", "$total_answers"]},
                        100
                    ]},
                    1
                ]
            },
            # --- CONDITIONAL ($switch): difficulty label ---
            "difficulty": {
                "$switch": {
                    "branches": [
                        {"case": {"$gte": [
                            {"$divide": ["$correct_answers", "$total_answers"]},
                            0.8
                        ]}, "then": "Easy"},
                        {"case": {"$gte": [
                            {"$divide": ["$correct_answers", "$total_answers"]},
                            0.5
                        ]}, "then": "Medium"},
                    ],
                    "default": "Hard"
                }
            }
        }},
        {"$sort": {"correct_rate": 1}}
    ]
    return list(db.attempts.aggregate(pipeline))


def get_integrity_report():
    """AGGREGATION + CONDITIONAL: flag suspicious attempts.

    Uses $switch to classify each attempt's integrity status:
      - 'Time Exceeded'      — server flagged overtime
      - 'Suspiciously Fast'  — completed in < 10 % of allowed time
      - 'Normal'             — everything looks fine
    """
    pipeline = [
        {"$match": {"is_submitted": True}},
        {"$lookup": {
            "from": "exams",
            "localField": "exam_id",
            "foreignField": "_id",
            "as": "exam_info"
        }},
        {"$unwind": "$exam_info"},

        # Compute durations
        {"$addFields": {
            "duration_seconds": {
                "$divide": [
                    {"$subtract": [
                        {"$ifNull": ["$finished_at", "$started_at"]},
                        "$started_at"
                    ]},
                    1000
                ]
            },
            "allowed_seconds": {
                "$multiply": ["$exam_info.duration_minutes", 60]
            }
        }},

        # --- CONDITIONAL ($switch): integrity classification ---
        {"$addFields": {
            "integrity_status": {
                "$switch": {
                    "branches": [
                        {
                            "case": {"$eq": ["$time_exceeded", True]},
                            "then": "Time Exceeded"
                        },
                        {
                            "case": {"$lt": [
                                "$duration_seconds",
                                {"$multiply": ["$allowed_seconds", 0.1]}
                            ]},
                            "then": "Suspiciously Fast"
                        },
                    ],
                    "default": "Normal"
                }
            }
        }},

        {"$group": {
            "_id": "$integrity_status",
            "count": {"$sum": 1},
            "avg_score": {"$avg": "$score"}
        }},
        {"$addFields": {
            "avg_score": {"$round": ["$avg_score", 1]}
        }},
        {"$sort": {"count": -1}}
    ]
    return list(db.attempts.aggregate(pipeline))


def get_top_students(limit=10):
    """AGGREGATION: rank students by average score across all submitted exams."""
    pipeline = [
        {"$match": {"is_submitted": True}},
        {"$group": {
            "_id": "$user_id",
            "avg_score": {"$avg": "$score"},
            "exams_taken": {"$sum": 1},
        }},
        {"$lookup": {
            "from": "users",
            "localField": "_id",
            "foreignField": "_id",
            "as": "user_info"
        }},
        {"$unwind": "$user_info"},
        {"$project": {
            "username": "$user_info.username",
            "avg_score": {"$round": ["$avg_score", 1]},
            "exams_taken": 1,
        }},
        {"$sort": {"avg_score": -1}},
        {"$limit": limit}
    ]
    return list(db.attempts.aggregate(pipeline))
