"""Read-only preparation diagnostics: no model calls or document contents."""
import os

def main():
    print('Embedding device:',os.getenv('AURA_EMBEDDING_DEVICE','auto'))
    print('CPU threads setting:',os.getenv('AURA_EMBEDDING_THREADS','adaptive (up to 4)'))
    print('Embedding batch setting:',os.getenv('AURA_EMBEDDING_BATCH_SIZE','adaptive'))
    print('Vision configured:',bool(os.getenv('OLLAMA_VISION_MODEL','').strip()))
    try:
        from backend.auth_db import get_auth_connection
        con=get_auth_connection()
        try:
            with con.cursor() as cur:
                cur.execute("SELECT state,stage,completed,total,EXTRACT(EPOCH FROM NOW()-created_at)::int,EXTRACT(EPOCH FROM NOW()-updated_at)::int FROM aura_preparation_jobs ORDER BY created_at DESC LIMIT 5")
                rows=cur.fetchall()
                for i,(state,stage,done,total,age,idle) in enumerate(rows,1):
                    print(f'Upload {i}: {state}; stage={stage}; step={done}/{total}; age={age}s; last_update={idle}s ago')
                if not rows:print('No preparation jobs in this database. Run this on the computer handling the upload.')
        finally:con.close()
    except Exception as error:
        print('Preparation status unavailable:',type(error).__name__);return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
