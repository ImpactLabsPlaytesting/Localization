import os
import json
import secrets
import logging
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from functools import wraps

import config
from db import get_db, init_db
from auth import verify_admin_password, verify_totp, generate_totp_secret, get_totp_qr_base64, admin_required
import sheets
import email_service
from magic_link import generate_magic_link, verify_token, cleanup_expired

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

if os.environ.get('DATABASE_URL'):
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
else:
    os.makedirs(os.path.join(os.path.dirname(__file__), 'logs'), exist_ok=True)
    logging.basicConfig(
        filename=os.path.join(os.path.dirname(__file__), 'logs', 'app.log'),
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s'
    )

ALL_LANGUAGES = ['French', 'Spanish', 'German', 'Japanese', 'Russian', 'Chinese Simplified', 'Turkish']


@app.errorhandler(Exception)
def handle_exception(e):
    import traceback
    logging.error(f"Unhandled exception: {e}\n{traceback.format_exc()}")
    return "Internal Server Error", 500


# --- Translator auth decorator ---
def translator_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('translator_id'):
            return redirect(url_for('translator_login_page'))
        return f(*args, **kwargs)
    return decorated


# --- Root ---
@app.route('/')
def index():
    if session.get('admin_authenticated'):
        return redirect(url_for('admin_overview'))
    if session.get('translator_id'):
        return redirect(url_for('translator_home'))
    return redirect(url_for('admin_login'))


# ============================================================
# ADMIN AUTH
# ============================================================

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if verify_admin_password(request.form.get('password', '')):
            session['admin_password_ok'] = True
            return redirect(url_for('admin_2fa'))
        flash('Invalid password.', 'error')
    return render_template('admin_login.html')


@app.route('/admin/2fa', methods=['GET', 'POST'])
def admin_2fa():
    if not session.get('admin_password_ok'):
        return redirect(url_for('admin_login'))

    setup_mode = not config.TOTP_SECRET
    totp_secret = None
    qr_base64 = None

    if setup_mode:
        totp_secret = session.get('totp_setup_secret')
        if not totp_secret:
            totp_secret = generate_totp_secret()
            session['totp_setup_secret'] = totp_secret
        qr_base64 = get_totp_qr_base64(totp_secret)

    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        if setup_mode:
            secret = request.form.get('setup_secret', '') or session.get('totp_setup_secret', '')
            import pyotp
            totp = pyotp.TOTP(secret)
            if totp.verify(code):
                _save_totp_secret(secret)
                session.pop('totp_setup_secret', None)
                session.pop('admin_password_ok', None)
                session['admin_authenticated'] = True
                flash('2FA setup complete. You are now logged in.', 'success')
                return redirect(url_for('admin_dashboard'))
            flash('Invalid code. Try again.', 'error')
        else:
            if verify_totp(code):
                session.pop('admin_password_ok', None)
                session['admin_authenticated'] = True
                return redirect(url_for('admin_dashboard'))
            flash('Invalid code.', 'error')

    return render_template('admin_2fa.html',
                           setup_mode=setup_mode,
                           totp_secret=totp_secret,
                           qr_base64=qr_base64)


def _save_totp_secret(secret):
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            lines = f.readlines()
        found = False
        for i, line in enumerate(lines):
            if line.startswith('TOTP_SECRET='):
                lines[i] = f'TOTP_SECRET={secret}\n'
                found = True
                break
        if not found:
            lines.append(f'TOTP_SECRET={secret}\n')
        with open(env_path, 'w') as f:
            f.writelines(lines)
    else:
        with open(env_path, 'w') as f:
            f.write(f'TOTP_SECRET={secret}\n')
    config.TOTP_SECRET = secret


@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))


# ============================================================
# ADMIN - OVERVIEW DASHBOARD
# ============================================================

