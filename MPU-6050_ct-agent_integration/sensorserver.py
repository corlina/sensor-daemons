import argparse
import time
import socket
import struct
import threading
import Queue
from mpu6050 import mpu6050


def listenserver(port, queue_list, lock, stopped):
    serversock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serversock.bind(('0.0.0.0', port))
    serversock.listen(3)
    while True:
        sock, addr = serversock.accept()
        queue = Queue.Queue(maxsize=1000)
        with lock:
            queue_list.append(queue)
        thr = threading.Thread(target=clientstreamer, args=(sock, queue, stopped))
        thr.setDaemon(True)
        thr.start()


def clientstreamer(sock, queue, stopped):
    while not stopped.isSet():
        data = queue.get()
        packet = struct.pack('ffffff', *data)
        sock.send(packet)


def datasource(queue_list, lock, dt, stopped):
    sensor = mpu6050(0x68)
    while not stopped.isSet():
        start = time.time()
        accel = sensor.get_accel_data()
        gyro = sensor.get_gyro_data()
        item = accel['x'], accel['y'], accel['z'], gyro['x'], gyro['y'], gyro['z']
        with lock:
            queues = queue_list[:]
        for q in queues:
            try:
                q.put(item, timeout=dt * 0.75)
            except Queue.Full:
                pass
        duration = time.time() - start
        if dt > duration:
            time.sleep(dt - duration)
    with lock:
        queues = queue_list[:]
    for q in queues:
        q.put(None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dt', type=float, default=0.01)
    parser.add_argument('--port', type=int, default=3333)
    opts = parser.parse_args()

    queue_list = []
    lock = threading.Lock()
    stopped = threading.Event()

    source_thread = threading.Thread(
        target=datasource,
        args=(queue_list, lock, opts.dt, stopped),
    )
    source_thread.start()

    try:
        listenserver(opts.port, queue_list, lock, stopped)
    except KeyboardInterrupt:
        pass
    finally:
        stopped.set()
        source_thread.join()


if __name__ == '__main__':
    main()

