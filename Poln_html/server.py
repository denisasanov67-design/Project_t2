from flask import Flask, request, jsonify, send_from_directory
import sqlite3
import hashlib
import os
import csv
from io import StringIO
from datetime import datetime
import json

# Для Google Sheets
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__, static_folder='static', static_url_path='')

# Настройка Google Sheets
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SERVICE_ACCOUNT_FILE = 'credentials.json'  # Файл с ключами сервисного аккаунта
SPREADSHEET_ID = None  # ID вашей Google таблицы

# При экспорте
def calculate_hours(start_time, end_time):
    if not start_time or not end_time or start_time == 'Выходной':
        return 0
    
    start = datetime.strptime(start_time, '%H:%M')
    end = datetime.strptime(end_time, '%H:%M')
    
    if end < start:
        end += timedelta(days=1)
    
    return (end - start).total_seconds() / 3600
def get_google_sheet():
    """Подключение к Google Sheets"""
    try:
        if os.path.exists(SERVICE_ACCOUNT_FILE):
            creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
            client = gspread.authorize(creds)
            return client
    except Exception as e:
        print(f"Ошибка подключения к Google Sheets: {e}")
    return None

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  password TEXT NOT NULL,
                  role TEXT NOT NULL,
                  full_name TEXT NOT NULL,
                  department TEXT,
                  status TEXT DEFAULT 'pending',
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS shifts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  date TEXT NOT NULL,
                  start_time TEXT NOT NULL,
                  end_time TEXT,
                  status TEXT DEFAULT 'pending',
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  google_sync BOOLEAN DEFAULT 0,
                  FOREIGN KEY (user_id) REFERENCES users (id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS settings
                 (key TEXT PRIMARY KEY,
                  value TEXT)''')
    
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        admin_pass = hashlib.sha256("admin123".encode()).hexdigest()
        manager_pass = hashlib.sha256("manager123".encode()).hexdigest()
        emp1_pass = hashlib.sha256("emp123".encode()).hexdigest()
        emp2_pass = hashlib.sha256("emp456".encode()).hexdigest()
        
        users = [
            ("admin", admin_pass, "admin", "Администратор Системы", "IT", "approved"),
            ("manager", manager_pass, "manager", "Петров Иван Сергеевич", "Управление", "approved"),
            ("employee1", emp1_pass, "employee", "Иванов Алексей Петрович", "Продажи", "approved"),
            ("employee2", emp2_pass, "employee", "Смирнова Елена Викторовна", "Маркетинг", "approved"),
        ]
        c.executemany("INSERT INTO users (username, password, role, full_name, department, status) VALUES (?, ?, ?, ?, ?, ?)", users)
    c.execute('''CREATE TABLE IF NOT EXISTS user_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  action TEXT NOT NULL,
                  old_department_id INTEGER,
                  new_department_id INTEGER,
                  old_organization_id INTEGER,
                  new_organization_id INTEGER,
                  changed_by INTEGER,
                  changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (user_id) REFERENCES users(id),
                  FOREIGN KEY (changed_by) REFERENCES users(id))''')
    conn.commit()
    conn.close()
    print("✓ База данных инициализирована")

def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# === GOOGLE SHEETS API ===

@app.route('/api/google/settings', methods=['POST'])
def save_google_settings():
    """Сохранение настроек Google Sheets"""
    data = request.get_json()
    conn = get_db()
    c = conn.cursor()
    
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
              ('spreadsheet_id', data.get('spreadsheet_id', '')))
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
              ('auto_sync', data.get('auto_sync', 'false')))
    conn.commit()
    conn.close()
    
    global SPREADSHEET_ID
    SPREADSHEET_ID = data.get('spreadsheet_id')
    
    return jsonify({'success': True})

@app.route('/api/google/settings', methods=['GET'])
def get_google_settings():
    """Получение настроек Google Sheets"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT key, value FROM settings WHERE key IN ('spreadsheet_id', 'auto_sync')")
    settings = {row['key']: row['value'] for row in c.fetchall()}
    conn.close()
    return jsonify(settings)

@app.route('/api/google/sync', methods=['POST'])
def sync_to_google_sheets():
    """Синхронизация данных с Google Таблицей"""
    try:
        client = get_google_sheet()
        if not client:
            return jsonify({'success': False, 'error': 'Google Sheets не настроен'}), 400
        
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key = 'spreadsheet_id'")
        row = c.fetchone()
        if not row or not row['value']:
            conn.close()
            return jsonify({'success': False, 'error': 'Не указан ID таблицы'}), 400
        
        spreadsheet_id = row['value']
        
        # Получаем все смены
        c.execute("""
            SELECT u.full_name, u.department, s.date, s.start_time, s.end_time, s.status, s.id
            FROM shifts s 
            JOIN users u ON s.user_id = u.id 
            ORDER BY s.date DESC
        """)
        shifts = c.fetchall()
        
        # Открываем таблицу
        spreadsheet = client.open_by_key(spreadsheet_id)
        
        # Проверяем существование листа, если нет - создаем
        sheet_name = datetime.now().strftime("График %Y-%m")
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
        except:
            worksheet = spreadsheet.add_worksheet(title=sheet_name, rows="1000", cols="20")
        
        # Подготавливаем данные
        headers = ['Сотрудник', 'Отдел', 'Дата', 'Начало', 'Конец', 'Статус', 'Последнее обновление']
        worksheet.clear()
        worksheet.update('A1:G1', [headers])
        
        if shifts:
            data = []
            for shift in shifts:
                data.append([
                    shift['full_name'],
                    shift['department'] or '-',
                    shift['date'],
                    shift['start_time'],
                    shift['end_time'] or '-',
                    shift['status'],
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ])
            
            worksheet.update(f'A2:G{len(data)+1}', data)
            
            # Форматирование
            worksheet.format('A1:G1', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.38, 'green': 0, 'blue': 0.92}  # #6200ea
            })
        
        # Отмечаем синхронизированные записи
        for shift in shifts:
            c.execute("UPDATE shifts SET google_sync = 1 WHERE id = ?", (shift['id'],))
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True, 
            'message': f'Синхронизировано {len(shifts)} записей',
            'sheet_url': f'https://docs.google.com/spreadsheets/d/{spreadsheet_id}'
        })
        
    except Exception as e:
        print(f"Ошибка синхронизации: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/google/auto-sync', methods=['POST'])
def toggle_auto_sync():
    """Включение/выключение автосинхронизации"""
    data = request.get_json()
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('auto_sync', ?)",
              (str(data.get('enabled', False)).lower(),))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# === АВТОРИЗАЦИЯ ===
@app.route('/api/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return '', 200
        
    data = request.get_json()
    conn = get_db()
    c = conn.cursor()
    
    hashed = hashlib.sha256(data['password'].encode()).hexdigest()
    c.execute("SELECT * FROM users WHERE username = ? AND password = ? AND status = 'approved'", 
              (data['username'], hashed))
    user = c.fetchone()
    conn.close()
    
    if user:
        user_dict = dict(user)
        return jsonify({
            'success': True,
            'user_id': user_dict['id'],
            'username': user_dict['username'],
            'role': user_dict['role'],
            'full_name': user_dict['full_name'],
            'department': user_dict.get('department', '')
        })
    return jsonify({'success': False, 'error': 'Неверный логин/пароль или аккаунт не подтвержден'}), 401

@app.route('/api/register', methods=['POST', 'OPTIONS'])
def register():
    if request.method == 'OPTIONS':
        return '', 200
        
    try:
        data = request.get_json()
        conn = get_db()
        c = conn.cursor()
        
        hashed = hashlib.sha256(data['password'].encode()).hexdigest()
        c.execute("INSERT INTO users (username, password, role, full_name, department, status) VALUES (?, ?, ?, ?, ?, ?)",
                  (data['username'], hashed, data['role'], data['full_name'], data.get('department', ''), 'pending'))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Заявка на регистрацию отправлена администратору'})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'error': 'Пользователь уже существует'}), 400

# === ПОЛЬЗОВАТЕЛИ ===
@app.route('/api/users', methods=['GET'])
def get_all_users():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, username, full_name, role, department, status, created_at FROM users ORDER BY created_at DESC")
    users = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(users)

@app.route('/api/users/pending', methods=['GET'])
def get_pending_users():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, username, full_name, role, department, created_at FROM users WHERE status = 'pending' ORDER BY created_at")
    users = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(users)

@app.route('/api/users/<int:user_id>/approve', methods=['PUT'])
def approve_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET status = 'approved' WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/users/<int:user_id>/reject', methods=['PUT'])
def reject_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id = ? AND status = 'pending'", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# === СМЕНЫ ===
@app.route('/api/employees', methods=['GET'])
def get_employees():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, username, full_name, role, department FROM users WHERE role = 'employee' AND status = 'approved'")
    employees = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(employees)

@app.route('/api/shifts', methods=['GET', 'POST', 'OPTIONS'])
def shifts():
    if request.method == 'OPTIONS':
        return '', 200
        
    conn = get_db()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    if request.method == 'GET':
        user_id = request.args.get('user_id')
        if user_id:
            c.execute("SELECT * FROM shifts WHERE user_id = ? ORDER BY date", (user_id,))
        else:
            c.execute("""
                SELECT s.*, u.full_name, u.department 
                FROM shifts s 
                JOIN users u ON s.user_id = u.id 
                WHERE u.status = 'approved'
                ORDER BY s.date
            """)
        shifts_data = [dict(row) for row in c.fetchall()]
        conn.close()
        return jsonify(shifts_data)
    
    elif request.method == 'POST':
        data = request.get_json()
        c.execute("INSERT INTO shifts (user_id, date, start_time, end_time, status) VALUES (?, ?, ?, ?, ?)",
                  (data['user_id'], data['date'], data['start_time'], data.get('end_time'), 'pending'))
        conn.commit()
        shift_id = c.lastrowid
        
        # Проверяем автосинхронизацию
        c.execute("SELECT value FROM settings WHERE key = 'auto_sync'")
        row = c.fetchone()
        conn.close()
        
        if row and row['value'] == 'true':
            # Автоматическая синхронизация в фоне
            sync_to_google_sheets()
        
        return jsonify({'success': True, 'shift_id': shift_id})

@app.route('/api/shifts/<int:shift_id>', methods=['DELETE', 'OPTIONS'])
def delete_shift(shift_id):
    if request.method == 'OPTIONS':
        return '', 200
        
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM shifts WHERE id = ?", (shift_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/shifts/<int:shift_id>/status', methods=['PUT', 'OPTIONS'])
def update_shift_status(shift_id):
    if request.method == 'OPTIONS':
        return '', 200
        
    data = request.get_json()
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE shifts SET status = ? WHERE id = ?", (data['status'], shift_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# === СТАТИСТИКА ===
@app.route('/api/stats')
def get_stats():
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM users WHERE role = 'employee' AND status = 'approved'")
    total_employees = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM shifts")
    total_shifts = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM shifts WHERE status = 'pending'")
    pending_shifts = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM shifts WHERE status = 'approved'")
    approved_shifts = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM shifts WHERE status = 'rejected'")
    rejected_shifts = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM users WHERE status = 'pending'")
    pending_users = c.fetchone()[0]
    
    c.execute("""
        SELECT u.department, COUNT(s.id) as count 
        FROM users u 
        LEFT JOIN shifts s ON u.id = s.user_id 
        WHERE u.role = 'employee' AND u.status = 'approved'
        GROUP BY u.department
        HAVING u.department IS NOT NULL AND u.department != ''
    """)
    by_department = [dict(row) for row in c.fetchall()]
    
    conn.close()
    
    return jsonify({
        'total_employees': total_employees,
        'total_shifts': total_shifts,
        'pending_shifts': pending_shifts,
        'approved_shifts': approved_shifts,
        'rejected_shifts': rejected_shifts,
        'pending_users': pending_users,
        'by_department': by_department
    })

# === ЭКСПОРТ ===
@app.route('/api/export/csv')
def export_csv():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT u.full_name, u.department, s.date, s.start_time, s.end_time, s.status 
        FROM shifts s 
        JOIN users u ON s.user_id = u.id 
        ORDER BY s.date, u.full_name
    """)
    shifts = c.fetchall()
    conn.close()
    
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Сотрудник', 'Отдел', 'Дата', 'Начало смены', 'Конец смены', 'Статус'])
    
    for shift in shifts:
        cw.writerow([
            shift['full_name'],
            shift['department'] or '-',
            shift['date'],
            shift['start_time'],
            shift['end_time'] or '-',
            shift['status']
        ])
    
    output = si.getvalue()
    si.close()
    
    return output, 200, {
        'Content-Type': 'text/csv; charset=utf-8',
        'Content-Disposition': f'attachment; filename=shifts_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    }

@app.route('/')
def index():
    return send_from_directory('static', 'login.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

if __name__ == '__main__':
    if os.path.exists('database.db'):
        os.remove('database.db')
        print("Старая БД удалена")
    
    init_db()
    print("\n" + "="*50)
    print("🚀 T2 Пульс запущен!")
    print("📍 http://localhost:5000")
    print("="*50 + "\n")
    app.run(host='0.0.0.0', port=5000, debug=True)


def check_consecutive_shifts(user_id, new_date, new_start_time):
    """
    Проверяет, не будет ли превышен лимит в 6 смен подряд
    Возвращает (can_add, current_consecutive, max_allowed)
    """
    if new_start_time == 'Выходной':
        return True, 0, 6
    
    conn = get_db()
    c = conn.cursor()
    
    # Получаем все рабочие смены сотрудника за последние 30 дней
    c.execute("""
        SELECT date FROM shifts 
        WHERE user_id = ? AND start_time != 'Выходной'
        ORDER BY date
    """, (user_id,))
    
    dates = [row[0] for row in c.fetchall()]
    
    # Добавляем новую дату
    if new_date not in dates:
        dates.append(new_date)
    
    dates.sort()
    
    # Считаем максимальное количество подряд
    max_consecutive = 0
    current_consecutive = 0
    last_date = None
    
    for date_str in dates:
        current_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        if last_date:
            diff = (current_date - last_date).days
            if diff == 1:
                current_consecutive += 1
            else:
                current_consecutive = 1
        else:
            current_consecutive = 1
        
        max_consecutive = max(max_consecutive, current_consecutive)
        last_date = current_date
    
    conn.close()
    
    return max_consecutive <= 6, max_consecutive, 6


@app.route('/api/users/<int:user_id>/move', methods=['PUT'])
def move_employee(user_id):
    """
    Перемещение сотрудника в другой отдел/организацию
    """
    data = request.get_json()
    new_department_id = data.get('department_id')
    new_organization_id = data.get('organization_id')
    
    conn = get_db()
    c = conn.cursor()
    
    # Проверяем существование пользователя
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'success': False, 'error': 'Пользователь не найден'}), 404
    
    # Проверяем существование отдела
    if new_department_id:
        c.execute("SELECT * FROM departments WHERE id = ?", (new_department_id,))
        dept = c.fetchone()
        if not dept:
            conn.close()
            return jsonify({'success': False, 'error': 'Отдел не найден'}), 404
        
        # Обновляем организацию если нужно
        if new_organization_id:
            c.execute("UPDATE users SET organization_id = ?, department_id = ? WHERE id = ?",
                      (new_organization_id, new_department_id, user_id))
        else:
            c.execute("UPDATE users SET department_id = ? WHERE id = ?",
                      (new_department_id, user_id))
    elif new_organization_id:
        c.execute("UPDATE users SET organization_id = ?, department_id = NULL WHERE id = ?",
                  (new_organization_id, user_id))
    
    conn.commit()
    
    # Логируем перемещение
    c.execute("""
        INSERT INTO user_history (user_id, action, old_department_id, new_department_id, changed_by, changed_at)
        VALUES (?, 'move', ?, ?, ?, ?)
    """, (user_id, user['department_id'], new_department_id, request.headers.get('User-Id'), datetime.now()))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'message': '✅ Сотрудник перемещен',
        'old_department': user['department_id'],
        'new_department': new_department_id
    })

@app.route('/api/users/<int:user_id>/history', methods=['GET'])
def get_user_history(user_id):
    """
    История перемещений сотрудника
    """
    conn = get_db()
    c = conn.cursor()
    
    c.execute("""
        SELECT h.*, 
               d1.name as old_dept_name,
               d2.name as new_dept_name,
               u.full_name as changed_by_name
        FROM user_history h
        LEFT JOIN departments d1 ON h.old_department_id = d1.id
        LEFT JOIN departments d2 ON h.new_department_id = d2.id
        LEFT JOIN users u ON h.changed_by = u.id
        WHERE h.user_id = ?
        ORDER BY h.changed_at DESC
    """, (user_id,))
    
    history = [dict(row) for row in c.fetchall()]
    conn.close()
    
    return jsonify(history)

@app.route('/api/departments/<int:dept_id>/employees', methods=['GET'])
def get_department_employees_full(dept_id):
    """
    Получение всех сотрудников отдела с возможностью перемещения
    """
    include_sub = request.args.get('include_sub', 'true').lower() == 'true'
    
    conn = get_db()
    c = conn.cursor()
    
    if include_sub:
        # Рекурсивно получаем все подотделы
        def get_sub_departments(dept_id):
            c.execute("SELECT id FROM departments WHERE parent_department_id = ?", (dept_id,))
            sub_depts = [row[0] for row in c.fetchall()]
            
            all_depts = [dept_id]
            for sub in sub_depts:
                all_depts.extend(get_sub_departments(sub))
            
            return all_depts
        
        all_dept_ids = get_sub_departments(dept_id)
        placeholders = ','.join('?' * len(all_dept_ids))
        
        c.execute(f"""
            SELECT u.*, d.name as department_name, o.name as organization_name
            FROM users u 
            JOIN departments d ON u.department_id = d.id
            JOIN organizations o ON u.organization_id = o.id
            WHERE u.department_id IN ({placeholders}) AND u.status = 'approved'
            ORDER BY u.full_name
        """, all_dept_ids)
    else:
        c.execute("""
            SELECT u.*, d.name as department_name, o.name as organization_name
            FROM users u 
            JOIN departments d ON u.department_id = d.id
            JOIN organizations o ON u.organization_id = o.id
            WHERE u.department_id = ? AND u.status = 'approved'
            ORDER BY u.full_name
        """, (dept_id,))
    
    employees = [dict(row) for row in c.fetchall()]
    conn.close()
    
    return jsonify(employees)

@app.route('/api/departments/transfer', methods=['POST'])
def bulk_transfer_employees():
    """
    Массовое перемещение сотрудников
    """
    data = request.get_json()
    user_ids = data.get('user_ids', [])
    new_department_id = data.get('department_id')
    
    if not user_ids or not new_department_id:
        return jsonify({'success': False, 'error': 'Не указаны сотрудники или отдел'}), 400
    
    conn = get_db()
    c = conn.cursor()
    
    # Проверяем существование отдела
    c.execute("SELECT id FROM departments WHERE id = ?", (new_department_id,))
    if not c.fetchone():
        conn.close()
        return jsonify({'success': False, 'error': 'Отдел не найден'}), 404
    
    # Перемещаем сотрудников
    placeholders = ','.join('?' * len(user_ids))
    c.execute(f"""
        UPDATE users 
        SET department_id = ? 
        WHERE id IN ({placeholders})
    """, [new_department_id] + user_ids)
    
    moved_count = c.rowcount
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'message': f'✅ Перемещено сотрудников: {moved_count}',
        'moved_count': moved_count
    })


# === ОРГАНИЗАЦИИ ===

@app.route('/api/organizations', methods=['GET'])
def get_organizations():
    """Получение списка всех организаций"""
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT o.*, 
               COUNT(DISTINCT d.id) as departments_count,
               COUNT(DISTINCT u.id) as employees_count
        FROM organizations o
        LEFT JOIN departments d ON o.id = d.organization_id
        LEFT JOIN users u ON o.id = u.organization_id
        GROUP BY o.id
        ORDER BY o.name
    """)
    orgs = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(orgs)

@app.route('/api/organizations', methods=['POST'])
def create_organization():
    """Создание новой организации"""
    data = request.get_json()
    name = data.get('name', '').strip()
    
    if not name:
        return jsonify({'success': False, 'error': 'Название обязательно'}), 400
    
    conn = get_db()
    c = conn.cursor()
    
    # Проверка на дубликат
    c.execute("SELECT id FROM organizations WHERE name = ?", (name,))
    if c.fetchone():
        conn.close()
        return jsonify({'success': False, 'error': 'Организация с таким названием уже существует'}), 400
    
    c.execute("INSERT INTO organizations (name) VALUES (?)", (name,))
    org_id = c.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'id': org_id, 'message': f'✅ Организация "{name}" создана'})

@app.route('/api/organizations/<int:org_id>', methods=['PUT'])
def update_organization(org_id):
    """Обновление организации"""
    data = request.get_json()
    name = data.get('name', '').strip()
    
    if not name:
        return jsonify({'success': False, 'error': 'Название обязательно'}), 400
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute("UPDATE organizations SET name = ? WHERE id = ?", (name, org_id))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': f'✅ Организация обновлена'})

@app.route('/api/organizations/<int:org_id>', methods=['DELETE'])
def delete_organization(org_id):
    """Удаление организации"""
    conn = get_db()
    c = conn.cursor()
    
    # Проверяем наличие отделов
    c.execute("SELECT COUNT(*) FROM departments WHERE organization_id = ?", (org_id,))
    depts_count = c.fetchone()[0]
    
    # Проверяем наличие сотрудников
    c.execute("SELECT COUNT(*) FROM users WHERE organization_id = ?", (org_id,))
    users_count = c.fetchone()[0]
    
    if depts_count > 0 or users_count > 0:
        conn.close()
        return jsonify({
            'success': False, 
            'error': f'❌ Нельзя удалить организацию. В ней {depts_count} отделов и {users_count} сотрудников.'
        }), 400
    
    c.execute("DELETE FROM organizations WHERE id = ?", (org_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': '✅ Организация удалена'})

@app.route('/api/organizations/<int:org_id>/departments', methods=['GET'])
def get_organization_departments(org_id):
    """Получение отделов организации"""
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT d.*, 
               COUNT(u.id) as employees_count
        FROM departments d
        LEFT JOIN users u ON d.id = u.department_id
        WHERE d.organization_id = ?
        GROUP BY d.id
        ORDER BY d.level, d.name
    """, (org_id,))
    departments = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(departments)

@app.route('/api/organizations/<int:org_id>/employees', methods=['GET'])
def get_organization_employees(org_id):
    """Получение сотрудников организации"""
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT u.*, d.name as department_name
        FROM users u
        LEFT JOIN departments d ON u.department_id = d.id
        WHERE u.organization_id = ? AND u.status = 'approved'
        ORDER BY u.full_name
    """, (org_id,))
    employees = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(employees)

@app.route('/api/organizations/<int:org_id>/stats', methods=['GET'])
def get_organization_stats(org_id):
    """Статистика по организации"""
    conn = get_db()
    c = conn.cursor()
    
    # Общая статистика
    c.execute("SELECT COUNT(*) FROM users WHERE organization_id = ? AND status = 'approved'", (org_id,))
    total_employees = c.fetchone()[0]
    
    c.execute("""
        SELECT COUNT(*) FROM shifts s
        JOIN users u ON s.user_id = u.id
        WHERE u.organization_id = ?
    """, (org_id,))
    total_shifts = c.fetchone()[0]
    
    c.execute("""
        SELECT COUNT(*) FROM shifts s
        JOIN users u ON s.user_id = u.id
        WHERE u.organization_id = ? AND s.status = 'pending'
    """, (org_id,))
    pending_shifts = c.fetchone()[0]
    
    c.execute("""
        SELECT COUNT(*) FROM shifts s
        JOIN users u ON s.user_id = u.id
        WHERE u.organization_id = ? AND s.status = 'approved'
    """, (org_id,))
    approved_shifts = c.fetchone()[0]
    
    # По отделам
    c.execute("""
        SELECT d.name, COUNT(u.id) as emp_count
        FROM departments d
        LEFT JOIN users u ON d.id = u.department_id AND u.status = 'approved'
        WHERE d.organization_id = ?
        GROUP BY d.id
        ORDER BY d.name
    """, (org_id,))
    by_department = [dict(row) for row in c.fetchall()]
    
    conn.close()
    
    return jsonify({
        'organization_id': org_id,
        'total_employees': total_employees,
        'total_shifts': total_shifts,
        'pending_shifts': pending_shifts,
        'approved_shifts': approved_shifts,
        'by_department': by_department
    })