@app.route('/admin/overview')
@admin_required
def admin_overview():
    db = get_db()
    project_count = db.execute('SELECT COUNT(*) as c FROM projects').fetchone()['c']
    translator_count = db.execute('SELECT COUNT(*) as c FROM translators').fetchone()['c']
    active_assignments = db.execute("SELECT COUNT(*) as c FROM assignments WHERE status = 'active'").fetchone()['c']
    done_assignments = db.execute("SELECT COUNT(*) as c FROM assignments WHERE status = 'done'").fetchone()['c']

    # Per-project stats
    projects = db.execute('SELECT * FROM projects ORDER BY created_at DESC').fetchall()
    project_stats = []
    for p in projects:
        assignments = db.execute('''
            SELECT a.*, t.name as translator_name
            FROM assignments a JOIN translators t ON a.translator_id = t.id
            WHERE a.project_id = ?
            ORDER BY a.language
        ''', (p['id'],)).fetchall()
        lang_stats = []
        total_rows = 0
        total_reviewed = 0
        for a in assignments:
            try:
                progress = sheets.get_progress(a['sheet_id'] if 'sheet_id' in a.keys() else p['sheet_id'], a['tab_name'])
            except Exception:
                progress = {'total': 0, 'reviewed': 0, 'correct': 0, 'corrected': 0, 'pct': 0}
            total_rows += progress['total']
            total_reviewed += progress['reviewed']
            lang_stats.append({
                'language': a['language'],
                'translator': a['translator_name'],
                'status': a['status'],
                'progress': progress
            })
        overall_pct = round(total_reviewed / total_rows * 100) if total_rows else 0
        project_stats.append({
            'id': p['id'],
            'name': p['name'],
            'languages': lang_stats,
            'overall_pct': overall_pct,
            'total_rows': total_rows,
            'total_reviewed': total_reviewed
        })

    db.close()
    return render_template('admin_overview.html',
                           project_count=project_count,
                           translator_count=translator_count,
                           active_assignments=active_assignments,
                           done_assignments=done_assignments,
                           project_stats=project_stats)


# ============================================================
# ADMIN - TRANSLATOR ROSTER
# ============================================================

@app.route('/admin/translators')
@admin_required
def admin_dashboard():
    db = get_db()
    translators = db.execute('SELECT * FROM translators ORDER BY name').fetchall()
    result = []
    for t in translators:
        assignments = db.execute('''
            SELECT a.*, p.sheet_id, p.name as project_name
            FROM assignments a JOIN projects p ON a.project_id = p.id
            WHERE a.translator_id = ? ORDER BY a.status, p.name
        ''', (t['id'],)).fetchall()
        t_assignments = []
        for a in assignments:
            try:
                progress = sheets.get_progress(a['sheet_id'], a['tab_name'])
            except Exception:
                progress = {'total': 0, 'reviewed': 0, 'correct': 0, 'corrected': 0, 'pct': 0}
            t_assignments.append({**dict(a), 'progress': progress})
        result.append({**dict(t), 'assignments': t_assignments})
    db.close()
    return render_template('admin_dashboard.html', translators=result, all_languages=ALL_LANGUAGES)


