import time
import logging
from ct_addons.transport import CTSocketClient


# VENDOR will be sent to SaaS as part of METADATA
VENDOR = 'vendor-1234'

# EVENT_TYPE valid values: MANUAL_TRIGGER, TEMPERATURE, MOVEMENT, ORIENTATION
EVENT_TYPE = 'MANUAL_TRIGGER'

# METADATA must be in JSON format (e.g. Python dict)
# structure of METADATA depends on EVENT_TYPE
METADATA = {'text': 'something I want to say'}


# setup code:
logging.basicConfig(level=logging.INFO)
client = CTSocketClient(
    client_id=VENDOR,
    event_types=[],
    on_config_enabled=None,
    on_config_disabled=None,
)
client.start()

# sending data
client.send_event(
    event_type=EVENT_TYPE,
    data=METADATA,
)
# sending is asynchronous, so wait a bit
time.sleep(3)

# close the connection
client.stop()


# to find out the eventstamp use the following command:
# sudo journalctl -u ct-agent -o cat -e | grep S017

# Example of cURL command that gets eventstamps
# curl -X GET "https://management-staging.corlina.com/api/v1/epochs/4083ae02d5c50de4f1d447025c395de8" -H "accept: */*" -H "Authorization: 1edb52981adc3b22f086c3c87bf86bda5b30cb0299ea14e1c21709322d7e5758"
# fill eventstamp and auth token
