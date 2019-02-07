# Build from sources

Run from repository root:
```python setup.py```

Result of build is put to file `ct_addons.zip`.

# Installation

Requirements:
* python 2.7
* `sudo apt-get install python-smbus`
* Corlina agent should be installed on the device

Installation:
* `pip install mpu6050-raspberrypi==1.1` - this can be installed in virtualenv as well
* download the daemon archive (`ct_addons.zip`)

# Usage
Run the daemon:

```sudo python ct_addons.zip --client-id <client-id> mpu6050```

Client ID currently can be arbitrary string.

When CT agent is running and online, daemon is running, you can rotate the device
and see Epochs generated on Corlina dashboard.
