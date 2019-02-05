import threading
import logging
import time


log = logging.getLogger(__name__)


class TestingEventTracker(object):

    EVENT_TYPE = 'MANUAL_TRIGGER'

    def __init__(self, client, program):
        self.client = client
        self._lock = threading.Lock()
        self._config_state = False
        self._program = program

    def run(self):
        for cmd in self._program:
            key, _, val = cmd.partition('=')
            if key == 'wait':
                time.sleep(float(val))
            elif key == 'send':
                with self._lock:
                    if self._config_state:
                        log.error("daemon in config state, not sending anything")
                        continue
                self.client.send_event(self.EVENT_TYPE, {'text': val})
            else:
                raise ValueError("Unknown command: {}".format(cmd))

    def on_config_enabled(self, etype, params):
        with self._lock:
            self._config_state = True

    def on_config_disabled(self, etype, params):
        with self._lock:
            self._config_state = False
