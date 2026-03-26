# coding: utf-8

import os
import random
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, session, jsonify, send_from_directory, abort

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.secret_key = 'codesprout_secret_key_2026'
app.config['DATABASE'] = os.path.join(ROOT_DIR, 'database.db')

# صفحات HTML في جذر المشروع (للنشر على Render وغيره — طلبات GET / وليس فقط /api)
_HTML_PAGES = frozenset({
    'index.html', 'login.html', 'register.html', 'dashboard.html',
    'games.html', 'play.html', 'analytics.html', 'suggestions.html',
    'about.html', 'contact.html', 'admin.html', 'exercises.html',
})

BRACKET_RANK = {'6-8': 0, '9-11': 1, '12+': 2}


def get_db():
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn


def age_to_bracket(age):
    if age is None:
        return '9-11'
    if age <= 8:
        return '6-8'
    if age <= 11:
        return '9-11'
    return '12+'


def bracket_allows_exercise(user_bracket, min_bracket):
    return BRACKET_RANK.get(user_bracket, 0) >= BRACKET_RANK.get(min_bracket or '6-8', 0)


def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            full_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS exercises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            question_type TEXT NOT NULL,
            content TEXT NOT NULL,
            correct_answer TEXT NOT NULL,
            difficulty INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            exercise_id INTEGER NOT NULL,
            is_correct INTEGER NOT NULL,
            time_spent REAL,
            attempts_count INTEGER DEFAULT 1,
            error_type TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (exercise_id) REFERENCES exercises(id)
        );
        CREATE TABLE IF NOT EXISTS performance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            level TEXT NOT NULL,
            total_exercises INTEGER DEFAULT 0,
            correct_count INTEGER DEFAULT 0,
            total_time REAL DEFAULT 0,
            success_rate REAL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category TEXT,
            metric_name TEXT NOT NULL,
            metric_value REAL NOT NULL,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            ntype TEXT NOT NULL,
            read_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    ''')
    conn.commit()
    conn.close()


def migrate_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('PRAGMA table_info(users)')
    ucols = [r[1] for r in cursor.fetchall()]
    if 'role' not in ucols:
        cursor.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'child'")
    if 'age' not in ucols:
        cursor.execute("ALTER TABLE users ADD COLUMN age INTEGER")
    if 'age_bracket' not in ucols:
        cursor.execute("ALTER TABLE users ADD COLUMN age_bracket TEXT DEFAULT '9-11'")
    if 'parent_id' not in ucols:
        cursor.execute("ALTER TABLE users ADD COLUMN parent_id INTEGER REFERENCES users(id)")
    cursor.execute('PRAGMA table_info(exercises)')
    ecols = [r[1] for r in cursor.fetchall()]
    if 'min_age_bracket' not in ecols:
        cursor.execute("ALTER TABLE exercises ADD COLUMN min_age_bracket TEXT DEFAULT '6-8'")
    if 'stage_number' not in ecols:
        cursor.execute("ALTER TABLE exercises ADD COLUMN stage_number INTEGER DEFAULT 1")
    cursor.execute("UPDATE users SET role = 'child' WHERE role IS NULL OR role = ''")
    cursor.execute("UPDATE users SET age_bracket = '9-11' WHERE age_bracket IS NULL OR age_bracket = ''")
    cursor.execute("UPDATE exercises SET min_age_bracket = '6-8' WHERE min_age_bracket IS NULL OR min_age_bracket = ''")
    cursor.execute("UPDATE exercises SET stage_number = 1 WHERE stage_number IS NULL")
    if 'points' not in ucols:
        cursor.execute('ALTER TABLE users ADD COLUMN points INTEGER DEFAULT 0')
    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS badges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            icon_class TEXT DEFAULT 'fa-award',
            rule_type TEXT,
            rule_value INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS user_badges (
            user_id INTEGER NOT NULL,
            badge_id INTEGER NOT NULL,
            earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, badge_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (badge_id) REFERENCES badges(id)
        );
        CREATE TABLE IF NOT EXISTS motivational_phrases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phrase TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS challenge_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            exercise_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            detail TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (exercise_id) REFERENCES exercises(id)
        );
    ''')
    conn.commit()
    conn.close()


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'يرجى تسجيل الدخول أولاً'}), 401
        return f(*args, **kwargs)
    return decorated_function


def child_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'يرجى تسجيل الدخول أولاً'}), 401
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT role FROM users WHERE id = ?', (session['user_id'],))
        row = cursor.fetchone()
        conn.close()
        r = (row['role'] or 'child') if row else 'child'
        if r == 'parent':
            return jsonify({'error': 'هذه الخاصية للحسابات المخصصة للأطفال. سجّل دخولاً بحساب طفل أو أنشئ حساباً للطفل من لوحة ولي الأمر.'}), 403
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'يرجى تسجيل الدخول أولاً'}), 401
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT role FROM users WHERE id = ?', (session['user_id'],))
        row = cursor.fetchone()
        conn.close()
        if not row or (row['role'] or '') != 'admin':
            return jsonify({'error': 'هذه الصفحة للمدير فقط'}), 403
        return f(*args, **kwargs)
    return decorated_function


def get_user_level(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT level FROM performance WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row['level'] if row else 'مبتدئ'


def calculate_level(success_rate, total_attempts):
    if total_attempts < 5:
        return 'مبتدئ'
    if success_rate >= 80:
        return 'متقدم'
    if success_rate >= 50:
        return 'متوسط'
    return 'مبتدئ'


def get_exercise_categories():
    return [
        ('ترتيب', 'ترتيب الأوامر'),
        ('متغيرات', 'المتغيرات'),
        ('حلقات', 'الحلقات'),
        ('منطق', 'التفكير المنطقي'),
        ('اختيار', 'اختيار صحيح وخاطئ'),
    ]


def create_notification(user_id, title, body, ntype='motivation'):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO notifications (user_id, title, body, ntype) VALUES (?, ?, ?, ?)',
        (user_id, title, body, ntype)
    )
    conn.commit()
    conn.close()


