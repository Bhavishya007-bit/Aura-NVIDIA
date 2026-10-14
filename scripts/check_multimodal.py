"""Read-only teammate setup report; never print secrets or source contents."""
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
import requests
load_dotenv(Path(__file__).resolve().parents[1]/'backend'/'.env')
try:
    health = requests.get('http://127.0.0.1:8000/health', timeout=5).json()
    print('Running tutor version:', health.get('tutor_version','OLD VERSION: restart/update backend'))
except Exception:
    print('Backend health unavailable: stop the old backend and start the updated server.')
model = os.getenv('OLLAMA_VISION_MODEL','').strip()
print('Configured vision model:', model or 'MISSING')
try:
    base = os.getenv('OLLAMA_BASE_URL','http://localhost:11434').rstrip('/')
    if base.endswith('/api/chat'):base = base[:-9]
    models = requests.get(base+'/api/tags',timeout=5)
    models.raise_for_status()
    names = {item['name'] for item in models.json().get('models',[])}
    print('Configured vision model installed:', bool(model and (model in names or model+':latest' in names)))
except Exception:
    print('Ollama model check unavailable: verify Ollama is running on this laptop.')
from backend.auth_db import get_auth_connection
try:
    connection = get_auth_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute('''SELECT s.source_id,s.source_name,s.source_type,s.status,
                COUNT(c.chunk_id),COUNT(c.embedding) FROM sources s LEFT JOIN chunks c
                ON c.source_id=s.source_id GROUP BY s.source_id,s.source_name,s.source_type,s.status
                ORDER BY s.source_id DESC LIMIT 10''')
            print('ID | File | Type | Status | Chunks | Indexed')
            for row in cursor.fetchall():print(' | '.join(str(v) for v in row))
    finally:connection.close()
except Exception as error:
    print('Database check failed:', type(error).__name__, '(check your existing database configuration)')
