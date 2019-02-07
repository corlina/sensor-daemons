import argparse
import logging
import json
from .transport import CTSocketClient
from .event_trackers import testing, mpu6050


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--client-id', required=True)

    subparsers = parser.add_subparsers()

    mock_parser = subparsers.add_parser('testing', help='used for autotests')
    mock_parser.add_argument('program', nargs='*')
    mock_parser.set_defaults(
        get_tracker=lambda client, args: testing.TestingEventTracker(client, args.program),
        etype=testing.TestingEventTracker.EVENT_TYPE,
    )

    mpu_parser = subparsers.add_parser('mpu6050')
    mpu_parser.add_argument('server_port', nargs='?', type=int,
                            help="optional TCP server that streams both raw "
                                 "and filtered data to all clients. used for "
                                 "debugging")
    mpu_parser.add_argument('--accel-calibration',
                            help="optional JSON file that contains calibration"
                                 " data for accelerometer")
    mpu_parser.set_defaults(
        get_tracker=lambda client, args: load_mpu6050_eventtracker(
            client, args.server_port, args.accel_calibration
        ),
        etype=mpu6050.Mpu6050EventTracker.EVENT_TYPE,
    )

    def load_mpu6050_eventtracker(client, server_port, accel_calibration):
        if accel_calibration:
            with open(accel_calibration) as f:
                data = json.load(f)
            accel_offsets = data['x_offs'], data['y_offs'], data['z_offs']
        else:
            log.info('using development accelerometer calibration params')
            accel_offsets = 0.42, -1.11, 0.255
        return mpu6050.Mpu6050EventTracker(
            client,
            run_server_at_port=server_port,
            accel_offsets=accel_offsets,
        )

    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger(__name__)

    args = parser.parse_args()

    def on_config_enabled(etype, params):
        tracker.on_config_enabled(etype, params)

    def on_config_disabled(etype, params):
        tracker.on_config_enabled(etype, params)

    client = CTSocketClient(args.client_id, [args.etype],
                            on_config_enabled, on_config_disabled)

    tracker = args.get_tracker(client, args)
    client.start()
    try:
        tracker.run()
    except KeyboardInterrupt:
        pass
    finally:
        client.stop()
