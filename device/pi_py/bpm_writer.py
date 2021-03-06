#!/usr/bin/python
import argparse
import datetime
import os
import random
import ssl
import time
import json
import datetime

import jwt
import paho.mqtt.client as mqtt

import serial

fake = False
# [START iot_mqtt_jwt]
def create_jwt(project_id, private_key_file, algorithm):

    token = {
            # The time that the token was issued at
            'iat': datetime.datetime.utcnow(),
            # The time the token expires.
            'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=60),
            # The audience field should always be set to the GCP project id.
            'aud': project_id
    }

    # Read the private key file.
    with open(private_key_file, 'r') as f:
        private_key = f.read()

    print('Creating JWT using {} from private key file {}'.format(
            algorithm, private_key_file))

    return jwt.encode(token, private_key, algorithm=algorithm)
# [END iot_mqtt_jwt]


# [START iot_mqtt_config]
def error_str(rc):
    """Convert a Paho error to a human readable string."""
    return '{}: {}'.format(rc, mqtt.error_string(rc))


def on_connect(unused_client, unused_userdata, unused_flags, rc):
    """Callback for when a device connects."""
    print('on_connect', mqtt.connack_string(rc))

    # After a successful connect, reset backoff time and stop backing off.
    global connected
    connected = True



def on_disconnect(unused_client, unused_userdata, rc):
    """Paho callback for when a device disconnects."""
    print('on_disconnect', error_str(rc))


def on_publish(unused_client, unused_userdata, unused_mid):
    """Paho callback when a message is sent to the broker."""
    print('on_publish')


def on_message(unused_client, unused_userdata, message):
    """Callback when the device receives a message on a subscription."""
    global hr_limit
    payload = str(message.payload)
    print('Received message \'{}\' on topic \'{}\' with Qos {}'.format(
            payload, message.topic, str(message.qos)))
    try:
        hr_limit = int(120)
    except ValueError:
        print('no valid config')


def get_client(
        project_id, cloud_region, registry_id, device_id, private_key_file,
        algorithm, ca_certs, mqtt_bridge_hostname, mqtt_bridge_port):
    """Create our MQTT client. The client_id is a unique string that identifies
    this device. For Google Cloud IoT Core, it must be in the format below."""
    client = mqtt.Client(
            client_id=('projects/{}/locations/{}/registries/{}/devices/{}'
                       .format(
                               project_id,
                               cloud_region,
                               registry_id,
                               device_id)))

    # With Google Cloud IoT Core, the username field is ignored, and the
    # password field is used to transmit a JWT to authorize the device.
    client.username_pw_set(
            username='unused',
            password=create_jwt(
                    project_id, private_key_file, algorithm))

    # Enable SSL/TLS support.
    client.tls_set(ca_certs=ca_certs, tls_version=ssl.PROTOCOL_TLSv1_2)

    # Register message callbacks. 
    client.on_connect = on_connect
    #client.on_publish = on_publish
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    # Connect to the Google MQTT bridge.
    
    client.connect(mqtt_bridge_hostname, mqtt_bridge_port)
    

    
    
    return client

def toggle_led(status):
    if not fake:
        global led_status

        if led_status is False and status is True:
            GPIO.output(18,GPIO.HIGH)
            led_status = True
        if led_status is True and status is False:
            GPIO.output(18,GPIO.LOW)
            led_status = False
    else: 
        'hr limit exceeded, slow down!'

###CONFIG###

# device specific config
with open('../../device/device_config.json') as f:
    dconfig = json.loads(str(f.read()))

device_id = dconfig['DEVICE']['DEVICE_ID']
private_key_file = dconfig['DEVICE']['PRIVATE_KEY']
serial_port = dconfig['DEVICE']['SERIAL_PORT']
sys_type = dconfig['DEVICE']['TYPE']
ca_certs = dconfig['DEVICE']['CA_CERTS']


#global config
with open('startup_utils/global_config.json') as f:
    gconfig = json.loads(str(f.read()))

project_id = gconfig['GCP']['PROJECT_ID']
cloud_region = gconfig['GCP']['CLOUD_REGION']
registry_id = gconfig['GCP']['REGISTRY_ID']
mqtt_bridge_hostname = gconfig['GCP']['MQTT_BRIDGE_HOSTNAME']
mqtt_bridge_port = gconfig['GCP']['MQTT_BRIDGE_PORT']
algorithm = gconfig['GCP']['ALGORITHM']





# This is the topic that the device will receive configuration updates on.
mqtt_config_topic = '/devices/{}/config'.format(device_id)


#uart config and vars
if not fake:
    ser = serial.Serial()
    ser.baudrate = 115200
    ser.port = serial_port
    ser.open()

    #led setup
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(18,GPIO.OUT)
    GPIO.output(18,GPIO.LOW)

    global led_status
    led_status = False



#test

def main():
    global minimum_backoff_time
    global connected
    connected = False
    global hr_limit
    hr_limit = 1000

    #args = parse_command_line_args()

    mqtt_topic = '/devices/{}/events'.format(device_id)

    jwt_iat = datetime.datetime.utcnow()
    jwt_exp_mins = 120
    client = get_client(
        project_id, cloud_region, registry_id, device_id,
        private_key_file, algorithm, ca_certs,
        mqtt_bridge_hostname, mqtt_bridge_port)

    # Process network events on new thread
    client.loop_start()

    # Subscribe to the config topic.
    time.sleep(1)
    client.subscribe(mqtt_config_topic, qos=0)

    while True:
        if not fake:
     
            ser.reset_input_buffer()
            time.sleep(0.1)
            sline = ser.readline().decode("utf-8")
            if sline and sline != '':
                print('in white')
                ser_vals = sline.split(',')
                bpm = int(ser_vals[1])
                temp = float(ser_vals[0])
                #print('bpm: ' + str(bpm))
                #print('temp: ' + str(temp))
        else:
            bpm = random.randint(50,100)
            temp = random.randint(50,100)

        read_time = int(datetime.datetime.now().strftime("%s")) * 1000

        if bpm >= hr_limit:
            toggle_led(True)
        else:
            toggle_led(False)
        print(connected)

        if connected:
            payload = json.dumps({'bpm':bpm, 'temperature':temp, 'timestamp':read_time})
            print('publishing ' + str(payload) + ' on ' + mqtt_topic)
            client.publish(mqtt_topic, payload, qos=0)


        # Send events every second. limit to 1 per second due to fs limits
        time.sleep(1)



if __name__ == '__main__':
    main()