def grant_badges_for_user(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT COALESCE(points, 0) as p FROM users WHERE id = ?', (user_id,))
    pts = cursor.fetchone()['p']
    cursor.execute('SELECT COUNT(*) as c FROM attempts WHERE user_id = ? AND is_correct = 1', (user_id,))
    ctot = cursor.fetchone()['c']
    cursor.execute(
        'SELECT COUNT(DISTINCT exercise_id) as d FROM attempts WHERE user_id = ? AND is_correct = 1',
        (user_id,)
    )
    dist = cursor.fetchone()['d']
    st = streak_days(user_id)
    cursor.execute('SELECT id, code, title FROM badges')
    rows = cursor.fetchall()
    earned = []
    for b in rows:
        cursor.execute('SELECT 1 FROM user_badges WHERE user_id = ? AND badge_id = ?', (user_id, b['id']))
        if cursor.fetchone():
            continue
        code = b['code']
        grant = False
        if code == 'first_step' and ctot >= 1:
            grant = True
        elif code == 'ten_answers' and ctot >= 10:
            grant = True
        elif code == 'explorer' and dist >= 5:
            grant = True
        elif code == 'hot_streak' and st >= 3:
            grant = True
        elif code == 'points_100' and pts >= 100:
            grant = True
        elif code == 'deep_25' and (ctot >= 25 or dist >= 15):
            grant = True
        if grant:
            cursor.execute('INSERT INTO user_badges (user_id, badge_id) VALUES (?, ?)', (user_id, b['id']))
            earned.append(b['title'])
            create_notification(user_id, 'شارة جديدة', 'حصلت على: «' + b['title'] + '»', 'badge')
    conn.commit()
    conn.close()
    return earned


def seed_badges_and_phrases():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as c FROM badges')
    if cursor.fetchone()['c'] == 0:
        for code, title, desc, icon in [
            ('first_step', 'أول خطوة', 'إنجاز أول إجابة صحيحة', 'fa-star'),
            ('ten_answers', 'عشر إجابات', 'عشر إجابات صحيحة تراكميًا', 'fa-certificate'),
            ('explorer', 'مستكشف المحتوى', 'حلّ خمسة تمارين مختلفة', 'fa-map'),
            ('hot_streak', 'سلسلة حماس', 'ثلاثة أيام نشاط متتالية', 'fa-fire'),
            ('points_100', 'مئة نقطة', 'اجتمع لديك 100 نقطة', 'fa-coins'),
            ('deep_25', 'متعلّم عميق', '25 إجابة صحيحة أو 15 تمرينًا مختلفًا', 'fa-graduation-cap'),
        ]:
            cursor.execute(
                'INSERT INTO badges (code, title, description, icon_class, rule_type, rule_value) VALUES (?, ?, ?, ?, ?, ?)',
                (code, title, desc, icon, 'auto', 0)
            )
    cursor.execute('SELECT COUNT(*) as c FROM motivational_phrases')
    if cursor.fetchone()['c'] == 0:
        phrases = [
            'كل خطوة صغيرة تقرّبك من فهم أعمق للبرمجة.',
            'الترتيب الصحيح للأوامر هو أساس التفكير الخوارزمي.',
            'المتغيرات تحمل معنى — اختر أسماءً واضحة كما يفعل المحترفون.',
            'الحلقات تعلّمك الصبر والدقة في التكرار.',
            'المنطق البرمجي يُشبّه حل المشكلات في الحياة اليومية.',
            'لا تخف من الخطأ — المحاولة جزء من التعلّم.',
            'برمجة الأطفال تبدأ بالتفكير قبل الكتابة.',
            'أنت تبني عادات عقلية تخدمك في المستقبل الرقمي.',
            'الممارسة اليومية أقوى من الجلسة الطويلة النادرة.',
            'كل شارة جديدة تعكس تقدّمًا حقيقيًا.',
        ]
        for p in phrases:
            cursor.execute('INSERT INTO motivational_phrases (phrase) VALUES (?)', (p,))
    conn.commit()
    conn.close()


def seed_demo_users():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM users WHERE username = ?', ('admin',))
    if not cursor.fetchone():
        cursor.execute(
            'INSERT INTO users (username, password, full_name, role, age, age_bracket, parent_id, points) VALUES (?,?,?,?,?,?,?,?)',
            ('admin', 'Admin@2026', 'مدير المنصة', 'admin', None, '9-11', None, 0)
        )
    cursor.execute('SELECT 1 FROM users WHERE username = ?', ('parent_demo',))
    if not cursor.fetchone():
        cursor.execute(
            'INSERT INTO users (username, password, full_name, role, age, age_bracket, parent_id, points) VALUES (?,?,?,?,?,?,?,?)',
            ('parent_demo', 'Demo@2026', 'فاطمة — ولي أمر', 'parent', None, '9-11', None, 0)
        )
    conn.commit()
    cursor.execute('SELECT id FROM users WHERE username = ?', ('parent_demo',))
    pr = cursor.fetchone()
    pid = pr['id'] if pr else None
    children = [
        ('child_lina', 'Demo@2026', 'لينا — متعلّمة', 7, '6-8', 120),
        ('child_omar', 'Demo@2026', 'عمر — متعلّم', 10, '9-11', 200),
        ('child_sara', 'Demo@2026', 'سارة — متعلّمة', 13, '12+', 350),
    ]
    for uname, pw, fn, age, bracket, pts in children:
        cursor.execute('SELECT 1 FROM users WHERE username = ?', (uname,))
        if cursor.fetchone():
            continue
        cursor.execute(
            'INSERT INTO users (username, password, full_name, role, age, age_bracket, parent_id, points) VALUES (?,?,?,?,?,?,?,?)',
            (uname, pw, fn, 'child', age, bracket, pid, pts)
        )
        uid = cursor.lastrowid
        cursor.execute('DELETE FROM performance WHERE user_id = ?', (uid,))
        cursor.execute(
            'INSERT INTO performance (user_id, level, total_exercises, correct_count, total_time, success_rate) VALUES (?,?,?,?,?,?)',
            (uid, 'متوسط' if pts > 150 else 'مبتدئ', 0, 0, 0, 0.0)
        )
    conn.commit()
    conn.close()


def last_attempt_date(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT created_at FROM attempts WHERE user_id = ? ORDER BY created_at DESC LIMIT 1',
        (user_id,)
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    s = str(row['created_at'])
    try:
        if len(s) >= 19:
            return datetime.strptime(s[:19], '%Y-%m-%d %H:%M:%S')
        return datetime.strptime(s[:10], '%Y-%m-%d')
    except ValueError:
        try:
            return datetime.fromisoformat(s.replace('Z', '+00:00').split('.')[0])
        except Exception:
            return None


def streak_days(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT DISTINCT date(created_at) as d FROM attempts WHERE user_id = ? ORDER BY d DESC LIMIT 30",
        (user_id,)
    )
    days = [r['d'] for r in cursor.fetchall()]
    conn.close()
    if not days:
        return 0
    streak = 1
    for i in range(1, len(days)):
        try:
            newer = datetime.strptime(days[i - 1], '%Y-%m-%d').date()
            older = datetime.strptime(days[i], '%Y-%m-%d').date()
            if (newer - older).days == 1:
                streak += 1
            else:
                break
        except Exception:
            break
    return streak


@app.before_request
def handle_options():
    if request.method == 'OPTIONS':
        resp = jsonify()
        resp.status_code = 204
        return resp


@app.after_request
def add_cors(resp):
    orig = request.headers.get('Origin') or 'null'
    resp.headers['Access-Control-Allow-Origin'] = orig
    resp.headers['Access-Control-Allow-Credentials'] = 'true'
    resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return resp


@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    full_name = data.get('full_name', '').strip()
    role = (data.get('role') or 'child').strip().lower()
    if role not in ('child', 'parent'):
        role = 'child'
    age = data.get('age')
    if role == 'child':
        try:
            age = int(age)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'يرجى إدخال عمر الطفل (رقم بين 6 و 15)'}), 400
        if age < 6 or age > 15:
            return jsonify({'success': False, 'error': 'العمر يجب أن يكون بين 6 و 15'}), 400
        age_bracket = age_to_bracket(age)
    else:
        age = None
        age_bracket = '9-11'
    if not username or not password or not full_name:
        return jsonify({'success': False, 'error': 'يرجى ملء جميع الحقول'}), 400
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT INTO users (username, password, full_name, role, age, age_bracket, parent_id) VALUES (?, ?, ?, ?, ?, ?, NULL)',
            (username, password, full_name, role, age, age_bracket)
        )
        conn.commit()
        user_id = cursor.lastrowid
        if role == 'child':
            cursor.execute('INSERT INTO performance (user_id, level) VALUES (?, ?)', (user_id, 'مبتدئ'))
            conn.commit()
        conn.close()
        create_notification(
            user_id,
            'مرحباً في CodeSprout',
            'ابدأ رحلتك من مكتبة الألعاب التعليمية وانتقل بين المراحل خطوة بخطوة.',
            'motivation'
        )
        return jsonify({'success': True, 'redirect': 'login.html'})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'success': False, 'error': 'اسم المستخدم مستخدم مسبقاً'}), 400


@app.route('/api/register_child', methods=['POST'])
@login_required
def api_register_child():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT role FROM users WHERE id = ?', (session['user_id'],))
    row = cursor.fetchone()
    if not row or (row['role'] or '') != 'parent':
        conn.close()
        return jsonify({'success': False, 'error': 'هذه الخاصية متاحة لحسابات أولياء الأمور فقط'}), 403
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    full_name = data.get('full_name', '').strip()
    try:
        age = int(data.get('age'))
    except (TypeError, ValueError):
        conn.close()
        return jsonify({'success': False, 'error': 'يرجى إدخال عمر صحيح للطفل'}), 400
    if age < 6 or age > 15:
        conn.close()
        return jsonify({'success': False, 'error': 'العمر يجب أن يكون بين 6 و 15'}), 400
    if not username or not password or not full_name:
        conn.close()
        return jsonify({'success': False, 'error': 'يرجى ملء جميع الحقول'}), 400
    age_bracket = age_to_bracket(age)
    parent_id = session['user_id']
    try:
        cursor.execute(
            'INSERT INTO users (username, password, full_name, role, age, age_bracket, parent_id) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (username, password, full_name, 'child', age, age_bracket, parent_id)
        )
        conn.commit()
        child_id = cursor.lastrowid
        cursor.execute('INSERT INTO performance (user_id, level) VALUES (?, ?)', (child_id, 'مبتدئ'))
        conn.commit()
        conn.close()
        create_notification(
            child_id,
            'تم إنشاء حسابك',
            'يمكنك الآن تسجيل الدخول واللعب من مكتبة الألعاب التعليمية.',
            'motivation'
        )
        return jsonify({'success': True, 'child_id': child_id})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'success': False, 'error': 'اسم المستخدم مستخدم مسبقاً'}), 400


