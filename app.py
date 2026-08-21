import os
import uuid
import urllib.parse
import threading
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from converters import convert_file, ConversionCanceledError

app = Flask(__name__)

# Configs
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
OUTPUT_FOLDER = os.path.join(os.path.dirname(__file__), 'outputs')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('MAX_CONTENT_LENGTH', 20 * 1024 * 1024 * 1024)) # 20 GB limit

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response

tasks = {}
tasks_lock = threading.Lock()

def clean_local_path(raw_path):
    if not raw_path:
        return ""
    path = raw_path.strip(" \t\n\r\"'<>`")
    if path.lower().startswith('file:///'):
        path = path[8:]
    elif path.lower().startswith('file://'):
        path = path[7:]
    path = urllib.parse.unquote(path)
    path = os.path.expanduser(path)
    path = os.path.normpath(path)
    return path

def find_output_file(task_id):
    # 1. Check in-memory tasks dictionary
    with tasks_lock:
        task = tasks.get(task_id)
        if task and task.get('out_path') and os.path.exists(task['out_path']):
            return task['out_path'], task['filename']

    # 2. Disk fallback: search outputs directory for matching task_id file
    if os.path.exists(OUTPUT_FOLDER):
        prefix = f"{task_id}_"
        for fname in os.listdir(OUTPUT_FOLDER):
            if fname.startswith(prefix):
                out_path = os.path.join(OUTPUT_FOLDER, fname)
                download_name = fname[len(prefix):]
                return out_path, download_name

    return None, None

@app.route('/')
def index():
    return render_template('index.html')

def run_conversion_task(task_id, in_path, out_path, ext, is_temp=True):
    def update_progress(pct, msg):
        with tasks_lock:
            task = tasks.get(task_id)
            if task and task.get('canceled'):
                return False
            if task:
                task['progress'] = round(pct, 1)
                task['message'] = msg
        return True

    try:
        update_progress(5.0, "Starting file conversion...")
        total = convert_file(in_path, out_path, ext, progress_cb=update_progress)
        with tasks_lock:
            if not tasks.get(task_id, {}).get('canceled'):
                tasks[task_id]['status'] = 'completed'
                tasks[task_id]['progress'] = 100.0
                tasks[task_id]['message'] = f"Successfully converted {total:,} records!"
    except ConversionCanceledError:
        with tasks_lock:
            if task_id in tasks:
                tasks[task_id]['status'] = 'canceled'
                tasks[task_id]['message'] = "Conversion was canceled by user."
        if os.path.exists(out_path):
            try:
                os.remove(out_path)
            except Exception:
                pass
    except Exception as e:
        with tasks_lock:
            if task_id in tasks and not tasks[task_id].get('canceled'):
                tasks[task_id]['status'] = 'failed'
                tasks[task_id]['error'] = str(e)
                tasks[task_id]['message'] = f"Conversion error: {str(e)}"
    finally:
        if is_temp and os.path.exists(in_path):
            try:
                os.remove(in_path)
            except Exception:
                pass

@app.route('/api/cancel/<task_id>', methods=['POST', 'OPTIONS'])
def api_cancel(task_id):
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200

    with tasks_lock:
        task = tasks.get(task_id)
        if task:
            task['canceled'] = True
            task['status'] = 'canceled'
            task['message'] = 'Canceling conversion...'

    return jsonify({'status': 'canceled', 'task_id': task_id})

@app.route('/api/convert_local_path', methods=['POST', 'OPTIONS'])
def api_convert_local_path():
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200

    data = request.get_json(silent=True) or {}
    raw_path = data.get('filepath', '')
    format_type = data.get('format_type', 'auto')
    filepath = clean_local_path(raw_path)

    if not filepath:
        return jsonify({'error': 'Please enter a valid file path on your computer.'}), 400

    if not os.path.isfile(filepath):
        is_cloud = os.environ.get('RENDER') or os.environ.get('RAILWAY_STATIC_URL') or os.environ.get('HEROKU_APP_DIR')
        if is_cloud:
            return jsonify({
                'error': f"File not found on server. Local File Path mode works when running locally on your computer (http://localhost:5000). On cloud-hosted websites (Render), please use the 'Upload File' tab!"
            }), 404
        else:
            return jsonify({
                'error': f"File not found at path: '{filepath}'. Please check the file path and make sure it exists on your computer."
            }), 404

    filename = os.path.basename(filepath)
    if format_type and format_type != 'auto':
        ext = format_type
    else:
        ext = os.path.splitext(filename)[1].lower().strip('.')

    task_id = str(uuid.uuid4())
    out_name = f"{os.path.splitext(filename)[0]}_converted.csv"
    out_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{task_id}_{out_name}")

    with tasks_lock:
        tasks[task_id] = {
            'status': 'running',
            'progress': 0.0,
            'message': 'Local file detected, starting conversion...',
            'filename': out_name,
            'out_path': out_path,
            'canceled': False
        }

    thread = threading.Thread(target=run_conversion_task, args=(task_id, filepath, out_path, ext, False))
    thread.daemon = True
    thread.start()

    return jsonify({
        'task_id': task_id,
        'filename': filename,
        'status': 'running'
    })

@app.route('/api/upload_chunk', methods=['POST', 'OPTIONS'])
def api_upload_chunk():
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200

    upload_id = request.form.get('upload_id')
    chunk_index = int(request.form.get('chunk_index', 0))
    total_chunks = int(request.form.get('total_chunks', 1))
    filename = secure_filename(request.form.get('filename', 'uploaded_file'))

    if 'chunk' not in request.files:
        return jsonify({'error': 'No chunk file uploaded'}), 400

    chunk_file = request.files['chunk']
    in_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{upload_id}_{filename}")

    with open(in_path, 'ab') as f:
        f.write(chunk_file.read())

    if chunk_index == total_chunks - 1:
        task_id = upload_id
        ext = os.path.splitext(filename)[1].lower().strip('.')
        out_name = f"{os.path.splitext(filename)[0]}_converted.csv"
        out_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{task_id}_{out_name}")

        with tasks_lock:
            tasks[task_id] = {
                'status': 'running',
                'progress': 0.0,
                'message': 'Upload finished! Starting file conversion...',
                'filename': out_name,
                'out_path': out_path,
                'canceled': False
            }

        thread = threading.Thread(target=run_conversion_task, args=(task_id, in_path, out_path, ext, True))
        thread.daemon = True
        thread.start()

        return jsonify({
            'status': 'uploaded',
            'task_id': task_id,
            'filename': filename
        })

    return jsonify({
        'status': 'chunk_received',
        'chunk_index': chunk_index
    })

@app.route('/api/progress/<task_id>', methods=['GET'])
def api_progress(task_id):
    with tasks_lock:
        task = tasks.get(task_id)
        if task:
            return jsonify(task)

    # Disk fallback for multi-worker Gunicorn / Render
    out_path, filename = find_output_file(task_id)
    if out_path:
        return jsonify({
            'status': 'completed',
            'progress': 100.0,
            'message': 'Successfully converted!',
            'filename': filename
        })

    return jsonify({'error': 'Task not found'}), 404

@app.route('/api/download/<task_id>', methods=['GET'])
def api_download(task_id):
    out_path, filename = find_output_file(task_id)

    if not out_path or not os.path.exists(out_path):
        return jsonify({'error': 'File not found on server'}), 404

    return send_file(
        out_path,
        as_attachment=True,
        download_name=filename,
        mimetype='text/csv'
    )

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    print(f"Server starting on http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