@app.route('/admin/translators/add', methods=['POST'])
@admin_required
def admin_add_translator():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    languages = request.form.getlist('languages')
    if not name or not email:
        flash('Name and email are required.', 'error')
        return redirect(url_for('admin_dashboard'))
    db = get_db()
    try:
        db.execute('INSERT INTO translators (name, email, languages) VALUES (?, ?, ?)',
                    (name, email, ','.join(languages)))
        db.commit()
        flash(f'Added {name}.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    db.close()
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/translators/<int:tid>/edit', methods=['POST'])
@admin_required
def admin_edit_translator(tid):
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    languages = request.form.getlist('languages')
    if not name or not email:
        flash('Name and email are required.', 'error')
        return redirect(url_for('admin_dashboard'))
    db = get_db()
    try:
        db.execute('UPDATE translators SET name = ?, email = ?, languages = ? WHERE id = ?',
                    (name, email, ','.join(languages), tid))
        db.commit()
        flash(f'Updated {name}.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    db.close()
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/translators/<int:tid>/delete', methods=['POST'])
@admin_required
def admin_delete_translator(tid):
    db = get_db()
    db.execute('DELETE FROM translators WHERE id = ?', (tid,))
    db.commit()
    db.close()
    flash('Translator removed.', 'success')
    return redirect(url_for('admin_dashboard'))


# ============================================================
# ADMIN - PROJECTS
# ============================================================

@app.route('/admin/projects')
@admin_required
def admin_projects():
    db = get_db()
    projects = db.execute('SELECT * FROM projects ORDER BY created_at DESC').fetchall()
    result = []
    for p in projects:
        assignments = db.execute('''
            SELECT a.*, t.name as translator_name
            FROM assignments a JOIN translators t ON a.translator_id = t.id
            WHERE a.project_id = ?
        ''', (p['id'],)).fetchall()
        try:
            data = sheets.read_main_tab(p['sheet_id'], p['main_tab'])
            languages = data['languages']
        except Exception as e:
            logging.error(f"read_main_tab failed for {p['name']} (sheet={p['sheet_id']}, tab={p['main_tab']}): {e}")
            languages = []
        total_new = 0
        for a in assignments:
            try:
                new_keys = sheets.get_new_keys(p['sheet_id'], p['main_tab'], a['tab_name'])
                total_new += len(new_keys)
            except Exception:
                pass
        result.append({**dict(p), 'assignment_count': len(assignments), 'languages': languages, 'new_rows': total_new})
    db.close()
    return render_template('admin_projects.html', projects=result)


@app.route('/admin/project/new', methods=['POST'])
@admin_required
def admin_add_project():
    name = request.form.get('name', '').strip()
    sheet_id = request.form.get('sheet_id', '').strip()
    main_tab = request.form.get('main_tab', 'Sheet1').strip() or 'Sheet1'
    if not name or not sheet_id:
        flash('Name and Sheet ID are required.', 'error')
        return redirect(url_for('admin_projects'))
    db = get_db()
    db.execute('INSERT INTO projects (name, sheet_id, main_tab) VALUES (?, ?, ?)',
               (name, sheet_id, main_tab))
    db.commit()
    db.close()
    flash(f'Project "{name}" added.', 'success')
    return redirect(url_for('admin_projects'))


@app.route('/admin/project/<int:pid>/delete', methods=['POST'])
@admin_required
def admin_delete_project(pid):
    db = get_db()
    db.execute('DELETE FROM projects WHERE id = ?', (pid,))
    db.commit()
    db.close()
    flash('Project deleted.', 'success')
    return redirect(url_for('admin_projects'))


@app.route('/admin/project/<int:pid>')
@admin_required
def admin_project_detail(pid):
    db = get_db()
    project = db.execute('SELECT * FROM projects WHERE id = ?', (pid,)).fetchone()
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('admin_projects'))

    try:
        data = sheets.read_main_tab(project['sheet_id'], project['main_tab'])
        languages = data['languages']
    except Exception as e:
        flash(f'Error reading sheet: {e}', 'error')
        languages = []

    # Get eligible translators per language
    all_translators = db.execute('SELECT * FROM translators ORDER BY name').fetchall()
    eligible_by_lang = {}
    for lang in languages:
        eligible = []
        for t in all_translators:
            t_langs = [l.strip() for l in t['languages'].split(',') if l.strip()]
            already_assigned = db.execute(
                'SELECT id FROM assignments WHERE translator_id = ? AND project_id = ? AND language = ?',
                (t['id'], pid, lang)
            ).fetchone()
            if lang in t_langs and not already_assigned:
                eligible.append(dict(t))
        eligible_by_lang[lang] = eligible

    # Get active assignments with progress
    assignments_raw = db.execute('''
        SELECT a.*, t.name as translator_name, t.email as translator_email
        FROM assignments a JOIN translators t ON a.translator_id = t.id
        WHERE a.project_id = ?
        ORDER BY a.language, t.name
    ''', (pid,)).fetchall()

    assignments = []
    for a in assignments_raw:
        try:
            progress = sheets.get_progress(project['sheet_id'], a['tab_name'])
        except Exception as e:
            print(f"[ERROR] get_progress failed for {a['tab_name']}: {e}")
            progress = {'total': 0, 'reviewed': 0, 'correct': 0, 'corrected': 0, 'pct': 0}
        try:
            new_keys = sheets.get_new_keys(project['sheet_id'], project['main_tab'], a['tab_name'])
            new_rows = len(new_keys)
        except Exception as e:
            print(f"[ERROR] get_new_keys failed for {a['tab_name']}: {e}")
            import traceback; traceback.print_exc()
            new_rows = 0
        assignments.append({
            **dict(a),
            'progress': progress,
            'new_rows': new_rows
        })

    db.close()
    return render_template('admin_project.html',
                           project=dict(project),
                           languages=languages,
                           eligible_by_lang=eligible_by_lang,
                           assignments=assignments)


# ============================================================
# ADMIN - INVITE / SYNC / NOTIFY
# ============================================================

@app.route('/admin/project/<int:pid>/invite', methods=['POST'])
@admin_required
def admin_invite(pid):
    db = get_db()
    project = db.execute('SELECT * FROM projects WHERE id = ?', (pid,)).fetchone()
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('admin_projects'))

    invites = request.form.getlist('invite')
    count = 0
    for item in invites:
        tid_str, lang = item.split(':', 1)
        tid = int(tid_str)
        translator = db.execute('SELECT * FROM translators WHERE id = ?', (tid,)).fetchone()
        if not translator:
            continue
        tab_name = f"{lang} ({translator['name']})"

        # Check if already assigned
        existing = db.execute(
            'SELECT id FROM assignments WHERE translator_id = ? AND project_id = ? AND language = ?',
            (tid, pid, lang)
        ).fetchone()
        if existing:
            continue

        try:
            sheets.create_translator_tab(project['sheet_id'], tab_name, lang, project['main_tab'])
        except Exception as e:
            flash(f"Error creating tab for {translator['name']}: {e}", 'error')
            continue

        db.execute(
            'INSERT INTO assignments (translator_id, project_id, language, tab_name) VALUES (?, ?, ?, ?)',
            (tid, pid, lang, tab_name)
        )
        db.commit()

        try:
            dashboard_url = f"{config.BASE_URL}/translate/"
            email_service.send_invitation(
                translator['name'], translator['email'],
                project['name'], lang, dashboard_url
            )
        except Exception as e:
            flash(f"Tab created for {translator['name']} but email failed: {e}", 'error')

        count += 1

    db.close()
    if count:
        flash(f'Invited {count} translator(s).', 'success')
    return redirect(url_for('admin_project_detail', pid=pid))


