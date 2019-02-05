from __future__ import print_function
import argparse
import socket
import struct
import time
import threading
from ct_addons.event_trackers.mpu6050.motion_tracker import MotionTracker
from ct_addons.event_trackers.mpu6050.data_source import motiontracker_data_generator


def stream_from_socket(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))

    packet_len = struct.calcsize('fffffffff')

    while True:
        packet = sock.recv(packet_len)
        yield struct.unpack('fffffffff', packet)


def stream_from_file(filename, dt):
    import numpy as np
    data = np.loadtxt(filename)[:, 1:]
    for item in data:
        yield tuple(item)
        if dt > 0:
            time.sleep(dt)


def main_terminal():
    parser = argparse.ArgumentParser()
    parser.add_argument('host')
    parser.add_argument('port', type=int)
    opts = parser.parse_args()

    streamer = stream_from_socket(opts.host, opts.port)
    for item in streamer:
        fmt_item = ' '.join('{:7.2f}'.format(x) for x in item)
        print(fmt_item)


def main_gui():
    import matplotlib
    matplotlib.use('TkAgg')
    import matplotlib.animation as animation
    from matplotlib import pyplot as plt

    parser = argparse.ArgumentParser()
    parser.add_argument('host')
    parser.add_argument('port', type=int)
    opts = parser.parse_args()

    dt = 0.011
    bufsize = 2000

    streamer = stream_from_file('data.txt', -1)
    # streamer = stream_from_socket(opts.host, opts.port)
    streamer = motiontracker_data_generator(
        streamer,
        MotionTracker(0.5, dt),
        calibrate_n=300,
    )

    # tracker = MotionTracker(0.5, dt)

    # print('Calibrating...')
    # tracker.start_calibration()
    # for _ in range(200):
    #     item = next(streamer)
    #     tracker.add_data(*item)
    # tracker.finish_calibration()
    # print('Calibration done')

    lock = threading.Lock()
    buffers = [[] for _ in range(9)]
    labels = 'accel_X accel_Y accel_Z ' \
             'gyro_X gyro_Y gyro_Z ' \
             'Angle_X Angle_Y Angle_Z'.split()
    lines = {}
    fig = plt.gcf()

    def data_update():
        for item in streamer:
            with lock:
                for i in range(9):
                    buf = buffers[i]
                    buf.append(item[i])
                    if len(buf) > bufsize:
                        buf.pop(0)
    update_thread = threading.Thread(target=data_update)
    update_thread.daemon = True
    update_thread.start()

    init_params = [
        (311, [0, 1, 2], (-30, 30)),
        (312, [3, 4, 5], (-120, 120)),
        (313, [6, 7, 8], (-3000, 3000)),
    ]

    for subidx, indices, (ymin, ymax) in init_params:
        ax = plt.subplot(subidx)
        ax.set_xlim(0, bufsize+100)
        ax.set_ylim(ymin, ymax)
        for i in indices:
            [line] = plt.plot([], label=labels[i].replace('_', ' '))
            lines[i] = line
        leg = plt.legend(loc='lower left', shadow=True, fancybox=True)
        leg.get_frame().set_alpha(0.5)

    def init_func():
        for buf in buffers:
            del buf[:]
        fig.canvas.draw()
        return tuple(lines.values())

    def dummy_source():
        while update_thread.isAlive():
            yield buffers

    def update_func(_):
        _buffers = buffers
        for i in range(9):
            buf = _buffers[i]
            line = lines[i]
            with lock:
                buf = buf[:]
                line.set_data(
                    range(bufsize-len(buf), bufsize),
                    buf
                )
        return tuple(lines.values())

    ani = animation.FuncAnimation(fig, update_func, dummy_source,
                                  repeat=False, init_func=init_func)
    # update_thread.join()
    # ani.save('filter-performance.avi', extra_args=['-vcodec', 'libxvid'])
    plt.show()

if __name__ == '__main__':
    # main_terminal()
    main_gui()
