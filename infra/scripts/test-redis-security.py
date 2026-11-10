"""Verify Redis ACL isolation and real Celery broker compatibility."""
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import uuid

from celery import Celery
from redis import Redis
from redis.exceptions import RedisError


def docker(*args, **kwargs):
    return subprocess.run(["docker",*args],check=True,text=True,capture_output=True,**kwargs).stdout.strip()


def main():
    root = Path(__file__).resolve().parents[2]
    name = "redis-security-"+uuid.uuid4().hex[:12]
    broker_pass, auth_pass = secrets.token_hex(32), secrets.token_hex(32)
    env = {**os.environ,"REDIS_PASSWORD":broker_pass,"AUTH_REDIS_PASSWORD":auth_pass}
    try:
        docker("run","-d","--name",name,"--user","redis","-p","127.0.0.1::6379",
            "-e","REDIS_PASSWORD","-e","AUTH_REDIS_PASSWORD",
            "-v",f"{(root/'infra/redis/start.sh').as_posix()}:/etc/redis/start.sh:ro",
            "redis:7-alpine@sha256:7b1753b4c5ad8458906c272a8132b8c15f5557b000379eb115fb239706a384b7",
            "sh","/etc/redis/start.sh",env=env)
        address = docker("port",name,"6379/tcp").splitlines()[0]
        auth_url=f"redis://auth:{auth_pass}@{address}/1"
        broker_url=f"redis://broker:{broker_pass}@{address}/0"
        auth, broker = Redis.from_url(auth_url,socket_timeout=2), Redis.from_url(broker_url,socket_timeout=2)
        for attempt in range(60):
            try:
                auth.ping();break
            except RedisError:
                if attempt==59:raise
                time.sleep(0.5)
        auth.setex("2fa_challenge:test",30,"private")
        for client, key in ((broker,"2fa_challenge:test"),(auth,"private")):
            try:client.get(key)
            except RedisError:pass
            else:raise AssertionError("ACL cross-service access allowed")
        for client in (broker,auth):
            try:client.config_get("*")
            except RedisError:pass
            else:raise AssertionError("Redis administration permitted")
        broker_db_one=Redis.from_url(broker_url.rsplit('/',1)[0]+'/1')
        try:broker_db_one.get("2fa_challenge:test")
        except RedisError:pass
        else:raise AssertionError("Database switching bypassed key ACL")
        app=Celery("acl-probe",broker=broker_url,backend=broker_url)
        app.conf.update(task_default_queue="private",task_serializer="json",accept_content=["json"])
        app.send_task("app.workers.tasks.healthcheck",queue="private")
        with app.connection() as connection:
            queue=connection.SimpleQueue("private")
            message=queue.get(block=False)
            assert message.headers["task"]=="app.workers.tasks.healthcheck"
            message.ack();queue.close()
        app.backend.store_result("probe","ok","SUCCESS")
        assert app.backend.get_task_meta("probe")["result"]=="ok"
        # Full startup exercises Kombu's Lua locks and worker control channels,
        # which a send/pop-only probe does not cover.
        script = '''import os
from celery import Celery
app=Celery("acl-probe",broker=os.environ["PROBE_BROKER"],backend=os.environ["PROBE_BROKER"])
app.conf.update(task_default_queue="private",task_serializer="json",accept_content=["json"])
app.worker_main(["worker","--pool=solo","--concurrency=1","-Q","private","--loglevel=ERROR"])
'''
        process=subprocess.Popen([sys.executable,"-c",script],env={**os.environ,"PROBE_BROKER":broker_url},
                                 stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            for attempt in range(30):
                if app.control.ping(timeout=1):break
                assert process.poll() is None,"Celery worker failed during startup"
                time.sleep(0.5)
            else:raise AssertionError("Celery control channel did not become ready")
        finally:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill();process.wait(timeout=5)
        app.close();auth.close();broker.close();broker_db_one.close()
        print("PASS Redis ACLs: authentication keys isolated, administration denied, Celery delivery and results work")
    finally:
        subprocess.run(["docker","rm","-f","-v",name],capture_output=True)


if __name__=="__main__":main()