@app.route('/api/parent/children')
@login_required
def api_parent_children():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT role FROM users WHERE id = ?', (session['user_id'],))
    row = cursor.fetchone()
    if not row or (row['role'] or '') != 'parent':
        conn.close()
        return jsonify({'error': 'غير مصرح'}), 403
    cursor.execute(
        'SELECT id, username, full_name, age, age_bracket FROM users WHERE parent_id = ? ORDER BY full_name',
        (session['user_id'],)
    )
    children = []
    for ch in cursor.fetchall():
        cid = ch['id']
        cursor.execute('SELECT COUNT(*) as t FROM attempts WHERE user_id = ?', (cid,))
        attempts = cursor.fetchone()['t']
        cursor.execute('SELECT COUNT(*) as c FROM attempts WHERE user_id = ? AND is_correct = 1', (cid,))
        correct = cursor.fetchone()['c']
        cursor.execute('SELECT level FROM performance WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1', (cid,))
        pl = cursor.fetchone()
        level = pl['level'] if pl else 'مبتدئ'
        children.append({
            'id': cid,
            'username': ch['username'],
            'full_name': ch['full_name'],
            'age': ch['age'],
            'age_bracket': ch['age_bracket'],
            'total_attempts': attempts,
            'correct_count': correct,
            'level': level
        })
    conn.close()
    return jsonify({'children': children})


@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    if not username or not password:
        return jsonify({'success': False, 'error': 'يرجى إدخال اسم المستخدم وكلمة المرور'}), 400
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, username, full_name, role, age, age_bracket FROM users WHERE username = ? AND password = ?',
        (username, password)
    )
    user = cursor.fetchone()
    conn.close()
    if user:
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['full_name'] = user['full_name']
        session['role'] = user['role'] or 'child'
        uid = user['id']
        last = last_attempt_date(uid)
        if last and datetime.utcnow() - last > timedelta(days=7):
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) as c FROM notifications WHERE user_id = ? AND ntype = 'reminder' AND read_at IS NULL",
                (uid,)
            )
            has_unread_reminder = cursor.fetchone()['c'] > 0
            conn.close()
            if not has_unread_reminder:
                create_notification(
                    uid,
                    'اشتقنا لك',
                    'لم تلعب منذ فترة — عد لمكتبة الألعاب وأكمل مرحلتك التالية!',
                    'reminder'
                )
        rd = 'admin.html' if (user['role'] or '') == 'admin' else 'dashboard.html'
        return jsonify({
            'success': True,
            'redirect': rd,
            'full_name': user['full_name'],
            'role': session['role']
        })
    return jsonify({'success': False, 'error': 'اسم المستخدم أو كلمة المرور غير صحيحة'}), 401


@app.route('/api/logout')
def api_logout():
    session.clear()
    return jsonify({'success': True})


@app.route('/api/user')
def api_user():
    if 'user_id' not in session:
        return jsonify({'logged_in': False})
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT full_name, username, role, age, age_bracket, parent_id, COALESCE(points, 0) as points FROM users WHERE id = ?',
        (session['user_id'],)
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify({'logged_in': False})
    return jsonify({
        'logged_in': True,
        'full_name': row['full_name'],
        'username': row['username'],
        'role': row['role'] or 'child',
        'age': row['age'],
        'age_bracket': row['age_bracket'],
        'parent_id': row['parent_id'],
        'points': row['points']
    })


@app.route('/api/notifications')
@login_required
def api_notifications():
    user_id = session['user_id']
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, title, body, ntype, read_at, created_at FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 80',
        (user_id,)
    )
    rows = [dict(r) for r in cursor.fetchall()]
    cursor.execute(
        'SELECT COUNT(*) as c FROM notifications WHERE user_id = ? AND read_at IS NULL',
        (user_id,)
    )
    unread = cursor.fetchone()['c']
    conn.close()
    return jsonify({'notifications': rows, 'unread_count': unread})


@app.route('/api/notifications/read', methods=['POST'])
@login_required
def api_notifications_read():
    data = request.get_json() or {}
    nid = data.get('id')
    user_id = session['user_id']
    conn = get_db()
    cursor = conn.cursor()
    if nid == 'all':
        cursor.execute(
            'UPDATE notifications SET read_at = CURRENT_TIMESTAMP WHERE user_id = ? AND read_at IS NULL',
            (user_id,)
        )
    else:
        try:
            nid = int(nid)
        except (TypeError, ValueError):
            conn.close()
            return jsonify({'success': False}), 400
        cursor.execute(
            'UPDATE notifications SET read_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?',
            (nid, user_id)
        )
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/stages')
@login_required
def api_stages():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT role, age_bracket FROM users WHERE id = ?', (session['user_id'],))
    ur = cursor.fetchone()
    role = ur['role'] or 'child'
    user_bracket = ur['age_bracket'] or '9-11'
    if role == 'parent':
        user_bracket = '12+'
    elif role == 'admin':
        user_bracket = ur['age_bracket'] or '12+'
    cursor.execute('SELECT MAX(stage_number) as m FROM exercises')
    max_stage = cursor.fetchone()['m'] or 1
    cursor.execute('SELECT DISTINCT stage_number FROM exercises ORDER BY stage_number')
    stage_nums = [r['stage_number'] for r in cursor.fetchall()]
    progress = []
    uid = session['user_id']
    for sn in stage_nums:
        cursor.execute('SELECT id FROM exercises WHERE stage_number = ?', (sn,))
        eids = [r['id'] for r in cursor.fetchall()]
        if not eids:
            continue
        ph = ','.join('?' * len(eids))
        cursor.execute(
            f'SELECT COUNT(DISTINCT exercise_id) as c FROM attempts WHERE user_id = ? AND is_correct = 1 AND exercise_id IN ({ph})',
            [uid] + eids
        )
        solved = cursor.fetchone()['c']
        progress.append({'stage_number': sn, 'total': len(eids), 'solved': solved, 'complete': solved >= len(eids)})
    conn.close()
    return jsonify({
        'max_stage': max_stage,
        'stages': progress,
        'user_bracket': user_bracket,
        'role': role
    })


@app.route('/api/dashboard')
@login_required
def api_dashboard():
    user_id = session['user_id']
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT role, age_bracket, age, COALESCE(points, 0) as points FROM users WHERE id = ?', (user_id,))
    urow = cursor.fetchone()
    role = urow['role'] or 'child'
    level = get_user_level(user_id) if role in ('child', 'admin') else '-'
    cursor.execute('SELECT COUNT(*) as total FROM attempts WHERE user_id = ?', (user_id,))
    total_attempts = cursor.fetchone()['total']
    cursor.execute('SELECT COUNT(*) as correct FROM attempts WHERE user_id = ? AND is_correct = 1', (user_id,))
    correct_count = cursor.fetchone()['correct']
    success_rate = (correct_count / total_attempts * 100) if total_attempts > 0 else 0
    conn.close()
    return jsonify({
        'level': level,
        'total_attempts': total_attempts,
        'correct_count': correct_count,
        'success_rate': round(success_rate, 1),
        'role': role,
        'age_bracket': urow['age_bracket'],
        'age': urow['age'],
        'streak_days': streak_days(user_id) if role in ('child', 'admin') else 0,
        'points': urow['points']
    })


