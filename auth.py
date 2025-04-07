from flask import Blueprint, render_template, request, redirect, url_for, flash, session
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from config import DB_CONFIG

auth_bp = Blueprint('auth', __name__)

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

# ✅ REGISTER ROUTE
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Check if email already exists
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        if user:
            flash("Email already registered.", "warning")
            return redirect(url_for('auth.register'))

        hashed_password = generate_password_hash(password)

        # Insert new user
        cursor.execute("""
            INSERT INTO users (name, email, phone, password_hash)
            VALUES (%s, %s, %s, %s)
        """, (name, email, phone, hashed_password))
        conn.commit()

        cursor.close()
        conn.close()

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for('auth.login'))

    return render_template("register.html")

# ✅ LOGIN ROUTE
@auth_bp.route('/login', methods=['GET', 'POST'])

def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Make sure to fetch user_id, name, and password_hash
        cursor.execute("SELECT user_id, name, password_hash FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        cursor.close()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['user_id']        # ✅ Matches your DB
            session['username'] = user['name']          # ✅ name not username
            flash("Login successful!", "success")
            return redirect(url_for('show_restaurants'))
        else:
            flash("Invalid email or password.", "danger")

    return render_template("login.html")


# ✅ LOGOUT ROUTE
@auth_bp.route('/logout')
def logout():
    session.clear()
    flash("You’ve been logged out.", "info")
    return redirect(url_for('home'))