@app.route('/admin/project/<int:pid>/assignment/<int:aid>/sync', methods=['POST'])
@admin_required
def admin_sync_assignment(pid, aid):
    db = get_db()
    assignment = db.execute('SELECT a.*, p.sheet_id, p.main_tab FROM assignments a JOIN projects p ON a.project_id = p.id WHERE a.id = ?', (aid,)).fetchone()
    if not assignment:
        flash('Assignment not found.', 'error')
        return redirect(url_for('admin_project_detail', pid=pid))

    try:
        count = sheets.sync_new_rows(assignment['sheet_id'], assignment['main_tab'], assignment['tab_name'], assignment['language'])
        flash(f'Synced {count} new row(s).', 'success')
    except Exception as e:
        flash(f'Sync error: {e}', 'error')

    db.close()
    return redirect(url_for('admin_project_detail', pid=pid))


@app.route('/admin/project/<int:pid>/assignment/<int:aid>/notify', methods=['POST'])
@admin_required
def admin_notify_assignment(pid, aid):
    db = get_db()
    assignment = db.execute('''
        SELECT a.*, t.name as translator_name, t.email as translator_email, p.name as project_name, p.sheet_id, p.main_tab
        FROM assignments a
        JOIN translators t ON a.translator_id = t.id
        JOIN projects p ON a.project_id = p.id
        WHERE a.id = ?
    ''', (aid,)).fetchone()

    if not assignment:
        flash('Assignment not found.', 'error')
        return redirect(url_for('admin_project_detail', pid=pid))

    try:
        progress = sheets.get_progress(assignment['sheet_id'], assignment['tab_name'])
        pending = progress['total'] - progress['reviewed']
        dashboard_url = f"{config.BASE_URL}/translate/"
        email_service.send_new_rows_notification(
            assignment['translator_name'], assignment['translator_email'],
            assignment['project_name'], assignment['language'],
            pending, dashboard_url
        )
        flash(f'Notification sent to {assignment["translator_name"]}.', 'success')
    except Exception as e:
        flash(f'Email error: {e}', 'error')

    db.close()
    return redirect(url_for('admin_project_detail', pid=pid))