@app.route('/api/exercises')
@login_required
def api_exercises():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT role, age_bracket, age FROM users WHERE id = ?', (session['user_id'],))
    urow = cursor.fetchone()
    role = urow['role'] or 'child'
    user_bracket = urow['age_bracket'] or '9-11'
    if role == 'parent':
        conn.close()
        return jsonify({
            'exercises': [],
            'categories': get_exercise_categories(),
            'parent_mode': True,
            'message': 'للمشاركة في الألعاب، سجّل دخولاً بحساب الطفل أو أنشئ حساباً للطفل من لوحة التحكم.'
        })
    if role == 'admin':
        cursor.execute('SELECT * FROM exercises ORDER BY stage_number, category, difficulty')
        exs = [dict(x) for x in cursor.fetchall()]
        conn.close()
        return jsonify({
            'exercises': exs,
            'categories': get_exercise_categories(),
            'parent_mode': False,
            'user_bracket': '12+',
            'is_admin': True
        })
    if not bracket_allows_exercise(user_bracket, '6-8'):
        pass
    cursor.execute('SELECT * FROM exercises ORDER BY stage_number, category, difficulty')
    exs = cursor.fetchall()
    conn.close()
    filtered = []
    for ex in exs:
        exd = dict(ex)
        if bracket_allows_exercise(user_bracket, exd.get('min_age_bracket')):
            filtered.append(exd)
    categories = get_exercise_categories()
    return jsonify({'exercises': filtered, 'categories': categories, 'parent_mode': False, 'user_bracket': user_bracket})


@app.route('/api/analytics')
@login_required
def api_analytics():
    user_id = session['user_id']
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT role FROM users WHERE id = ?', (user_id,))
    r0 = cursor.fetchone()
    if r0 and (r0['role'] or '') == 'parent':
        conn.close()
        return jsonify({'parent_mode': True, 'attempts': [], 'performance': {}, 'errors': [], 'weak_exercises': [], 'level': '-'})
    cursor.execute('SELECT * FROM attempts WHERE user_id = ? ORDER BY created_at DESC', (user_id,))
    attempts = [dict(a) for a in cursor.fetchall()]
    cursor.execute('SELECT * FROM performance WHERE user_id = ?', (user_id,))
    perf = cursor.fetchone()
    cursor.execute('''
        SELECT error_type, COUNT(*) as count FROM attempts
        WHERE user_id = ? AND is_correct = 0 AND error_type IS NOT NULL
        GROUP BY error_type ORDER BY count DESC
    ''', (user_id,))
    errors = [dict(e) for e in cursor.fetchall()]
    cursor.execute('''
        SELECT exercise_id, COUNT(*) as err_count FROM attempts
        WHERE user_id = ? AND is_correct = 0
        GROUP BY exercise_id ORDER BY err_count DESC LIMIT 5
    ''', (user_id,))
    weak_exercises = [dict(w) for w in cursor.fetchall()]
    conn.close()
    level = get_user_level(user_id)
    return jsonify({
        'attempts': attempts,
        'performance': dict(perf) if perf else {},
        'errors': errors,
        'weak_exercises': weak_exercises,
        'level': level,
        'parent_mode': False
    })


@app.route('/api/suggestions')
@login_required
def api_suggestions():
    user_id = session['user_id']
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT role FROM users WHERE id = ?', (user_id,))
    r0 = cursor.fetchone()
    if r0 and (r0['role'] or '') == 'parent':
        conn.close()
        return jsonify({'weak_categories': [], 'parent_mode': True})
    cursor.execute('''
        SELECT e.category, COUNT(*) as err_count FROM attempts a
        JOIN exercises e ON a.exercise_id = e.id
        WHERE a.user_id = ? AND a.is_correct = 0
        GROUP BY e.category ORDER BY err_count DESC
    ''', (user_id,))
    weak_categories = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({'weak_categories': weak_categories, 'parent_mode': False})


@app.route('/api/gamification/me')
@login_required
def api_gamification_me():
    user_id = session['user_id']
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT COALESCE(points, 0) as p, role FROM users WHERE id = ?', (user_id,))
    row = cursor.fetchone()
    pts = row['p']
    role = row['role'] or 'child'
    cursor.execute(
        '''SELECT b.title, b.icon_class, b.description, ub.earned_at
        FROM user_badges ub JOIN badges b ON b.id = ub.badge_id WHERE ub.user_id = ?
        ORDER BY ub.earned_at DESC''',
        (user_id,)
    )
    badges = [dict(x) for x in cursor.fetchall()]
    cursor.execute(
        'SELECT COUNT(DISTINCT exercise_id) as d FROM attempts WHERE user_id = ? AND is_correct = 1',
        (user_id,)
    )
    solved = cursor.fetchone()['d']
    cursor.execute('SELECT COUNT(*) as c FROM exercises')
    total_ex = cursor.fetchone()['c']
    cursor.execute('SELECT COUNT(*) as c FROM challenge_events WHERE user_id = ? AND event_type = ?', (user_id, 'solve_correct'))
    challenge_events = cursor.fetchone()['c']
    conn.close()
    return jsonify({
        'points': pts,
        'badges': badges,
        'challenges_solved_distinct': solved,
        'total_exercises': total_ex,
        'challenge_completions_logged': challenge_events,
        'role': role
    })


@app.route('/api/motivation/random')
@login_required
def api_motivation_random():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT phrase FROM motivational_phrases ORDER BY RANDOM() LIMIT 1')
    row = cursor.fetchone()
    conn.close()
    return jsonify({'phrase': row['phrase'] if row else 'واصل التعلّم بثبات.'})


@app.route('/api/admin/overview')
@login_required
@admin_required
def api_admin_overview():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as c FROM users')
    total_users = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM users WHERE role = 'child'")
    n_child = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM users WHERE role = 'parent'")
    n_parent = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM users WHERE role = 'admin'")
    n_admin = cursor.fetchone()['c']
    cursor.execute('SELECT COUNT(*) as c FROM attempts')
    n_attempts = cursor.fetchone()['c']
    cursor.execute('SELECT COUNT(*) as c FROM exercises')
    n_ex = cursor.fetchone()['c']
    cursor.execute('SELECT COUNT(*) as c FROM user_badges')
    n_badges = cursor.fetchone()['c']
    cursor.execute('SELECT COUNT(*) as c FROM challenge_events')
    n_ch = cursor.fetchone()['c']
    cursor.execute('''
        SELECT u.username, u.full_name, u.role, a.created_at, a.is_correct, e.title as exercise_title
        FROM attempts a
        JOIN users u ON u.id = a.user_id
        LEFT JOIN exercises e ON e.id = a.exercise_id
        ORDER BY a.created_at DESC LIMIT 20
    ''')
    recent = []
    for r in cursor.fetchall():
        recent.append({
            'username': r['username'],
            'full_name': r['full_name'],
            'role': r['role'],
            'created_at': str(r['created_at']),
            'is_correct': r['is_correct'],
            'exercise_title': r['exercise_title']
        })
    conn.close()
    return jsonify({
        'total_users': total_users,
        'users_child': n_child,
        'users_parent': n_parent,
        'users_admin': n_admin,
        'total_attempts': n_attempts,
        'total_exercises': n_ex,
        'badges_awarded_total': n_badges,
        'challenge_events_total': n_ch,
        'recent_attempts': recent
    })


@app.route('/api/admin/users')
@login_required
@admin_required
def api_admin_users():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        '''SELECT id, username, full_name, role, age, age_bracket, COALESCE(points, 0) as points, created_at
        FROM users ORDER BY id'''
    )
    users = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({'users': users})


@app.route('/api/contact', methods=['POST'])
def api_contact():
    data = request.get_json() or request.form
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip()
    message = (data.get('message') or '').strip()
    if name and (email or message):
        return jsonify({'success': True, 'message': 'شكراً على تواصلك! سنرد عليك قريباً'})
    return jsonify({'success': False, 'error': 'يرجى ملء الحقول المطلوبة'}), 400


