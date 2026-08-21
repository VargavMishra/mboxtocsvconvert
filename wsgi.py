import os
from app import app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    
    try:
        from waitress import serve
        print(f"Serving production app via Waitress on http://{host}:{port}")
        serve(app, host=host, port=port)
    except ImportError:
        print(f"Serving production app via Flask WSGI on http://{host}:{port}")
        app.run(host=host, port=port)
