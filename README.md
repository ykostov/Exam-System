# Online Exam System (Django + MongoDB)

A web-based online examination platform built as a coursework project for the
"Databases" module. All data is stored in **MongoDB** — no SQL, no Django ORM.
The project showcases three concrete features of document-oriented databases:
`$jsonSchema` validation, conditional operators (`$cond`, `$switch`, `$ifNull`),
and aggregation pipelines.

## What it does

Two roles with separate flows:

- **Student** — registers, sees a list of active exams, takes them within a
  time limit (client-side timer with auto-submit on timeout), and receives a
  score plus a letter grade (A–F) and a pass/fail status.
- **Admin** — creates and edits exams with multiple-choice questions (2–6
  options each), activates/deactivates them, and reviews aggregated reports:
  per-exam averages, pass/fail rates, top students, and an integrity report
  flagging late and suspiciously fast attempts.

## Tech stack

| Layer         | Technology                       |
|---------------|----------------------------------|
| Backend       | Python 3.9, Django 4.2            |
| Database      | MongoDB 7                         |
| Driver        | PyMongo 4                         |
| Frontend      | Django templates + Bootstrap 5    |
| Passwords     | Django PBKDF2 hashers             |

## Getting started

**1. Start MongoDB**

```bash
# macOS
brew tap mongodb/brew
brew install mongodb-community
brew services start mongodb-community

# or via Docker
docker run -d --name mongo -p 27017:27017 mongo:7
```

**2. Python environment**

```bash
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
```

**3. Seed data and run the server**

```bash
python manage.py seed_data   # creates schemas, 1 admin + 5 students, sample exams
python manage.py runserver
```

Open <http://localhost:8000/>.

### Login credentials (after `seed_data`)

| Role    | Username                                      | Password    |
|---------|-----------------------------------------------|-------------|
| Admin   | `admin`                                        | `admin123`  |
| Student | `ivan`, `maria`, `georgi`, `elena`, `dimitar`  | `pass123`   |

### Configuration (optional)

Connection parameters are read from environment variables:

| Variable         | Default                        | Purpose             |
|------------------|--------------------------------|---------------------|
| `MONGO_URI`      | `mongodb://localhost:27017/`   | MongoDB address     |
| `MONGO_DB_NAME`  | `exam_system`                  | Database name       |

## Project layout

```
proekt_bazi_danni/
├── manage.py
├── requirements.txt
├── exam_system/                # Django settings and root URLs
├── exams/
│   ├── db.py                   # MongoDB connection, schemas, aggregations
│   ├── views.py                # Student and admin views
│   ├── urls.py
│   └── management/commands/seed_data.py
├── templates/                  # base, student/, admin/
├── static/                     # CSS and JS (exam.js — timer)
├── kursov_proekt_BD.typ        # Full project documentation (Typst source)
└── kursov_proekt_BD.pdf        # Compiled PDF
```

Full coursework documentation is in `kursov_proekt_BD.pdf`, compiled from the
`.typ` source with:

```bash
typst compile kursov_proekt_BD.typ
```
