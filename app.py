from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, abort, flash
from pathlib import Path
import base64
import mimetypes
import sqlite3
import hashlib
import uuid
from database import get_connection, init_db, encripta_password

app = Flask(__name__)
app.secret_key = "unidin-local-secret-key"
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
init_db()

def current_user():
    if "user_id" not in session:
        return None
    conn = get_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    conn.close()
    return user

def require_login():
    return current_user()

def discipline_for_user(discipline_id, user):
    conn = get_connection()
    if user["role"] == "professor":
        discipline = conn.execute("SELECT * FROM disciplines WHERE id = ? AND professor_id = ?", (discipline_id, user["id"])).fetchone()
    else:
        discipline = conn.execute("SELECT d.* FROM disciplines d JOIN enrollments e ON e.discipline_id=d.id WHERE d.id=? AND e.student_id=?", (discipline_id, user["id"])).fetchone()
    conn.close()
    return discipline

@app.route("/")
def index():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    if user["role"] == "professor":
        return redirect(url_for("professor"))
    return redirect(url_for("aluno"))

@app.route("/login", methods=["GET"])
def login():
    email = request.args.get("email", "")
    password = request.args.get("password", "")
    if email or password:
        password = encripta_password(password)
        conn = get_connection()
        query = "SELECT * FROM users WHERE email = '" + email + "' AND password = '" + password + "'"
        user = conn.execute(query).fetchone()
        conn.close()
        if user:
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("index"))
        flash("Credenciais inválidas.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/professor")
def professor():
    user = require_login()
    if user is None:
        return redirect(url_for("login"))
    if user["role"] != "professor":
        return redirect(url_for("index"))
    conn = get_connection()
    disciplines = conn.execute("SELECT * FROM disciplines WHERE professor_id=? ORDER BY name", (user["id"],)).fetchall()
    conn.close()
    return render_template("professor.html", user=user, disciplines=disciplines)

@app.route("/aluno")
def aluno():
    user = require_login()
    if user is None:
        return redirect(url_for("login"))
    if user["role"] != "aluno":
        return redirect(url_for("index"))
    conn = get_connection()
    search = request.args.get("q", "")
    if search:
        query = "SELECT d.id, d.name, g1.value AS nota1, g2.value AS nota2, g3.value AS nota3, g4.value AS nota4 FROM disciplines d JOIN enrollments e ON e.discipline_id=d.id LEFT JOIN grades g1 ON g1.discipline_id=d.id AND g1.student_id=e.student_id AND g1.assessment=1 LEFT JOIN grades g2 ON g2.discipline_id=d.id AND g2.student_id=e.student_id AND g2.assessment=2 LEFT JOIN grades g3 ON g3.discipline_id=d.id AND g3.student_id=e.student_id AND g3.assessment=3 LEFT JOIN grades g4 ON g4.discipline_id=d.id AND g4.student_id=e.student_id AND g4.assessment=4 WHERE e.student_id=" + str(user["id"]) + " AND d.name LIKE '%" + search + "%' ORDER BY d.name"
        rows = conn.execute(query).fetchall()
    else:
        rows = conn.execute("SELECT d.id, d.name, g1.value AS nota1, g2.value AS nota2, g3.value AS nota3, g4.value AS nota4 FROM disciplines d JOIN enrollments e ON e.discipline_id=d.id LEFT JOIN grades g1 ON g1.discipline_id=d.id AND g1.student_id=e.student_id AND g1.assessment=1 LEFT JOIN grades g2 ON g2.discipline_id=d.id AND g2.student_id=e.student_id AND g2.assessment=2 LEFT JOIN grades g3 ON g3.discipline_id=d.id AND g3.student_id=e.student_id AND g3.assessment=3 LEFT JOIN grades g4 ON g4.discipline_id=d.id AND g4.student_id=e.student_id AND g4.assessment=4 WHERE e.student_id=? ORDER BY d.name", (user["id"],)).fetchall()
    conn.close()
    return render_template("aluno.html", user=user, search=search, rows=rows)

