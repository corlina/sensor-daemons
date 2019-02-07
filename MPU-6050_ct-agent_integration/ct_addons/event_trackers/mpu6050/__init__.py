from __future__ import absolute_import
import threading
import time
import socket
import struct
import logging
import math
from ct_addons.event_trackers.mpu6050 import data_source, motion_tracker


log = logging.getLogger(__name__)


class Mpu6050EventTracker(object):

    EVENT_TYPE = 'corlina.mpu6050'

    def __init__(self, client, accel_offsets, run_server_at_port=None):
        self.client = client
        self._stopped = threading.Event()
        generator = data_source.mpu6050_data_generator(0.011, self._stopped)
        generator = data_source.dump_to_file(generator, 'data.txt', 1000)
        generator = data_source.motiontracker_data_generator(
            generator,
            motion_tracker.MotionTracker(0.5, 0.011, accel_offsets=accel_offsets),
            calibrate_n=300,
        )
        self.streamer = data_source.DataStreamer(generator)
        self.streamer.add_consumer(self._react_for_epoch_condition)
        self._run_server_at_port = run_server_at_port

        self._lock = threading.Lock()
        self._config_state = False
        self._max_angle_deviation = 30.0
        self._max_lateral_movement = 0.2
        self._min_temp = 15
        self._max_temp = 45
        self._temp_blind_zone = 1
        self._temp_min_histeresis_state = 0
        self._temp_max_histeresis_state = 0
        assert 2 * self._temp_blind_zone < self._max_temp - self._min_temp
        self._is_in_epoch_condition = {
            'ORIENTATION': False,
            'MOVEMENT': False,
            'TEMPERATURE': False,
        }

    def _react_for_epoch_condition(self,
                                   accx, accy, accz,
                                   gyrox, gyroy, gyroz,
                                   temp,
                                   anglex, angley, anglez,
                                   latx, laty, latz):
        with self._lock:
            if self._config_state:
                return
        self._react_for_movement_epoch_condition(latx, laty, latz)
        self._react_for_orientation_epoch_condition(anglex, angley, anglez)
        self._react_for_temperature_epoch_condition(temp)

    def _react_for_orientation_epoch_condition(self, anglex, angley, anglez):
        maxdev = max(abs(anglex), abs(angley), abs(anglez))
        now_in_condition = maxdev > self._max_angle_deviation
        need_epoch = now_in_condition != self._is_in_epoch_condition['ORIENTATION']
        if need_epoch:
            log.info('met ORIENTATION Epoch condition: %s',
                     'IN' if now_in_condition else 'OUT')
            if now_in_condition:
                data = {'x': anglex, 'y': angley, 'z': anglez}
                self.client.send_event('ORIENTATION', data)
        self._is_in_epoch_condition['ORIENTATION'] = now_in_condition

    def _react_for_movement_epoch_condition(self, latx, laty, latz):
        movement = math.sqrt(latx**2 + laty**2 + latz**2)
        now_in_condition = movement > self._max_lateral_movement
        need_epoch = now_in_condition != self._is_in_epoch_condition['MOVEMENT']
        if need_epoch:
            log.info('met MOVEMENT Epoch condition: %s',
                     'IN' if now_in_condition else 'OUT')
            if now_in_condition:
                data = {'x': latx, 'y': laty, 'z': latz}
                self.client.send_event('MOVEMENT', data)
        self._is_in_epoch_condition['MOVEMENT'] = now_in_condition

    def _react_for_temperature_epoch_condition(self, temp):
        min_in_condition = temp < self._min_temp + self._temp_min_histeresis_state
        max_in_condition = temp > self._max_temp + self._temp_max_histeresis_state
        now_in_condition = min_in_condition or max_in_condition
        condition_changed = now_in_condition != self._is_in_epoch_condition['TEMPERATURE']
        if condition_changed:
            log.info('met TEMPERATURE Epoch condition: %s',
                     'IN' if now_in_condition else 'OUT')
            if now_in_condition:
                data = {'temp': temp}
                self.client.send_event('TEMPERATURE', data)
            if max_in_condition:
                self._temp_min_histeresis_state = -self._temp_blind_zone
                self._temp_max_histeresis_state = -self._temp_blind_zone
            elif min_in_condition:
                self._temp_min_histeresis_state = +self._temp_blind_zone
                self._temp_max_histeresis_state = +self._temp_blind_zone
            else:
                self._temp_min_histeresis_state = -self._temp_blind_zone
                self._temp_max_histeresis_state = +self._temp_blind_zone
        self._is_in_epoch_condition['TEMPERATURE'] = now_in_condition

    def run(self):
        try:
            if self._run_server_at_port is None:
                while True:
                    time.sleep(1)
            else:
                run_server(self._run_server_at_port, self.streamer)
        finally:
            log.info('interrupted, exiting gracefully...')
            self._stopped.set()
            self.streamer.request_stop()
            self.streamer.wait_for_end()

    def on_config_enabled(self, etype, params):
        with self._lock:
            self._config_state = True
            self._max_angle_deviation = params.get('max_angle_deviation', self._max_angle_deviation)

    def on_config_disabled(self, etype, params):
        with self._lock:
            self._config_state = False


def run_server(port, streamer):
    serversock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serversock.bind(('0.0.0.0', port))
    serversock.listen(3)
    while True:
        sock, addr = serversock.accept()
        cons = ClientConsumer(sock, streamer)
        log.info('connected client: %s -> %r', addr, cons)
        cid = streamer.add_consumer(cons)
        cons.consumer_id = cid


class ClientConsumer(object):
    def __init__(self, sock, streamer):
        self.sock = sock
        self.streamer = streamer
        self.consumer_id = None

    def __call__(self, *data):
        packet = struct.pack('f' * len(data), *data)
        try:
            self.sock.send(packet)
        except socket.error:
            if self.consumer_id is not None:
                self.streamer.remove_consumer(self.consumer_id)
                self.consumer_id = None
