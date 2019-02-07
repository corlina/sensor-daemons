import socket
import json
import struct
import threading
import select
import time
import logging


log = logging.getLogger(__name__)


class CTSocketClient(object):

    CT_AGENT_SOCKET_PATH = '/opt/corlina/var/event.sock'

    def __init__(self, client_id, event_types,
                 on_config_enabled, on_config_disabled,
                 socket_path=None, bufsize=10):
        self.client_id = client_id
        self.event_types = event_types
        self.socket_path = socket_path or self.CT_AGENT_SOCKET_PATH
        self.on_config_enabled = on_config_enabled
        self.on_config_disabled = on_config_disabled
        self._sock = None
        self._interrupt_socks = socket.socketpair()
        self._thread = None
        self._stopped = threading.Event()
        self._connected = threading.Event()
        self._buffer = []
        self.bufsize = 10

        # lock guards concurrent access on socket when reconnecting
        self._lock = threading.RLock()

    def start(self):
        if self._thread is not None:
            raise RuntimeError("Already started")
        self._stopped.clear()
        self._thread = threading.Thread(target=self._loop)
        self._thread.setDaemon(True)
        self._thread.start()

    def send_event(self, event_type, data):
        self._send({'event_type': event_type, 'data': data})

    def stop(self):
        self._stopped.set()
        self._interrupt_socks[1].send('\0')
        self._thread.join()
        self._interrupt_socks[0].recv(1)
        self._thread = None

    def _reconnect(self):
        while not self._stopped.isSet():
            with self._lock:
                self._close_if_open()
                self._sock = socket.socket(socket.AF_UNIX)
                self._sock.setblocking(0)
            try:
                self._sock.connect(self.socket_path)
            except socket.error as exc:
                log.error('%r: error while connecting: %r; backoff=10sec', self, exc)
                self._stopped.wait(10)
            else:
                self._connected.set()
                log.info('%r: connected', self)
                return

    def _send(self, contents):
        with self._lock:
            if not self._connected.isSet():
                log.warning('%r: not connected, buffering message: %s', self, contents)
                self._buffer.append(contents)
                if len(self._buffer) > self.bufsize:
                    removed = self._buffer.pop(0)
                    log.warning('%r: dropping message from buffer: %s', self, removed)
            else:
                log.info('%r: sending message: %s', self, contents)
                data = json.dumps(contents)
                header = struct.pack('>I', len(data))
                self._sock.send(header + data)

    def _send_hello(self):
        self._send({
            'client_id': self.client_id,
            'event_types': self.event_types,
        })

    def _loop(self):
        while not self._stopped.isSet():
            self._reconnect()
            if self._stopped.isSet():
                return
            try:
                self._send_hello()
                self._send_buffered()
                while not self._stopped.isSet():
                    self._process_one(self._read_one())
            except socket.error as err:
                log.error('%r: Error while reading message: %s', self, err)
            except _ReadInterrupted:
                self._close_if_open()

    def _read_one(self):
        [msg_len] = struct.unpack('>I', self._read_data(_HEADER_LEN))
        data = self._read_data(msg_len)
        return json.loads(data)

    def _read_data(self, length):
        result = ''
        while len(result) < length and not self._stopped.isSet():
            rlist, _, _ = select.select([
                self._sock.fileno(),
                self._interrupt_socks[0].fileno()
            ], [], [])
            if self._interrupt_socks[0].fileno() in rlist:
                raise _ReadInterrupted
            result += self._sock.recv(length - len(result))
        return result

    def _process_one(self, contents):
        log.info('%r: incoming: %s', self, contents)
        cfg_enabled = contents['config_state_enabled']
        event_type = contents['event_type']
        options = contents['options']

        if cfg_enabled:
            if callable(self.on_config_enabled):
                self.on_config_enabled(event_type, options)
        else:
            if callable(self.on_config_disabled):
                self.on_config_disabled(event_type, options)

    def _send_buffered(self):
        with self._lock:
            log.info('%r: sending buffered messages')
            n_messages = len(self._buffer)
            for _ in range(n_messages):
                msg = self._buffer.pop(0)
                self._send(msg)

    def _close_if_open(self):
        with self._lock:
            if self._sock is not None:
                self._sock.close()
                self._sock = None
                log.info('%r: closed', self)
        self._connected.clear()

    def __repr__(self):
        return '<id="{}" addr="{}">'.format(self.client_id, self.socket_path)


class _ReadInterrupted(Exception):
    pass


_HEADER_LEN = struct.calcsize('>I')

