from flask import Flask, request, jsonify, send_from_directory, make_response
import sqlite3
import hashlib
import os

app = Flask(__name__, static_folder='static', static_url_path='')

# Включаем CORS вручную для всех запросов
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

@app.route('/api/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return '', 200
        
    try:
        data = request.get_json()
        print(f"Login attempt: {data.get('username')}")
        
        conn = sqlite3.connect('database.db')
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        hashed = hashlib.sha256(data['password'].encode()).hexdigest()
        c.execute("SELECT * FROM users WHERE username = ? AND password = ?", 
                  (data['username'], hashed))
        user = c.fetchone()
        conn.close()
        
        if user:
            user_dict = dict(user)
            print(f"Login success: {user_dict['username']}")
            return jsonify({
                'success': True,
                'user_id': user_dict['id'],
                'username': user_dict['username'],
                'role': user_dict['role'],
                'full_name': user_dict['full_name']
            })
        else:
            return jsonify({'success': False, 'error': 'Неверный логин или пароль'}), 401
    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/register', methods=['POST', 'OPTIONS'])
def register():
    if request.method == 'OPTIONS':
        return '', 200
        
    try:
        data = request.get_json()
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        
        hashed = hashlib.sha256(data['password'].encode()).hexdigest()
        c.execute("INSERT INTO users (username, password, role, full_name) VALUES (?, ?, ?, ?)",
                  (data['username'], hashed, 'employee', data['full_name']))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Регистрация успешна'})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'error': 'Пользователь уже существует'}), 400

@app.route('/api/employees', methods=['GET'])
def get_employees():
    try:
        conn = sqlite3.connect('database.db')
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT id, username, full_name, role FROM users WHERE role = 'employee'")
        employees = [dict(row) for row in c.fetchall()]
        conn.close()
        return jsonify(employees)
    except Exception as e:
        return jsonify([])

@app.route('/api/shifts', methods=['GET', 'POST', 'OPTIONS'])
def shifts():
    if request.method == 'OPTIONS':
        return '', 200
        
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    if request.method == 'GET':
        user_id = request.args.get('user_id')
        if user_id:
            c.execute("SELECT * FROM shifts WHERE user_id = ? ORDER BY date", (user_id,))
        else:
            c.execute("""
                SELECT s.*, u.full_name 
                FROM shifts s 
                JOIN users u ON s.user_id = u.id 
                ORDER BY s.date
            """)
        shifts = [dict(row) for row in c.fetchall()]
        conn.close()
        return jsonify(shifts)
    
    elif request.method == 'POST':
        try:
            data = request.get_json()
            c.execute("INSERT INTO shifts (user_id, date, start_time, end_time, status) VALUES (?, ?, ?, ?, ?)",
                      (data['user_id'], data['date'], data['start_time'], data.get('end_time'), 'pending'))
            conn.commit()
            shift_id = c.lastrowid
            conn.close()
            return jsonify({'success': True, 'shift_id': shift_id})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/shifts/<int:shift_id>', methods=['DELETE', 'OPTIONS'])
def delete_shift(shift_id):
    if request.method == 'OPTIONS':
        return '', 200
        
    conn = sqlite3.connect('database.db')
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
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("UPDATE shifts SET status = ? WHERE id = ?", (data['status'], shift_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/')
def index():
    return send_from_directory('static', 'login.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  password TEXT NOT NULL,
                  role TEXT NOT NULL,
                  full_name TEXT NOT NULL)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS shifts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  date TEXT NOT NULL,
                  start_time TEXT NOT NULL,
                  end_time TEXT,
                  status TEXT DEFAULT 'pending',
                  FOREIGN KEY (user_id) REFERENCES users (id))''')
    
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        admin_pass = hashlib.sha256("admin123".encode()).hexdigest()
        manager_pass = hashlib.sha256("manager123".encode()).hexdigest()
        emp1_pass = hashlib.sha256("emp123".encode()).hexdigest()
        emp2_pass = hashlib.sha256("emp456".encode()).hexdigest()
        
        users = [
            ("admin", admin_pass, "admin", "Администратор Системы"),
            ("manager", manager_pass, "manager", "Петров Иван Сергеевич"),
            ("employee1", emp1_pass, "employee", "Иванов Алексей Петрович"),
            ("employee2", emp2_pass, "employee", "Смирнова Елена Викторовна"),
        ]
        c.executemany("INSERT INTO users (username, password, role, full_name) VALUES (?, ?, ?, ?)", users)
    
    conn.commit()
    conn.close()
    print("Database initialized!")

if __name__ == '__main__':
    init_db()
    print("Server starting at http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)