@app.route('/admin/project/<int:pid>/assignment/<int:aid>/delete', methods=['POST'])
@admin_required
def admin_delete_assignment(pid, aid):
    db = get_db()
    db.execute('DELETE FROM assignments WHERE id = ?', (aid,))
    db.commit()
    db.close()
    flash('Assignment removed.', 'success')
    return redirect(url_for('admin_project_detail', pid=pid))


# ============================================================
# TRANSLATOR AUTH (Google OAuth)
# ============================================================

@app.route('/login', methods=['GET', 'POST'])
def translator_login_page():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        if not email:
            flash('Please enter your email.', 'error')
            return render_template('translator_login.html')
        result = generate_magic_link(email)
        if result:
            flash('Login link sent! Check your email.', 'success')
        else:
            flash('Login link sent! Check your email.', 'success')
        return render_template('translator_login.html', email_sent=True)
    return render_template('translator_login.html')


@app.route('/login/verify')
def translator_verify_login():
    token = request.args.get('token', '')
    if not token:
        flash('Invalid login link.', 'error')
        return redirect(url_for('translator_login_page'))

    translator = verify_token(token)
    if not translator:
        flash('Login link expired or already used. Request a new one.', 'error')
        return redirect(url_for('translator_login_page'))

    session['translator_id'] = translator['id']
    session['translator_name'] = translator['name']
    session['translator_email'] = translator['email']
    cleanup_expired()
    return redirect(url_for('translator_home'))


@app.route('/logout')
def translator_logout():
    session.clear()
    return redirect(url_for('translator_login_page'))


# ============================================================
# TRANSLATOR PORTAL
# ============================================================

@app.route('/translate/')
@translator_required
def translator_home():
    db = get_db()
    assignments_raw = db.execute('''
        SELECT a.*, p.name as project_name, p.sheet_id
        FROM assignments a JOIN projects p ON a.project_id = p.id
        WHERE a.translator_id = ?
        ORDER BY a.status, p.name
    ''', (session['translator_id'],)).fetchall()

    assignments = []
    for a in assignments_raw:
        try:
            progress = sheets.get_progress(a['sheet_id'], a['tab_name'])
        except Exception:
            progress = {'total': 0, 'reviewed': 0, 'correct': 0, 'corrected': 0, 'pct': 0}
        assignments.append({**dict(a), 'progress': progress})

    db.close()
    return render_template('translator_home.html', assignments=assignments)


@app.route('/translate/<int:pid>/<int:aid>')
@translator_required
def translator_work(pid, aid):
    db = get_db()
    assignment = db.execute('''
        SELECT a.*, p.name as project_name, p.sheet_id
        FROM assignments a JOIN projects p ON a.project_id = p.id
        WHERE a.id = ? AND a.translator_id = ?
    ''', (aid, session['translator_id'])).fetchone()

    if not assignment:
        flash('Assignment not found.', 'error')
        return redirect(url_for('translator_home'))

    try:
        rows = sheets.read_translator_tab(assignment['sheet_id'], assignment['tab_name'])
        progress = sheets.get_progress(assignment['sheet_id'], assignment['tab_name'])
    except Exception as e:
        flash(f'Error reading sheet: {e}', 'error')
        rows = []
        progress = {'total': 0, 'reviewed': 0, 'correct': 0, 'corrected': 0, 'pct': 0}

    db.close()
    return render_template('translator_work.html',
                           rows=rows,
                           progress=progress,
                           project_name=assignment['project_name'],
                           language=assignment['language'],
                           assignment_id=aid,
                           assignment_status=assignment['status'])


