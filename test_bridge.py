import base64
import json
import multiprocessing
import socket
import time
import unittest
import urllib.error
import urllib.request

import bridge

class FakePasteboard:
    def __init__(self, helper, callback):
        self.callback = callback
        self.process = type('Process', (), {'poll': lambda _: None, 'terminate': lambda _: None})()
    def write(self, value):
        bridge.validate(value)

def run_server(port):
    bridge.Pasteboard = FakePasteboard
    bridge.serve({'token': 'x' * 64, 'port': port}, None)

class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            cls.port = s.getsockname()[1]
        cls.proc = multiprocessing.Process(target=run_server, args=(cls.port,))
        cls.proc.start()
        cls.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(60):
            try:
                cls.request('/status')
                break
            except OSError:
                time.sleep(.05)
        else:
            raise RuntimeError('server did not start')
    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.join(3)
    @classmethod
    def request(cls, route, value=None, token='x' * 64):
        req = urllib.request.Request('http://127.0.0.1:%s%s' % (cls.port, route),
            data=json.dumps(value).encode() if value is not None else None,
            headers={'Authorization': 'Bearer ' + token})
        with cls.opener.open(req, timeout=4) as response:
            return json.load(response)
    def test_auth_required(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request('/status', token='wrong')
        self.assertEqual(ctx.exception.code, 401)
    def test_text_roundtrip_and_metadata(self):
        v = {'type': 'text', 'data': base64.b64encode('图片测试 hello'.encode()).decode()}
        result = self.request('/clipboard', v)
        event = self.request('/poll?after=' + str(result['version'] - 1))['event']
        self.assertEqual(event['data'], v['data'])
        self.assertEqual(event['origin'], 'client')
        self.assertEqual(self.request('/status')['lastReceived']['hash'], bridge.validate(v)['hash'])
    def test_image_and_invalid_image(self):
        raw = base64.b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAEAAAAAwCAIAAAAuKetIAAAAZElEQVR4nO3PUQkAIBTAwFfN'
            'MmY3hiH8OITBAtzmrP11wwUNaEEDWtCAFjSgBQ1oQQNa0IAWNKAFDWhBA1rQgBY0oAUN'
            'aEEDWtCAFjSgBQ1oQQNa0IAWNKAFDWhBA1rQgBY8dgHxzrUPX9UZVwAAAABJRU5ErkJggg==')
        v = {'type': 'image', 'data': base64.b64encode(raw).decode()}
        result = self.request('/clipboard', v)
        event = self.request('/poll?after=' + str(result['version'] - 1))['event']
        self.assertEqual(base64.b64decode(event['data']), raw)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request('/clipboard', {'type': 'image', 'data': 'YWJj'})
        self.assertEqual(ctx.exception.code, 400)
    def test_stale_cursor_no_payload(self):
        version = self.request('/status')['version']
        self.assertIsNone(self.request('/poll?after=' + str(version))['event'])
    def test_reject_file_and_invalid_base64(self):
        for v in ({'type': 'file', 'data': ''}, {'type': 'text', 'data': '!!!'}):
            with self.assertRaises(ValueError): bridge.validate(v)

if __name__ == '__main__':
    unittest.main()