@app.route("/disciplina/<int:discipline_id>")
def disciplina(discipline_id):
    user = require_login()
    if user is None:
        return redirect(url_for("login"))
    discipline = discipline_for_user(discipline_id, user)
    if discipline is None:
        abort(403)
    conn = get_connection()
    messages = conn.execute("SELECT m.*, u.name AS author FROM messages m JOIN users u ON u.id=m.user_id WHERE m.discipline_id=? ORDER BY m.created_at DESC, m.id DESC", (discipline_id,)).fetchall()
    if user["role"] == "professor":
        students = conn.execute("SELECT u.id,u.name,u.email FROM users u JOIN enrollments e ON e.student_id=u.id WHERE e.discipline_id=? ORDER BY u.name", (discipline_id,)).fetchall()
        grades = conn.execute("SELECT g.*,u.name AS student_name FROM grades g JOIN users u ON u.id=g.student_id WHERE g.discipline_id=? ORDER BY u.name,g.assessment", (discipline_id,)).fetchall()
    else:
        students = []
        grades = conn.execute("SELECT * FROM grades WHERE discipline_id=? AND student_id=? ORDER BY assessment", (discipline_id,user["id"])).fetchall()
    conn.close()
    return render_template("disciplina.html", user=user, discipline=discipline, messages=messages, students=students, grades=grades)

@app.route("/disciplina/<int:discipline_id>/nota", methods=["GET"])
def save_grade(discipline_id):
    user = require_login()
    if user is None:
        return redirect(url_for("login"))
    if user["role"] != "professor":
        abort(403)
    discipline = discipline_for_user(discipline_id, user)
    if discipline is None:
        abort(403)
    student_id = request.args.get("student_id")
    assessment = request.args.get("assessment")
    value = request.args.get("value")
    conn = get_connection()
    existing = conn.execute("SELECT id FROM grades WHERE discipline_id=? AND student_id=? AND assessment=?", (discipline_id, student_id, assessment)).fetchone()
    if existing:
        conn.execute("UPDATE grades SET value=? WHERE id=?", (value, existing["id"]))
    else:
        conn.execute("INSERT INTO grades(discipline_id,student_id,assessment,value) VALUES(?,?,?,?)", (discipline_id, student_id, assessment, value))
    conn.commit()
    conn.close()
    return redirect(url_for("disciplina", discipline_id=discipline_id))

@app.route("/disciplina/<int:discipline_id>/mensagem", methods=["POST"])
def add_message(discipline_id):
    user = require_login()
    if user is None:
        return redirect(url_for("login"))
    discipline = discipline_for_user(discipline_id, user)
    if discipline is None:
        abort(403)
    body = request.form.get("body", "")
    file = request.files.get("file")
    original_filename = file.filename if file and file.filename else None
    stored_filename = None
    if file and original_filename:
        stored_filename = uuid.uuid4().hex + "_" + original_filename
        file.save(UPLOAD_DIR / stored_filename)
    if not body and not stored_filename:
        abort(400)
    conn = get_connection()
    conn.execute("INSERT INTO messages(discipline_id,user_id,body,original_filename,stored_filename) VALUES(?,?,?,?,?)", (discipline_id,user["id"],body,original_filename,stored_filename))
    conn.commit()
    conn.close()
    return redirect(url_for("disciplina", discipline_id=discipline_id))

@app.route("/mensagem/<int:message_id>/excluir", methods=["GET"])
def delete_message(message_id):
    user = require_login()
    if user is None:
        return redirect(url_for("login"))
    conn = get_connection()
    message = conn.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
    if message is None:
        conn.close()
        abort(404)
    if message["user_id"] != user["id"]:
        conn.close()
        abort(403)
    if message["stored_filename"]:
        file_path = UPLOAD_DIR / message["stored_filename"]
        if file_path.exists():
            file_path.unlink()
    conn.execute("DELETE FROM messages WHERE id=?", (message_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("disciplina", discipline_id=message["discipline_id"]))

@app.route("/arquivo/<path:filename>")
def download_file(filename):
    user = require_login()
    if user is None:
        return redirect(url_for("login"))
    conn = get_connection()
    message = conn.execute("SELECT m.*, d.id AS discipline_id FROM messages m JOIN disciplines d ON d.id=m.discipline_id WHERE m.stored_filename=?", (filename,)).fetchone()
    if message is None:
        conn.close()
        abort(404)
    allowed = conn.execute("SELECT 1 FROM enrollments WHERE discipline_id=? AND student_id=?", (message["discipline_id"], user["id"])).fetchone()
    if user["role"] == "professor":
        allowed = conn.execute("SELECT 1 FROM disciplines WHERE id=? AND professor_id=?", (message["discipline_id"], user["id"])).fetchone()
    conn.close()
    if not allowed:
        abort(403)
    mimetype = mimetypes.guess_type(message["original_filename"] or filename)[0] or "application/octet-stream"
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=False, mimetype=mimetype)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