@app.route('/api/submit_attempt', methods=['POST'])
@login_required
@child_required
def submit_attempt():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'بيانات غير صالحة'}), 400
    exercise_id = data.get('exercise_id')
    is_correct = data.get('is_correct', False)
    time_spent = data.get('time_spent', 0)
    attempts_count = data.get('attempts_count', 1)
    error_type = data.get('error_type', '')
    user_id = session['user_id']
    conn = get_db()
    cursor = conn.cursor()
    prev_level = get_user_level(user_id)
    cursor.execute('SELECT category, min_age_bracket FROM exercises WHERE id = ?', (exercise_id,))
    ex = cursor.fetchone()
    done_before_cat = None
    if ex and is_correct:
        cursor.execute('''
            SELECT COUNT(DISTINCT exercise_id) as c FROM attempts
            WHERE user_id = ? AND is_correct = 1 AND exercise_id IN (SELECT id FROM exercises WHERE category = ?)
        ''', (user_id, ex['category']))
        done_before_cat = cursor.fetchone()['c']
    cursor.execute('''
        INSERT INTO attempts (user_id, exercise_id, is_correct, time_spent, attempts_count, error_type)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, exercise_id, 1 if is_correct else 0, time_spent, attempts_count, error_type or None))
    conn.commit()
    if is_correct:
        cursor.execute('UPDATE users SET points = COALESCE(points, 0) + 10 WHERE id = ?', (user_id,))
        cursor.execute(
            'INSERT INTO challenge_events (user_id, exercise_id, event_type, detail) VALUES (?, ?, ?, ?)',
            (user_id, exercise_id, 'solve_correct', '')
        )
        conn.commit()
    if ex:
        cursor.execute('''
            INSERT INTO analytics (user_id, category, metric_name, metric_value)
            VALUES (?, ?, ?, ?)
        ''', (user_id, ex['category'], 'success' if is_correct else 'error', 1.0))
        conn.commit()
    cursor.execute('''
        SELECT COUNT(*) as total, SUM(CASE WHEN is_correct=1 THEN 1 ELSE 0 END) as correct
        FROM attempts WHERE user_id = ?
    ''', (user_id,))
    row = cursor.fetchone()
    total = row['total']
    correct = row['correct']
    success_rate = (correct / total * 100) if total > 0 else 0
    level = calculate_level(success_rate, total)
    cursor.execute('SELECT SUM(time_spent) as t FROM attempts WHERE user_id = ?', (user_id,))
    tot_time = cursor.fetchone()['t'] or 0
    cursor.execute('DELETE FROM performance WHERE user_id = ?', (user_id,))
    cursor.execute('''
        INSERT INTO performance (user_id, level, total_exercises, correct_count, total_time, success_rate)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, level, total, correct, tot_time, success_rate))
    conn.commit()
    if is_correct:
        if level != prev_level:
            create_notification(
                user_id,
                'ترقية المستوى',
                f'أصبح مستواك الآن: {level}. أحسنت الاستمرار!',
                'level_up'
            )
        st = streak_days(user_id)
        if st >= 3 and st % 3 == 0:
            create_notification(
                user_id,
                'سلسلة أيام ممتازة',
                f'لعبت {st} أيام متتالية. واصل التحدي!',
                'motivation'
            )
        if ex and done_before_cat is not None:
            cursor.execute('SELECT COUNT(*) as c FROM exercises WHERE category = ?', (ex['category'],))
            cat_total = cursor.fetchone()['c']
            cursor.execute('''
                SELECT COUNT(DISTINCT exercise_id) as c FROM attempts
                WHERE user_id = ? AND is_correct = 1 AND exercise_id IN (SELECT id FROM exercises WHERE category = ?)
            ''', (user_id, ex['category']))
            done_after = cursor.fetchone()['c']
            if cat_total > 0 and done_after >= cat_total and done_before_cat < cat_total:
                create_notification(
                    user_id,
                    'إنجاز: اكتمل موضوع',
                    f'أكملت جميع ألعاب فئة «{ex["category"]}» بنجاح!',
                    'milestone'
                )
    conn.close()
    badges_earned = []
    pts_new = None
    if is_correct:
        badges_earned = grant_badges_for_user(user_id)
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT COALESCE(points, 0) as p FROM users WHERE id = ?', (user_id,))
        pts_new = cursor.fetchone()['p']
        conn.close()
    return jsonify({
        'success': True,
        'level': level,
        'success_rate': round(success_rate, 1),
        'points': pts_new,
        'badges_earned': badges_earned
    })


