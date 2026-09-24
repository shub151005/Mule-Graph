import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from .db import connection, encode, now

pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='mulegraph')
lock = threading.Lock()

def submit(kind, work):
    with lock, connection() as c:
        pending = c.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
        if pending >= 3:
            raise ValueError('Three jobs are already queued. Wait for completion before submitting more.')
        jid = uuid.uuid4().hex
        c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)', (jid,kind,'queued',0,'Queued',now(),now(),None))
    def progress(percent, message):
        with connection() as c:
            c.execute("UPDATE jobs SET progress=?,message=?,updated_at=? WHERE id=?", (percent,message,now(),jid))
    def run():
        try:
            with connection() as c:
                c.execute("UPDATE jobs SET status='running',updated_at=? WHERE id=?", (now(),jid))
            result = work(progress)
            with connection() as c:
                c.execute("UPDATE jobs SET status='completed',progress=100,message='Completed',result=?,updated_at=? WHERE id=?", (encode(result),now(),jid))
        except Exception as exc:
            traceback.print_exc()
            with connection() as c:
                c.execute("UPDATE jobs SET status='failed',message=?,updated_at=? WHERE id=?", (str(exc)[:1000],now(),jid))
    pool.submit(run)
    return {'job_id': jid}
