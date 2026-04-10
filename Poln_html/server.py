from flask import Flask, request, jsonify, send_from_directory
import sqlite3
import hashlib
import os
import csv
from io import StringIO
from datetime import datetime

app = Flask(__name__, static_folder='static', static_url_path='')

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
                  FOREIGN KEY (user_id) REFERENCES users (id))''')
    
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
    
    conn.commit()
    conn.close()
    print("✓ База данных инициализирована")

def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

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

# === ПОЛЬЗОВАТЕЛИ (для админа) ===
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

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT role FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    if user and user['role'] == 'admin':
        c.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
        admin_count = c.fetchone()[0]
        if admin_count <= 1:
            conn.close()
            return jsonify({'success': False, 'error': 'Нельзя удалить последнего администратора'}), 400
    
    c.execute("DELETE FROM shifts WHERE user_id = ?", (user_id,))
    c.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    data = request.get_json()
    conn = get_db()
    c = conn.cursor()
    
    if data.get('password'):
        hashed = hashlib.sha256(data['password'].encode()).hexdigest()
        c.execute("UPDATE users SET full_name = ?, role = ?, department = ?, password = ? WHERE id = ?",
                  (data['full_name'], data['role'], data.get('department', ''), hashed, user_id))
    else:
        c.execute("UPDATE users SET full_name = ?, role = ?, department = ? WHERE id = ?",
                  (data['full_name'], data['role'], data.get('department', ''), user_id))
    
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
        shifts = [dict(row) for row in c.fetchall()]
        conn.close()
        return jsonify(shifts)
    
    elif request.method == 'POST':
        data = request.get_json()
        c.execute("INSERT INTO shifts (user_id, date, start_time, end_time, status) VALUES (?, ?, ?, ?, ?)",
                  (data['user_id'], data['date'], data['start_time'], data.get('end_time'), 'pending'))
        conn.commit()
        shift_id = c.lastrowid
        conn.close()
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

# === СТАТИСТИКА (ИСПРАВЛЕНО) ===
@app.route('/api/stats')
def get_stats():
    conn = get_db()
    c = conn.cursor()
    
    # Общая статистика
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
    
    # По отделам - ИСПРАВЛЕНО
    c.execute("""
        SELECT u.department, COUNT(s.id) as count 
        FROM users u 
        LEFT JOIN shifts s ON u.id = s.user_id 
        WHERE u.role = 'employee' AND u.status = 'approved'
        GROUP BY u.department
        HAVING u.department IS NOT NULL AND u.department != ''
    """)
    by_department = [dict(row) for row in c.fetchall()]
    
    # Количество pending пользователей
    c.execute("SELECT COUNT(*) FROM users WHERE status = 'pending'")
    pending_users = c.fetchone()[0]
    
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

@app.route('/api/export/google-sheets-data')
def google_sheets_data():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT u.full_name, u.department, s.date, s.start_time, s.end_time, s.status 
        FROM shifts s 
        JOIN users u ON s.user_id = u.id 
        ORDER BY s.date
    """)
    shifts = c.fetchall()
    conn.close()
    
    data = [['Сотрудник', 'Отдел', 'Дата', 'Начало', 'Конец', 'Статус']]
    for shift in shifts:
        data.append([
            shift['full_name'],
            shift['department'] or '',
            shift['date'],
            shift['start_time'],
            shift['end_time'] or '',
            shift['status']
        ])
    
    return jsonify({'data': data, 'total': len(shifts)})

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
    print("🚀 Сервер запущен!")
    print("📍 http://localhost:5000")
    print("="*50 + "\n")
    app.run(host='0.0.0.0', port=5000, debug=True)