def append_rich_exercises():
    conn = get_db()
    cursor = conn.cursor()
    extra = [
        ('غسل اليدين', 'ترتيب', 'رتّب خطوات غسل اليدين بالترتيب الصحيح للوصول لبرنامج صحي.', 'order', '["بلل اليدين","ضع الصابون","افرك لمدة 20 ثانية","اشطف وجفف"]', '["بلل اليدين","ضع الصابون","افرك لمدة 20 ثانية","اشطف وجفف"]', 1, '6-8', 2),
        ('تجهيز الحقيبة', 'ترتيب', 'ما الترتيب المنطقي لتحضير الحقيبة قبل المدرسة؟', 'order', '["ضع الكتب","أغلق القلم","ضع المذكرة","اربط الحقيبة"]', '["ضع الكتب","ضع المذكرة","أغلق القلم","اربط الحقيبة"]', 1, '6-8', 3),
        ('رحلة القطار', 'ترتيب', 'رتّب مراحل رحلة القطار من البداية للنهاية.', 'order', '["احجز التذكرة","اذهب للمحطة","اركب القطار","انزل في المحطة"]', '["احجز التذكرة","اذهب للمحطة","اركب القطار","انزل في المحطة"]', 1, '6-8', 4),
        ('وصفة السلطة', 'ترتيب', 'رتّب خطوات تحضير سلطة بسيطة.', 'order', '["اغسل الخضار","قطّعها","أضف الزيت","قلّب وقدّم"]', '["اغسل الخضار","قطّعها","أضف الزيت","قلّب وقدّم"]', 2, '9-11', 5),
        ('خوارزمية الاستيقاظ', 'ترتيب', 'رتّب روتين الاستيقاظ الصباحي.', 'order', '["أوقف المنبه","اغسل وجهك","تناول فطوراً خفيفاً","ارتدِ ملابسك"]', '["أوقف المنبه","اغسل وجهك","تناول فطوراً خفيفاً","ارتدِ ملابسك"]', 2, '9-11', 6),
        ('تصحيح مسار الروبوت', 'ترتيب', 'الروبوت يحتاج: أمام، يمين، أمام، توقف.', 'order', '["تحرك للأمام","انعطف يميناً","تحرك للأمام","توقف"]', '["تحرك للأمام","انعطف يميناً","تحرك للأمام","توقف"]', 2, '9-11', 7),
        ('مشروع بسيط', 'ترتيب', 'مراحل إنجاز مشروع صفّي: فكرة، تصميم، برمجة، اختبار.', 'order', '["فكرة","تصميم","برمجة","اختبار"]', '["فكرة","تصميم","برمجة","اختبار"]', 2, '12+', 8),
        ('نشر تطبيق', 'ترتيب', 'ترتيب معقول لنشر تطبيق ويب.', 'order', '["بناء","اختبار","رفع للخادم","مراقبة"]', '["بناء","اختبار","رفع للخادم","مراقبة"]', 3, '12+', 9),
        ('اسم المتغير للون', 'متغيرات', 'أي اسم متغير يتبع الأسلوب الشائع في بايثون لحفظ لون الخلفية؟', 'choice', '["bg_color","BgColor","bg-color","1color"]', 'bg_color', 1, '6-8', 2),
        ('تخزين الاسم', 'متغيرات', 'لتخزين اسم المستخدم في برنامج، ما الأنسب؟', 'choice', '["user_name","x","data","123"]', 'user_name', 1, '6-8', 3),
        ('قيمة ثابتة', 'متغيرات', 'ما الذي يميّز الثابت عن المتغير في التصميم البرمجي؟', 'choice', '["لا يتغير أثناء التنفيذ","يتغير كل سطر","يُحذف تلقائياً","يساوي صفراً دائماً"]', 'لا يتغير أثناء التنفيذ', 2, '9-11', 4),
        ('أنواع البيانات', 'متغيرات', 'ما نوع القيمة True في بايثون؟', 'choice', '["bool","int","str","float"]', 'bool', 2, '9-11', 5),
        ('نطاق المتغير', 'متغيرات', 'في بايثون، متغير يُعرّف داخل دالة يكون مرئياً أين؟', 'choice', '["داخل الدالة فقط","في كل الملف","في المجلد","عالمياً دائماً"]', 'داخل الدالة فقط', 2, '12+', 7),
        ('قائمة في بايثون', 'متغيرات', 'ما الصياغة الصحيحة لقائمة فارغة؟', 'choice', '["[]","{}","()","list()"]', '[]', 2, '12+', 8),
        ('حلقة العد التصاعدي', 'حلقات', 'لطباعة الأرقام من 1 إلى 10 في بايثون، أي نطاق range أنسب؟', 'choice', '["range(1,11)","range(10)","range(1,10)","range(0,11)"]', 'range(1,11)', 2, '9-11', 5),
        ('خروج مبكر', 'حلقات', 'أي أمر يوقف حلقة for في بايثون عند شرط؟', 'choice', '["break","stop","exit","return"]', 'break', 2, '9-11', 6),
        ('حلقة لا نهائية', 'حلقات', 'ما الخطر الشائع عند while بدون تحديث للشرط؟', 'choice', '["حلقة لا نهائية","حذف الذاكرة","تسريع الجهاز","إغلاق الشبكة"]', 'حلقة لا نهائية', 2, '12+', 8),
        ('تكرار نص', 'حلقات', 'في بايثون، كم مرة يُنفّذ الجسم إذا كتبت for i in range(3):؟', 'choice', '["3","2","4","0"]', '3', 1, '6-8', 4),
        ('شرط متعدد', 'منطق', 'إذا كان العمر أكبر من 12 والدرجة أكبر من 50، نطبع «نجح». أي عامل منطقي يربط الشرطين؟', 'choice', '["and","or","not","xor"]', 'and', 2, '12+', 8),
        ('قيمة المنطق', 'منطق', 'ما ناتج True and False في بايثون؟', 'choice', '["False","True","خطأ","لا يُعرّف"]', 'False', 2, '9-11', 5),
        ('عكس الشرط', 'منطق', 'ما ناتج not True؟', 'choice', '["False","True","0","1"]', 'False', 1, '6-8', 4),
        ('شجرة القرار', 'منطق', 'أي بنية تستخدم لاتخاذ قرار بين أكثر من مسارين؟', 'choice', '["if / elif / else","print فقط","import","comment"]', 'if / elif / else', 2, '12+', 9),
        ('مقارنة', 'منطق', 'في بايثون، هل 5 == 5.0؟', 'true_false', '["صح","خطأ"]', 'صح', 2, '9-11', 6),
        ('دالة الإخراج', 'اختيار', 'ما الدالة المعيارية لطباعة نص في بايثون 3؟', 'choice', '["print()","echo()","cout()","display()"]', 'print()', 1, '6-8', 5),
        ('تعليق', 'اختيار', 'ما الرمز لبدء تعليق سطر واحد في بايثون؟', 'choice', '["#","//","/*","--"]', '#', 1, '9-11', 6),
        ('استيراد', 'اختيار', 'ما الكلمة المفتاحية لاستيراد وحدة في بايثون؟', 'choice', '["import","include","using","require"]', 'import', 2, '12+', 9),
        ('قيمة الإرجاع', 'اختيار', 'دالة بدون return صريح في بايثون ترجع غالباً؟', 'choice', '["None","0","False","undefined"]', 'None', 2, '12+', 10),
        ('ترتيب: خطوات الطباعة', 'ترتيب', 'رتّب خطوات تشغيل برنامج بايثون من الملف.', 'order', '["احفظ الملف","افتح الطرفية","نفّذ python الملف"]', '["احفظ الملف","افتح الطرفية","نفّذ python الملف"]', 2, '12+', 10),
        ('متغير العداد', 'متغيرات', 'في حلقة، الاسم الشائع لمتغير العدّ هو؟', 'choice', '["i أو n","x فقط","لا يوجد","file"]', 'i أو n', 1, '9-11', 4),
        ('سلسلة نصية', 'متغيرات', 'ما علامات تنصيص السلسلة النصية في بايثون؟', 'choice', '["علامات تنصيص مفردة أو مزدوجة أو ثلاثية","فقط +","فقط *","لا يوجد"]', 'علامات تنصيص مفردة أو مزدوجة أو ثلاثية', 2, '12+', 7),
        ('حلقة while', 'حلقات', 'متى تُفضّل while على for؟', 'choice', '["عندما لا نعرف عدد التكرارات مسبقاً","دائماً","أبداً","للطباعة فقط"]', 'عندما لا نعرف عدد التكرارات مسبقاً', 2, '12+', 9),
        ('منطق الترتيب', 'منطق', 'هل يمكن تنفيذ else بعد while في بايثون؟', 'true_false', '["صح","خطأ"]', 'صح', 3, '12+', 10),
        ('اختيار: التعليمات', 'اختيار', 'ما الهدف من تعليمات المشروع في بيئة تعليمية؟', 'choice', '["توضيح المطلوب وتقييم الفهم","زيادة حجم الملف","إبطاء البرنامج","إخفاء الأخطاء"]', 'توضيح المطلوب وتقييم الفهم', 1, '6-8', 3),
    ]
    for row in extra:
        cursor.execute('SELECT 1 FROM exercises WHERE title = ?', (row[0],))
        if cursor.fetchone():
            continue
        cursor.execute('''
            INSERT INTO exercises (title, category, description, question_type, content, correct_answer, difficulty, min_age_bracket, stage_number)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', row)
    conn.commit()
    conn.close()


def append_more_motivational_phrases():
    conn = get_db()
    cursor = conn.cursor()
    extra = [
        'الخوارزمية هي وصفة واضحة — كل خطوة لها مكانها وزمنها.',
        'التفكير التجريدي يبدأ بتمثيل المشكلة بكلمات وبسيطة قبل الكود.',
        'تقسيم المشكلة إلى أجزاء صغيرة يجعل البرمجة أسهل على العقل والوقت.',
        'الاختبار المبكر يكشف الأخطاء قبل أن تتراكم.',
        'قراءة رسالة الخطأ في بايثون تلميح مباشر نحو الحل.',
        'الأسماء الوصفية للمتغيرات توفر وقتاً عند العودة للمشروع لاحقاً.',
        'الحلقات المرتبطة بالشروط تبني عادات التفكير في الحالات الحدية.',
        'التعلم بالمشاريع الصغيرة يعزز الثقة ثم يوسّع الطموح البرمجي.',
        'التعاون على مراجعة الكود يعلّم أنماطاً جديدة ويقلّل الأخطاء.',
        'الأمان في البرمجة يبدأ بفهم المدخلات وعدم الثقة العمياء بالمستخدم.',
        'الترتيب الصحيح للأوامر يعكس تسلسل الزمن في العالم الحقيقي.',
        'كل تمرين يحلّه الطفل يعزز ربط المفاهيم بالتطبيق.',
        'الصبر مع الأخطاء المنطقية مهارة أساسية لكل مبرمج.',
        'المنصات العالمية تبني على أساسيات كالتي تتعلمها هنا اليوم.',
        'احتفل بالتقدم الصغير — الشارات تعكس مساراً حقيقياً لا مجرد أرقاماً.',
    ]
    for p in extra:
        cursor.execute('SELECT 1 FROM motivational_phrases WHERE phrase = ?', (p,))
        if not cursor.fetchone():
            cursor.execute('INSERT INTO motivational_phrases (phrase) VALUES (?)', (p,))
    conn.commit()
    conn.close()


def append_deep_content():
    conn = get_db()
    cursor = conn.cursor()
    extra = [
        ('صباح المدرسة', 'ترتيب', 'رتّب خطوات الاستعداد للخروج بترتيب منطقي.', 'order', '["ارتدِ الملابس","تناول الفطور","جهّز الحقيبة","اخرج من الباب"]', '["ارتدِ الملابس","تناول الفطور","جهّز الحقيبة","اخرج من الباب"]', 1, '6-8', 11),
        ('زراعة نبتة', 'ترتيب', 'ما الترتيب الصحيح لزراعة بذرة في أصيص؟', 'order', '["املأ التربة","اغرس البذرة","اسقِ قليلاً","ضعها في الضوء"]', '["املأ التربة","اغرس البذرة","اسقِ قليلاً","ضعها في الضوء"]', 1, '6-8', 11),
        ('تنظيف الغرفة', 'ترتيب', 'رتّب خطوات تنظيم غرفة بسيطة.', 'order', '["اجمع الألعاب","رتّب الكتب","امسح السطح","رتّب السرير"]', '["اجمع الألعاب","رتّب الكتب","امسح السطح","رتّب السرير"]', 2, '6-8', 12),
        ('رحلة إلى الحديقة', 'ترتيب', 'من البيت إلى الحديقة — ترتيب معقول.', 'order', '["ارتدِ الحذاء","اغلق الباب","امشِ للحديقة","استمتع باللعب"]', '["ارتدِ الحذاء","اغلق الباب","امشِ للحديقة","استمتع باللعب"]', 2, '9-11', 12),
        ('تخطيط مشروع صفي', 'ترتيب', 'مراحل عمل جماعي في الصف.', 'order', '["قسّم المهام","نفّذ كل جزء","ادمج النتائج","اعرض أمام الصف"]', '["قسّم المهام","نفّذ كل جزء","ادمج النتائج","اعرض أمام الصف"]', 2, '9-11', 13),
        ('نشر موقع بسيط', 'ترتيب', 'ترتيب تقني مبسّط لنشر صفحة.', 'order', '["اكتب المحتوى","اختبر محلياً","ارفع للخادم","راقب الأعطال"]', '["اكتب المحتوى","اختبر محلياً","ارفع للخادم","راقب الأعطال"]', 3, '12+', 13),
        ('تحليل بيانات', 'ترتيب', 'خطوات أولية لتحليل مجموعة أرقام.', 'order', '["اجمع البيانات","نظّفها","احسب المتوسط","استنتج"]', '["اجمع البيانات","نظّفها","احسب المتوسط","استنتج"]', 3, '12+', 14),
        ('متغير للعدد', 'متغيرات', 'لحفظ عدد التفاحات في سلة، أي اسم أنسب؟', 'choice', '["apple_count","x","a1","العدد"]', 'apple_count', 1, '6-8', 11),
        ('نوع الرقم الصحيح', 'متغيرات', 'في بايثون، الرقم 42 بدون فاصلة عشريّة غالباً يُعرّف كـ؟', 'choice', '["int","float","str","bool"]', 'int', 2, '9-11', 12),
        ('سلسلة فارغة', 'متغيرات', 'ما القيمة الافتراضية لسلسلة نصية جديدة فارغة؟', 'choice', '["\"\"","None","0","[]"]', '""', 2, '9-11', 13),
        ('قائمة من أرقام', 'متغيرات', 'ما النوع إذا كتبت [1, 2, 3] في بايثون؟', 'choice', '["list","tuple","set","dict"]', 'list', 2, '12+', 13),
        ('نطاق عام', 'متغيرات', 'متغير يُعرّف في أعلى الملف خارج الدوال يكون عادةً؟', 'choice', '["على مستوى الوحدة (ملف)","محلي دائماً","مخفياً","ثابتاً فقط"]', 'على مستوى الوحدة (ملف)', 3, '12+', 14),
        ('حلقة على قائمة', 'حلقات', 'لطباعة كل عنصر في قائمة أسماء، أي بنية أنسب؟', 'choice', '["for name in names:","while names:","if names:","print(names) فقط"]', 'for name in names:', 2, '9-11', 12),
        ('عدّ تنازلي', 'حلقات', 'لعدّ من 5 إلى 1 بالطباعة، ما الفكرة العامة؟', 'choice', '["حلقة مع متغير ينقص","حلقة لا نهائية","دالة واحدة فقط","تعليق فقط"]', 'حلقة مع متغير ينقص', 2, '12+', 14),
        ('تكرار حتى شرط', 'حلقات', 'متى نستخدم while بدلاً من for؟', 'choice', '["عندما يعتمد التوقف على شرط ديناميكي","دائماً","أبداً","للطباعة فقط"]', 'عندما يعتمد التوقف على شرط ديناميكي', 3, '12+', 15),
        ('شرط داخل حلقة', 'منطق', 'لتخطي عنصراً في حلقة for عند شرط، نستخدم غالباً؟', 'choice', '["continue","break فقط","pass فقط","import"]', 'continue', 2, '9-11', 13),
        ('دمج شرطين', 'منطق', 'نريد النجاح إذا (الدرجة ≥ 50) أو (المشروع مكتمل). أي عامل؟', 'choice', '["or","and","not","xor"]', 'or', 2, '12+', 14),
        ('قيمة منطقية', 'منطق', 'ما ناتج (True or False) and False؟', 'choice', '["False","True","خطأ","غير معرّف"]', 'False', 2, '12+', 15),
        ('مقارنة سلاسل', 'منطق', 'في بايثون، هل "ب" > "أ" عادةً (ترتيب معجمي)؟', 'true_false', '["صح","خطأ"]', 'صح', 2, '9-11', 12),
        ('دالة مساعدة', 'اختيار', 'ما الهدف من تقسيم الكود إلى دوال صغيرة؟', 'choice', '["إعادة الاستخدام والوضوح","زيادة الأخطاء","إطالة الملف فقط","منع التعليقات"]', 'إعادة الاستخدام والوضوح', 2, '9-11', 11),
        ('تعليق توضيحي', 'اختيار', 'متى يكون التعليق في الكود مفيداً؟', 'choice', '["عند شرح «لماذا» وليس فقط «ماذا»","دائماً على كل سطر","أبداً","لإخفاء الكود"]', 'عند شرح «لماذا» وليس فقط «ماذا»', 2, '12+', 12),
        ('ترتيب: تصحيح خطأ', 'ترتيب', 'رتّب خطوات التعامل مع خطأ في برنامج.', 'order', '["اقرأ الرسالة","حدّد السطر","صحّح","شغّل مجدداً"]', '["اقرأ الرسالة","حدّد السطر","صحّح","شغّل مجدداً"]', 2, '12+', 15),
        ('خوارزمية البحث اليدوي', 'ترتيب', 'في قائمة ورقية، البحث عن رقم — خطوات مرتبة.', 'order', '["ابدأ من أول عنصر","قارن","إن لم يوجد انتقل","كرر حتى النهاية"]', '["ابدأ من أول عنصر","قارن","إن لم يوجد انتقل","كرر حتى النهاية"]', 3, '12+', 16),
        ('متغير منطقي', 'متغيرات', 'لتخزين هل انتهى التمرين، أنسب نوع غالباً؟', 'choice', '["bool","str","float","list"]', 'bool', 1, '6-8', 12),
        ('حلقة مرسومة', 'حلقات', 'لرسم مثلث من نجوم بارتفاع 4، غالباً نحتاج حلقة؟', 'choice', '["خارجية وداخلية","واحدة فقط","لا حلقات","تعليق فقط"]', 'خارجية وداخلية', 3, '12+', 16),
        ('منطق الألعاب', 'منطق', 'في لعبة: إذا نفدت الحياة انتهت الجلسة. هذا يشبه؟', 'choice', '["شرط إيقاف","تعليق","استيراد","طباعة فقط"]', 'شرط إيقاف', 1, '6-8', 11),
        ('تسلسل فيديو قصير', 'ترتيب', 'إنتاج مقطع تعليمي قصير — ترتيب منطقي.', 'order', '["اكتب النص","سجّل الصوت","اضبط الصورة","صدّر الملف"]', '["اكتب النص","سجّل الصوت","اضبط الصورة","صدّر الملف"]', 2, '9-11', 14),
        ('مهمة روبوت متقدمة', 'ترتيب', 'الروبوت يجمع قطعاً: تقدّم، التقط، تقدّم، أفرغ.', 'order', '["تقدّم","التقط","تقدّم","أفرغ في الصندوق"]', '["تقدّم","التقط","تقدّم","أفرغ في الصندوق"]', 2, '9-11', 13),
        ('مشروع Scratch مفاهيمي', 'اختيار', 'أي مفهوم يربط «الرسائل» بين كائنين في سكراتش؟', 'choice', '["بث واستقبال","حلقة فقط","لون الخلفية","حجم النافذة"]', 'بث واستقبال', 2, '6-8', 12),
        ('أمان كلمات المرور', 'اختيار', 'ما السلوك الأفضل لكلمة مرور حساب تعليمي؟', 'choice', '["فريدة ولا تُشارك","بسيطة جداً للجميع","نفسها لكل المواقع","تُكتب على اللوحة"]', 'فريدة ولا تُشارك', 2, '12+', 11),
        ('بيانات وخصوصية', 'منطق', 'لماذا لا نشارك معلومات شخصية في دردشة عامة؟', 'choice', '["لحماية الخصوصية والأمان","لزيادة السرعة","لأن الكود يمنع","لا سبب"]', 'لحماية الخصوصية والأمان', 2, '9-11', 11),
        ('هيكلة برنامج', 'اختيار', 'أي ملف يُنصح أن يكون نقطة الدخول في مشروع بايثون صغير؟', 'choice', '["main.py أو ما يعادله","ملف بدون اسم","صورة فقط","مجلد فارغ"]', 'main.py أو ما يعادله', 2, '12+', 14),
        ('تعابير منطقية', 'منطق', 'ما ناتج not (False or True)؟', 'choice', '["False","True","خطأ","صفر"]', 'False', 2, '12+', 16),
        ('قائمة الأوامر', 'ترتيب', 'ترتيب تنفيذ أوامر في محرر بلوكات.', 'order', '["اسحب الأمر","أفلته في التسلسل","اضبط الأرقام","شغّل"]', '["اسحب الأمر","أفلته في التسلسل","اضبط الأرقام","شغّل"]', 1, '6-8', 13),
        ('تعلم من الخطأ', 'اختيار', 'بعد إجابة خاطئة، أفضل أسلوب تعلّم هو؟', 'choice', '["قراءة التوضيح وإعادة المحاولة","تجاهل التمرين","نسخ عشوائي","إغلاق البرنامج"]', 'قراءة التوضيح وإعادة المحاولة', 1, '6-8', 11),
        ('تنسيق النصوص', 'متغيرات', 'لدمج اسم مع ترحيب في بايثون نستخدم غالباً؟', 'choice', '["f-string أو +","فقط print بدون متغيرات","//","/*"]', 'f-string أو +', 2, '12+', 12),
        ('حدث تحدي', 'اختيار', 'عند حل تمرين صحيح، ماذا يعكس سجلّ التحديات في المنصة؟', 'choice', '["تقدّماً يمكن ربطه بالجوائز والشارات","لا شيء","فقط لون الخلفية","عدد النوافذ"]', 'تقدّماً يمكن ربطه بالجوائز والشارات', 1, '9-11', 11),
    ]
    for row in extra:
        cursor.execute('SELECT 1 FROM exercises WHERE title = ?', (row[0],))
        if cursor.fetchone():
            continue
        cursor.execute('''
            INSERT INTO exercises (title, category, description, question_type, content, correct_answer, difficulty, min_age_bracket, stage_number)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', row)
    conn.commit()
    conn.close()


def seed_exercises():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as c FROM exercises')
    if cursor.fetchone()['c'] > 0:
        conn.close()
        return
    exercises_data = [
        ('رتب الأوامر', 'ترتيب', 'رتب الأوامر التالية لطباعة الرسالة', 'order', '["افتح الملف","اكتب الرسالة","أغلق الملف"]', '["افتح الملف","اكتب الرسالة","أغلق الملف"]', 1, '6-8', 1),
        ('أي ترتيب صحيح؟', 'ترتيب', 'اختر الترتيب الصحيح لإعداد سندويتش', 'order', '["ضع الخبز","أضف الجبن","ضع الخبز الآخر"]', '["ضع الخبز","أضف الجبن","ضع الخبز الآخر"]', 1, '6-8', 1),
        ('اكتب الترتيب', 'ترتيب', 'ما الترتيب الصحيح لتحضير العصير؟', 'choice', '["اعصر البرتقال","اسكب في الكوب","اشرب"]', '["اعصر البرتقال","اسكب في الكوب","اشرب"]', 1, '6-8', 2),
        ('المتغير والاسم', 'متغيرات', 'اختر الاسم المناسب لمتغير يخزن العمر', 'choice', '["age","x","var1","123"]', 'age', 1, '6-8', 2),
        ('نوع المتغير', 'متغيرات', 'ما نوع البيانات التي يخزنها المتغير؟', 'choice', '["نص","رقم","منطقي"]', 'رقم', 2, '9-11', 3),
        ('تكرار مع حلقات', 'حلقات', 'كم مرة نكرر الأمر لرسم مربع؟', 'choice', '["2","3","4","5"]', '4', 2, '6-8', 3),
        ('حلقة مناسبة', 'حلقات', 'أي حلقة تناسب تكرار 10 مرات؟', 'choice', '["for","while","repeat"]', 'repeat', 2, '9-11', 4),
        ('صحيح أم خاطئ', 'منطق', 'هل الترتيب: ابدأ ثم أنهِ هو الترتيب الصحيح؟', 'true_false', '["صح","خطأ"]', 'صح', 1, '6-8', 4),
        ('منطق البرنامج', 'منطق', 'إذا كان الشرط صحيحاً نفذ الأمر. هل هذا صحيح؟', 'true_false', '["صح","خطأ"]', 'صح', 2, '9-11', 5),
        ('اختر الصحيح', 'اختيار', 'ما الأمر الصحيح لتحريك الروبوت للأمام؟', 'choice', '["forward()","go()","move()"]', 'forward()', 1, '6-8', 5),
        ('تسلسل الروبوت', 'ترتيب', 'رتّب أوامر الروبوت للوصول للهدف', 'order', '["انطلق","انعطف يميناً","توقف"]', '["انطلق","انعطف يميناً","توقف"]', 2, '9-11', 6),
        ('متغير المسافة', 'متغيرات', 'اختر اسماً مناسباً لمسافة الرحلة', 'choice', '["distance","d","مسافة","123dist"]', 'distance', 2, '12+', 6),
        ('حلقة العد', 'حلقات', 'كم مرة نكرر لطباعة الأرقام 1 إلى 5؟', 'choice', '["3","4","5","6"]', '5', 2, '12+', 7),
        ('شرط منطقي', 'منطق', 'هل «و» تعني أن الشرطين يجب أن يكونا صحيحين معاً؟', 'true_false', '["صح","خطأ"]', 'صح', 2, '12+', 7),
        ('دالة بسيطة', 'اختيار', 'ما الذي يمثل «إدخال» من المستخدم؟', 'choice', '["input()","print()","start()"]', 'input()', 2, '12+', 8),
    ]
    for ex in exercises_data:
        cursor.execute('''
            INSERT INTO exercises (title, category, description, question_type, content, correct_answer, difficulty, min_age_bracket, stage_number)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', ex)
    conn.commit()
    conn.close()


@app.route('/')
def serve_index():
    return send_from_directory(ROOT_DIR, 'index.html')


@app.route('/<page>')
def serve_html_page(page):
    if page in _HTML_PAGES:
        return send_from_directory(ROOT_DIR, page)
    abort(404)


def bootstrap_database():
    init_db()
    migrate_db()
    seed_exercises()
    append_rich_exercises()
    append_deep_content()
    append_more_motivational_phrases()
    seed_badges_and_phrases()
    seed_demo_users()


bootstrap_database()


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