@app.route('/api/save', methods=['POST'])
@translator_required
def api_save():
    data = request.get_json()
    aid = data.get('assignment_id')
    row_num = data.get('row_num')
    status = data.get('status', '')
    corrected = data.get('corrected', '')

    db = get_db()
    assignment = db.execute('''
        SELECT a.*, p.sheet_id FROM assignments a JOIN projects p ON a.project_id = p.id
        WHERE a.id = ? AND a.translator_id = ?
    ''', (aid, session['translator_id'])).fetchone()

    if not assignment:
        db.close()
        return jsonify({'error': 'not found'}), 404

    try:
        sheets.save_translation(assignment['sheet_id'], assignment['tab_name'], row_num, status, corrected)
        db.close()
        return jsonify({'success': True})
    except Exception as e:
        db.close()
        return jsonify({'error': str(e)}), 500


@app.route('/translate/<int:aid>/update', methods=['POST'])
@translator_required
def translator_update(aid):
    db = get_db()
    assignment = db.execute('''
        SELECT a.*, p.name as project_name, p.sheet_id, t.name as translator_name
        FROM assignments a
        JOIN projects p ON a.project_id = p.id
        JOIN translators t ON a.translator_id = t.id
        WHERE a.id = ? AND a.translator_id = ?
    ''', (aid, session['translator_id'])).fetchone()

    if not assignment:
        flash('Assignment not found.', 'error')
        db.close()
        return redirect(url_for('translator_home'))

    note = request.form.get('note', '').strip()
    mark_done = request.form.get('mark_done') == '1'

    if mark_done:
        db.execute("UPDATE assignments SET status = 'done', done_at = ? WHERE id = ?",
                   (datetime.utcnow().isoformat(), aid))
        db.commit()

    try:
        progress = sheets.get_progress(assignment['sheet_id'], assignment['tab_name'])
        subject = f"Update from {assignment['translator_name']} - {assignment['project_name']} ({assignment['language']})"
        status_line = "COMPLETED" if mark_done else f"{progress['reviewed']}/{progress['total']} reviewed ({progress['pct']}%)"
        note_line = f"<p><strong>Note:</strong> {note}</p>" if note else ""
        body = f"""<p><strong>{assignment['translator_name']}</strong> sent an update for <strong>{assignment['language']}</strong> on <strong>{assignment['project_name']}</strong>.</p>
<p>Status: {status_line}</p>
{note_line}"""
        email_service.send_email(config.ADMIN_EMAIL, subject, body)
    except Exception:
        pass

    db.close()
    msg = 'Marked as done and Todd has been notified.' if mark_done else 'Update sent to Todd.'
    flash(msg, 'success')
    return redirect(url_for('translator_home'))


@app.route('/translate/<int:aid>/done', methods=['POST'])
@translator_required
def translator_mark_done(aid):
    db = get_db()
    assignment = db.execute('''
        SELECT a.*, p.name as project_name, p.sheet_id, t.name as translator_name
        FROM assignments a
        JOIN projects p ON a.project_id = p.id
        JOIN translators t ON a.translator_id = t.id
        WHERE a.id = ? AND a.translator_id = ?
    ''', (aid, session['translator_id'])).fetchone()

    if not assignment:
        flash('Assignment not found.', 'error')
        db.close()
        return redirect(url_for('translator_home'))

    db.execute("UPDATE assignments SET status = 'done', done_at = ? WHERE id = ?",
               (datetime.utcnow().isoformat(), aid))
    db.commit()

    try:
        progress = sheets.get_progress(assignment['sheet_id'], assignment['tab_name'])
        email_service.send_done_notification(
            assignment['translator_name'],
            assignment['project_name'],
            assignment['language'],
            progress['reviewed'],
            progress['total'],
            progress['correct'],
            progress['corrected']
        )
    except Exception:
        pass

    db.close()
    flash('Marked as done. Todd has been notified.', 'success')
    return redirect(url_for('translator_home'))


# ============================================================
# STARTUP
# ============================================================

init_db()

if __name__ == '__main__':
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    port = int(os.environ.get('PORT', 6767))
    app.run(host='0.0.0.0', port=port, debug=debug)
