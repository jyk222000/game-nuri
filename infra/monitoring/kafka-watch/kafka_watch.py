#!/usr/bin/env python3
"""kafka_watch: Kafka 브로커(9092)·컨트롤러(9093) 접속 확인 + KRaft 리더 조회. 표준 라이브러리만 사용."""
import os, re, socket, subprocess, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LISTEN = os.environ.get("KW_LISTEN", "10.0.2.1")
PORT = int(os.environ.get("KW_PORT", "9399"))
QUORUM_BIN = os.environ.get("KW_QUORUM_BIN", "/opt/kafka/bin/kafka-metadata-quorum.sh")
BOOTSTRAP = os.environ.get("KW_BOOTSTRAP", "kafka1:9092,kafka2:9092,kafka3:9092")
CHECK_EVERY = 2.0
QUORUM_EVERY = 30.0
FAILS_TO_DOWN = 2

TARGETS = [("broker", "kafka1", 1, 9092), ("broker", "kafka2", 2, 9092), ("broker", "kafka3", 3, 9092),
           ("controller", "kafka1", 1, 9093), ("controller", "kafka2", 2, 9093), ("controller", "kafka3", 3, 9093),
           ("controller", "backup", 4, 9093), ("controller", "monitoring", 5, 9093)]
if os.environ.get("KW_TEST_PORT_BASE"):
    b = int(os.environ["KW_TEST_PORT_BASE"])
    TARGETS = [(k, h, n, b + i) for i, (k, h, n, _) in enumerate(TARGETS)]

lock = threading.Lock()
state = {t: {"up": None, "fails": 0, "events": 0, "down_s": 0.0, "last_down": 0.0, "last_check": 0.0} for t in TARGETS}
quorum = {"ok": 0, "ts": 0.0, "leader": None, "epoch": None, "lag": {}, "fetch_ts": {}, "voters": 0}

def tcp_ok(host, port):
    if os.environ.get("KW_TEST_PORT_BASE"):
        host = "127.0.0.1"
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False

def check_loop():
    while True:
        t0 = time.time()
        res = {}
        def one(t):
            res[t] = tcp_ok(t[1], t[3])
        ths = [threading.Thread(target=one, args=(t,)) for t in TARGETS]
        [x.start() for x in ths]; [x.join() for x in ths]
        now = time.time()
        with lock:
            for t, ok in res.items():
                s = state[t]
                prev_check = s["last_check"]; s["last_check"] = now
                if ok:
                    s["fails"] = 0
                    s["up"] = 1
                else:
                    s["fails"] += 1
                    if s["fails"] >= FAILS_TO_DOWN:
                        if s["up"] != 0:
                            s["events"] += 1
                            s["last_down"] = now
                        s["up"] = 0
                if s["up"] == 0 and prev_check:
                    s["down_s"] += now - prev_check
        time.sleep(max(0.0, CHECK_EVERY - (time.time() - t0)))

def run_q(sub):
    env = dict(os.environ, KAFKA_HEAP_OPTS="-Xmx64m -Xms32m")
    env.pop("JMX_PORT", None); env.pop("KAFKA_JMX_OPTS", None)
    return subprocess.run([QUORUM_BIN, "--bootstrap-server", BOOTSTRAP, "describe", sub],
                          capture_output=True, text=True, timeout=20, env=env).stdout

def quorum_loop():
    while True:
        t0 = time.time()
        try:
            st = run_q("--status"); rp = run_q("--replication")
            leader = re.search(r"LeaderId:\s+(\d+)", st); epoch = re.search(r"LeaderEpoch:\s+(\d+)", st)
            voters = re.search(r"CurrentVoters:\s+\[([\d,\s]*)\]", st)
            lag, fts = {}, {}
            for line in rp.splitlines():
                f = line.split()
                if len(f) >= 6 and f[0].isdigit():
                    lag[int(f[0])] = int(f[2]); fts[int(f[0])] = int(f[3]) / 1000.0
            if not (leader and epoch and lag):
                raise ValueError("parse")
            with lock:
                quorum.update(ok=1, ts=time.time(), leader=int(leader.group(1)), epoch=int(epoch.group(1)), lag=lag,
                              fetch_ts=fts, voters=len([x for x in voters.group(1).split(",") if x.strip()]) if voters else 0)
        except Exception:
            with lock:
                quorum.update(ok=0, leader=None, lag={}, fetch_ts={})
        time.sleep(max(1.0, QUORUM_EVERY - (time.time() - t0)))

def render():
    o = []
    a = o.append
    with lock:
        a("# TYPE kafka_watch_up gauge"); a("# TYPE kafka_watch_down_events_total counter"); a("# TYPE kafka_watch_down_seconds_total counter")
        for (kind, host, nid, port), s in state.items():
            if s["up"] is None: continue
            lb = 'kind="%s",host="%s",node_id="%d"' % (kind, host, nid)
            a("kafka_watch_up{%s} %d" % (lb, s["up"]))
            a("kafka_watch_down_events_total{%s} %d" % (lb, s["events"]))
            a("kafka_watch_down_seconds_total{%s} %.1f" % (lb, s["down_s"]))
            a("kafka_watch_last_down_timestamp_seconds{%s} %.0f" % (lb, s["last_down"]))
        a("kafka_watch_quorum_ok %d" % quorum["ok"])
        if quorum["ok"]:
            a("kafka_watch_quorum_update_timestamp_seconds %.0f" % quorum["ts"])
            a("kafka_watch_quorum_leader_id %d" % quorum["leader"])
            a("kafka_watch_quorum_leader_epoch %d" % quorum["epoch"])
            a("kafka_watch_quorum_voters %d" % quorum["voters"])
            for n, l in quorum["lag"].items():
                a('kafka_watch_controller_leader{node_id="%d"} %d' % (n, 1 if n == quorum["leader"] else 0))
                a('kafka_watch_controller_lag{node_id="%d"} %d' % (n, l))
                a('kafka_watch_controller_last_fetch_age_seconds{node_id="%d"} %.1f' % (n, max(0.0, quorum["ts"] - quorum["fetch_ts"][n])))
    return "\n".join(o) + "\n"

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = render().encode()
        self.send_response(200); self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass

if __name__ == "__main__":
    threading.Thread(target=check_loop, daemon=True).start()
    threading.Thread(target=quorum_loop, daemon=True).start()
    ThreadingHTTPServer((LISTEN, PORT), H).serve_forever()
