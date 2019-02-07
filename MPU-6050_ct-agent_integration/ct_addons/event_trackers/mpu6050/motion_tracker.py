import logging
from math import atan2, sqrt, pi, sin, cos, acos


log = logging.getLogger(__name__)


class MotionTracker(object):
    def __init__(self, time_term, read_interval, bufsize=20, accel_offsets=(0, 0, 0)):
        # TODO document this
        self.rot_decay = float(time_term) / (time_term + read_interval)
        self.bufsize = bufsize
        self.dt = read_interval
        self.world_pos = _ZERO
        self.basis_x = _X_AXIS
        self.basis_y = _Y_AXIS

        self._gyro_moment = _ZERO
        self._gyro_integrated = _ZERO

        self._calibration_state = False
        self._init_gravity = _ZERO
        self._gravity = _ZERO
        self._init_gravity_value = 0
        self._gyro_offs = _ZERO
        self._calibration_sums = None
        self._calibration_n = 0

        self._acc_offs = accel_offsets

    def start_calibration(self):
        self._calibration_state = True
        self._calibration_sums = [0, 0, 0, 0, 0, 0]
        self._calibration_n = 0

    def finish_calibration(self):
        self._calibration_state = False
        calib_means = [x / self._calibration_n for x in self._calibration_sums]
        self._gravity = calib_means[:3]
        self._gyro_offs = calib_means[3:]

        self._gravity = _sub(self._gravity, self._acc_offs)
        self._init_gravity = self._gravity
        self._init_gravity_value = dist(*self._gravity)

        self._init_basis_x = _X_AXIS
        self._init_basis_y = _Y_AXIS
        self._init_basis_z = _cross(self._init_basis_x, self._init_basis_y)

        self._gyro_moment = _ZERO
        self._gyro_integrated = _ZERO

        self.world_pos = _ZERO
        self.velocity = _ZERO
        self.basis_x = self._init_basis_x
        self.basis_y = self._init_basis_y
        self.basis_z = self._init_basis_z

        log.info('gyro offsets = ({})'.format(_fmt(self._gyro_offs)))
        log.info('accelerometer offsets = ({})'.format(_fmt(self._acc_offs)))
        log.info('gravity value = {:.3f}'.format(dist(*self._gravity)))

    def add_data(self, acc_x, acc_y, acc_z, gyro_x, gyro_y, gyro_z):
        if self._calibration_state:
            data_tuple = acc_x, acc_y, acc_z, gyro_x, gyro_y, gyro_z
            for i in range(len(data_tuple)):
                self._calibration_sums[i] += data_tuple[i]
            self._calibration_n += 1
        else:
            gyro = _sub((gyro_x, gyro_y, gyro_z), self._gyro_offs)
            acc = _sub((acc_x, acc_y, acc_z), self._acc_offs)

            dt = self.dt
            self._gyro_moment = _mul(gyro, dt * _DEG2RAD)
            self._gyro_integrated = _add(self._gyro_integrated, self._gyro_moment)

            hpf = self.rot_decay
            lpf = 1 - hpf

            angle, axis = _gyro_to_angleaxis(self._gyro_moment)
            newbasis_g_x = _rotate(self.basis_x, axis, angle)
            newbasis_g_y = _rotate(self.basis_y, axis, angle)
            gravity_g = _rotate(self._gravity, axis, angle)
            gravity_a = _mul(acc, self._init_gravity_value / dist(*acc))

            gravity_f = _add(_mul(gravity_a, lpf), _mul(gravity_g, hpf))
            fix_angle = _angle_between(gravity_g, gravity_f)
            fix_axis = _cross(gravity_f, gravity_g)

            self._gravity = gravity_a

            self.basis_x = _rotate(newbasis_g_x, fix_axis, fix_angle)
            self.basis_y = _rotate(newbasis_g_y, fix_axis, fix_angle)

            self.basis_z = _cross(self.basis_x, self.basis_y)

            acceleration = _sub(acc, gravity_f)
            new_velocity = _add(self.velocity, _mul(acceleration, dt))
            self.world_pos = _add(
                self.world_pos,
                _mul(self.velocity, dt / 2),
                _mul(new_velocity, dt / 2),
            )
            self.velocity = _mul(new_velocity, 0.99)

    @property
    def angles(self):
        return (
            _angle_between(self.basis_x, self._init_basis_x) * _RAD2DEG,
            _angle_between(self.basis_y, self._init_basis_y) * _RAD2DEG,
            _angle_between(self.basis_z, self._init_basis_z) * _RAD2DEG,
        )

    @property
    def coordinates(self):
        return self.world_pos


def dist(*args):
    return sqrt(sum(x*x for x in args))


def get_y_angle(vector):
    x, y, z = vector
    return -atan2(x, dist(y, z))


def get_x_angle(vector):
    x, y, z = vector
    return atan2(y, dist(x, z))


def get_z_angle(vector):
    x, y, z = vector
    return -atan2(z, dist(x, y))


def _add(*vectors):
    return tuple(sum(xs) for xs in zip(*vectors))


def _sub(v1, v2):
    return tuple(x1 - x2 for x1, x2 in zip(v1, v2))


def _mul(v, k):
    return tuple(k * x for x in v)


def _dot(v1, v2):
    return sum(x1 * x2 for x1, x2 in zip(v1, v2))


def _cross(v1, v2):
    x1, y1, z1 = v1
    x2, y2, z2 = v2
    return y1*z2-z1*y2, z1*x2-x1*z2, x1*y2-y1*x2


def _norm(vector, with_d=False):
    d = dist(*vector)
    if d > 0.00001:
        vector = _mul(vector, 1/d)
    if with_d:
        return vector, d
    else:
        return vector


def _rotate(vector, axis, angle):
    axis, d = _norm(axis, with_d=True)
    if d < 0.00001:
        return vector

    rotbasis_y = -axis[1], axis[0], 0
    if dist(*rotbasis_y) < 0.2:
        rotbasis_y = 0, axis[2], -axis[1]
    rotbasis_y = _norm(rotbasis_y)
    rotbasis_z = _cross(axis, rotbasis_y)

    b_x = _dot(vector, axis)
    b_y = _dot(vector, rotbasis_y)
    b_z = _dot(vector, rotbasis_z)

    cos_a = cos(angle)
    sin_a = sin(angle)

    a_y = cos_a * b_y - sin_a * b_z
    a_z = cos_a * b_z + sin_a * b_y

    return _add(_mul(axis, b_x), _mul(rotbasis_y, a_y), _mul(rotbasis_z, a_z))


def _gyro_to_angleaxis(gyro):
    angle = dist(*gyro)
    if angle < 0.00001:
        return 0, _X_AXIS
    axis = _mul(gyro, -1/angle)
    return angle, axis


def _angle_between(v1, v2):
    return acos(_dot(v1, v2) / (dist(*v1) * dist(*v2)))


def _fmt(vector):
    return ' '.join(['{:.3f}'] * len(vector)).format(*vector)

_ZERO = 0.0, 0.0, 0.0
_X_AXIS = 1.0, 0.0, 0.0
_Y_AXIS = 0.0, 1.0, 0.0
_Z_AXIS = 0.0, 0.0, 1.0

_DEG2RAD = pi / 180.0
_RAD2DEG = 180.0 / pi
