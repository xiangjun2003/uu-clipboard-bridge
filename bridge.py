#!/usr/bin/env python3
"""Two-Mac clipboard bridge. Server binds loopback; client uses UU TCP forwarding.
No clipboard history on disk. Payloads and authentication tokens are never logged.
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_RAW = 20 * 1024 * 1024
MAX_BODY = (MAX_RAW * 4 // 3) + 8192

def log(message):
    print(time.strftime('%Y-%m-%d %H:%M:%S'), message, flush=True)

def validate(value):
    if not isinstance(value, dict) or value.get('type') not in ('image', 'text'):
        raise ValueError('unsupported type')
    encoded = value.get('data')
    if not isinstance(encoded, str) or len(encoded) > MAX_BODY:
        raise ValueError('payload too large')
    raw = base64.b64decode(encoded, validate=True)
    if len(raw) > MAX_RAW:
        raise ValueError('payload too large')
    if value['type'] == 'text':
        raw.decode('utf-8')
    elif not raw.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('PNG required')
    return {'type': value['type'], 'data': encoded,
            'hash': hashlib.sha256(value['type'].encode() + b'\0' + raw).hexdigest(),
            'bytes': len(raw)}

class Pasteboard:
    def __init__(self, helper, on_copy):
        self.on_copy = on_copy
        self.lock = threading.RLock()
        self.acks = {}
        self.last_hash = None
        self.process = subprocess.Popen([str(helper)], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, text=True, bufsize=1)
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        try:
            for line in self.process.stdout:
                msg = json.loads(line)
                if msg.get('kind') == 'ack':
                    with self.lock:
                        ack = self.acks.get(msg.get('id'))
                    if ack:
                        ack[1].append(bool(msg.get('ok')))
                        ack[0].set()
                elif msg.get('kind') == 'clipboard':
                    value = validate(msg)
                    with self.lock:
                        if value['hash'] == self.last_hash:
                            continue
                        self.last_hash = value['hash']
                    self.on_copy(value)
        except Exception as exc:
            log('pasteboard reader error: ' + type(exc).__name__)
        finally:
            if self.process.poll() is not None:
                log('pasteboard helper exited')

    def write(self, value):
        value = validate(value)
        identity = os.urandom(12).hex()
        ack = (threading.Event(), [])
        with self.lock:
            self.acks[identity] = ack
            self.last_hash = value['hash']
            self.process.stdin.write(json.dumps(dict(value, id=identity)) + '\n')
            self.process.stdin.flush()
        try:
            if not ack[0].wait(5) or not ack[1] or not ack[1][0]:
                raise RuntimeError('clipboard write failed')
        finally:
            with self.lock:
                self.acks.pop(identity, None)

class State:
    def __init__(self):
        self.condition = threading.Condition(threading.RLock())
        self.version = 0
        self.event = None
        self.last_received = None
        self.applied = 0

    def publish(self, value, origin):
        with self.condition:
            self.version += 1
            self.event = dict(value, version=self.version, origin=origin)
            self.condition.notify_all()
            return self.version

def serve(config, helper):
    state = State()
    def copied(value):
        state.publish(value, 'server')
        log('captured type=%s bytes=%s' % (value['type'], value['bytes']))
    board = Pasteboard(helper, copied)
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        def setup(self):
            super().setup()
            self.connection.settimeout(30)
        def handle(self):
            try:
                super().handle()
            except (ConnectionResetError, BrokenPipeError, TimeoutError):
                pass  # A peer closing an idle/persistent connection is normal.
        def log_message(self, *_):
            pass
        def authorized(self):
            expected = 'Bearer ' + config['token']
            if not hmac.compare_digest(self.headers.get('Authorization', ''), expected):
                self.respond(401, {'error': 'unauthorized'})
                return False
            return True
        def respond(self, status, value):
            # UU may drop response bytes when the server immediately closes TCP.
            self.close_connection = False
            data = json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass
        def do_GET(self):
            if not self.authorized(): return
            url = urllib.parse.urlsplit(self.path)
            if url.path == '/status':
                with state.condition:
                    self.respond(200, {'version': state.version, 'applied': state.applied,
                        'lastReceived': state.last_received, 'helperAlive': board.process.poll() is None})
            elif url.path == '/poll':
                try:
                    after = int(urllib.parse.parse_qs(url.query).get('after', ['0'])[0])
                except ValueError:
                    return self.respond(400, {'error': 'invalid cursor'})
                with state.condition:
                    state.condition.wait_for(lambda: state.version > after, timeout=1)
                    event = state.event if state.version > after else None
                    self.respond(200, {'version': state.version, 'event': event})
            else:
                self.respond(404, {'error': 'not found'})
        def do_POST(self):
            if not self.authorized(): return
            if self.path != '/clipboard': return self.respond(404, {'error': 'not found'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= MAX_BODY: raise ValueError('invalid length')
                self.connection.settimeout(15)
                value = validate(json.loads(self.rfile.read(length)))
                board.write(value)
                with state.condition:
                    version = state.publish(value, 'client')
                    state.applied += 1
                    state.last_received = {k: value[k] for k in ('type', 'hash', 'bytes')}
                log('received type=%s bytes=%s' % (value['type'], value['bytes']))
                self.respond(200, {'version': version, 'hash': value['hash']})
            except (ValueError, TypeError, KeyError, UnicodeError):
                self.respond(400, {'error': 'invalid clipboard payload'})
            except Exception as exc:
                log('write error: ' + type(exc).__name__)
                self.respond(500, {'error': 'clipboard write failed'})
    server = ThreadingHTTPServer(('127.0.0.1', config.get('port', 24130)), Handler)
    server.daemon_threads = True
    log('server listening on loopback port=%s' % server.server_port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        board.process.terminate()

def client(config, helper):
    lock = threading.RLock()
    pending = [None]
    def copied(value):
        with lock:
            pending[0] = (time.monotonic(), value)
        log('captured type=%s bytes=%s' % (value['type'], value['bytes']))
    board = Pasteboard(helper, copied)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    endpoint = config.get('endpoint', 'http://127.0.0.1:24131').rstrip('/')
    if urllib.parse.urlsplit(endpoint).hostname != '127.0.0.1':
        raise ValueError('client must connect to the local UU mapping')
    def request(path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(endpoint + path, data=data, headers={
            'Authorization': 'Bearer ' + config['token'], 'Content-Type': 'application/json'})
        with opener.open(req, timeout=20) as response:
            return json.load(response)
    cursor = None
    connected = False
    try:
        while True:
            try:
                if cursor is None:
                    cursor = request('/status')['version']
                if not connected:
                    log('connected via UU endpoint=' + endpoint)
                    connected = True
                with lock:
                    item = pending[0]
                if item:
                    if time.monotonic() - item[0] < 120:
                        result = request('/clipboard', item[1])
                        cursor = result['version']
                        log('sent type=%s bytes=%s' % (item[1]['type'], item[1]['bytes']))
                    with lock:
                        if pending[0] is item: pending[0] = None
                result = request('/poll?after=' + str(cursor))
                cursor = result['version']
                event = result.get('event')
                if event and event['origin'] == 'server':
                    with lock:
                        should_apply = pending[0] is None
                    if should_apply:
                        value = validate(event)
                        board.write(value)
                        log('received type=%s bytes=%s' % (value['type'], value['bytes']))
            except Exception as exc:
                if connected:
                    log('disconnected: ' + type(exc).__name__)
                connected = False
                cursor = None  # Never replay old server clipboard after reconnect.
                time.sleep(2)
    finally:
        board.process.terminate()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['server', 'client'])
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    if len(config.get('token', '')) < 32: raise ValueError('token too short')
    helper = Path(__file__).resolve().parent / 'pasteboard'
    (serve if args.mode == 'server' else client)(config, helper)

if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    main()
