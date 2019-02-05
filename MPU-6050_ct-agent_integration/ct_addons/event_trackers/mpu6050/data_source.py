import time
import Queue
import threading
import logging


log = logging.getLogger(__name__)


def mpu6050_data_generator(dt, stopped):
    from mpu6050 import mpu6050
    sensor = mpu6050(0x68)

    # try to poll the sensor until it configures properly
    started_at = time.time()
    last_err = None
    while time.time() < started_at + 1:
        try:
            sensor.get_all_data()
        except IOError as err:
            last_err = err
            time.sleep(0.02)
        else:
            break
    else:
        raise IOError('MPU6050 reading fails: {}'.format(str(last_err)))

    while not stopped.isSet():
        start = time.time()
        accel = sensor.get_accel_data()
        gyro = sensor.get_gyro_data()
        temp = sensor.get_temp()
        item = accel['x'], accel['y'], accel['z'], gyro['x'], gyro['y'], gyro['z'], temp
        yield item
        duration = time.time() - start
        if dt > duration:
            time.sleep(dt - duration)


def motiontracker_data_generator(mpu_generator, tracker, calibrate_n=0):
    if calibrate_n > 0:
        log.info('starting calibration, don\'t move the device...')
        tracker.start_calibration()
        for _ in range(calibrate_n):
            item = next(mpu_generator)
            tracker.add_data(*item[:-1])  # last item is temperature
        tracker.finish_calibration()
        log.info('calibration finished')
    for item in mpu_generator:
        tracker.add_data(*item[:-1])  # last item is temperature
        yield item + tracker.angles + tracker.coordinates


class DataStreamer(object):

    def __init__(self, generator, max_queue_size=1000, consumer_timeout=0.01):
        self.max_queue_size = max_queue_size
        self.consumer_timeout = consumer_timeout
        self._consumers = {}
        self._next_id = 1
        self._lock = threading.Lock()
        self._stopped = threading.Event()
        self._generator = generator
        self._thread = threading.Thread(target=self._run)
        self._thread.setDaemon(True)
        self._thread.start()

    def add_consumer(self, function):
        with self._lock:
            if self._stopped.isSet():
                return
            queue = Queue.Queue(maxsize=self.max_queue_size)
            consumer_thread = threading.Thread(target=self._consumer_run,
                                               args=(queue, function))
            consumer_thread.setDaemon(True)
            consumer_thread.start()
            new_id = self._next_id
            self._next_id += 1
            self._consumers[new_id] = (queue, function, consumer_thread)
        log.info('added new consumer: %r -> %s', function, new_id)
        return new_id

    def request_stop(self):
        self._stopped.set()

    def remove_consumer(self, consumer_id):
        with self._lock:
            q, f, t = self._consumers.pop(consumer_id)
        try:
            while True:
                q.get_nowait()
        except Queue.Empty:
            q.put(None)
        blocking = threading.currentThread().ident != t.ident
        log.info('removing consumer: %r -> %s %s',
                 f, consumer_id, '(blocking)' if blocking else '')
        if blocking:
            t.join()

    def wait_for_end(self):
        self._thread.join()
        with self._lock:
            consumers = list(self._consumers.values())
        for q, f, t in consumers:
            t.join()

    def _run(self):
        try:
            for item in self._generator:
                if self._stopped.isSet():
                    break
                with self._lock:
                    consumers = list(self._consumers.values())
                for q, _, _ in consumers:
                    try:
                        q.put(item, timeout=self.consumer_timeout)
                    except Queue.Full:
                        pass
        except:
            log.exception('data generator got an error')
        log.info('data generator finished')
        with self._lock:
            for q, _, _ in self._consumers.values():
                q.put(None)
            for _, _, t in self._consumers.values():
                t.join()

    def _consumer_run(self, queue, function):
        while not self._stopped.isSet():
            item = queue.get()
            if item is None:
                break
            function(*item)
        log.info('stopped consumer %r', function)


def dump_to_file(generator, filename, n_entries):
    log.info("start dumping to file %s from %r", filename, generator)
    with open(filename, 'w') as f:
        for _, item in zip(range(n_entries), generator):
            f.write(' '.join(map(str, item)) + '\n')
            yield item
    log.info("DONE dumping to file %s from %r", filename, generator)
    for item in generator:
        yield item
