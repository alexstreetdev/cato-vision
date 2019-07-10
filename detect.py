import argparse
import cv2
import datetime
import jsonpickle
import numpy as np
import os
import pika
import requests
import urllib
from commands import DetectFaceCmd
from models import ImageContent

_channel = None
_messages_recd = 0
_classifier = None
_queue_name = ''
_object_name = ''
_imageUrl = ''

def main(queuename, objectname, imageHostUrl):
    print('Running...')
    global _queue_name
    _queue_name = queuename
    global _object_name
    _object_name = objectname
    global _imageUrl
    _imageUrl = imageHostUrl
    print('prefetch count = 1')
    _channel.basic_qos(prefetch_count=1)
    print('listening to queue: ')
    print(_queue_name)
    _channel.basic_consume(queue=_queue_name, on_message_callback=_recv_message)
    _channel.start_consuming()

def _recv_message(channel, method, header, body):
    global _messages_recd

    _messages_recd += 1
    stop = False
    detectedFace = False
    decodedMessage = jsonpickle.decode(body.decode('UTF8'))
    cmd = hydrate_msg(decodedMessage)
    #print(cmd)
    # get image
    response = requests.get(cmd.ImageUrl)
    print(response.status_code)
    if response.status_code == 200:
        t = np.fromstring(response.content, np.uint8)
        cvimg = cv2.imdecode(t, -1)
        cropped = cvimg[cmd.Y:cmd.Y+cmd.Height, cmd.X:cmd.X+cmd.Width]
        gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
        faces = _classifier.detectMultiScale(gray, 1.3, 5)
        for (x,y,w,h) in faces:
            print('detected ' + _object_name)
            eventTime = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
            fd = ImageContent(cmd.ImageId, cmd.ImageUrl, cmd.X + x.item(), cmd.Y + y.item(), w.item(), h.item(), _object_name,"",'detect(' + _object_name +')')
            upload_content_data(fd)
            send_face_detected_msg(channel, fd)
    else:
        print(response.status_code)
        print(cmd.ImageUrl + ' not found')

    channel.basic_ack(method.delivery_tag) 

    #_channel.stop_consuming()


def hydrate_msg(decoded):
    ic = DetectFaceCmd(decoded['CommandId'])
    ic.ImageId=decoded['ImageId']
    ic.ImageUrl=decoded['ImageUrl']
    ic.X = decoded['X']
    ic.Y = decoded['Y']
    ic.Width = decoded['Width']
    ic.Height = decoded['Height']
    return ic

def send_face_detected_msg(channel, faceDetect):
    # Send face detected message
    try:
        jsonBody=jsonpickle.encode(faceDetect,unpicklable=False)
        routingKey='vision.evt.detected-' + _object_name
        props = pika.BasicProperties(app_id='cato-detect', type='ImageContent')
        channel.basic_publish(exchange='msg_gateway',
            properties=props,
            routing_key=routingKey, body=jsonBody)
        print(routingKey)
    except Exception as e:
        print(e)


def configure_rabbitmq(hostname, username, password):
    print('Connecting as user ' + username + ' @ ' + hostname)
    credentials=pika.PlainCredentials(username, password)
    parameters=pika.ConnectionParameters(hostname, 5672, '/', credentials)
    connection=pika.BlockingConnection(parameters)
    channel=connection.channel()
    return channel

# upload image content info to ImageStore
def upload_content_data(c):
    targetUrl = _imageUrl + '/api/imagedata/addcontent'
    jsonBody = jsonpickle.encode(c, unpicklable = False)
    jsonBody = jsonBody.replace('"', r'\"')
    jsonBody = '"' + jsonBody + '"'
    requests.post(targetUrl, data=jsonBody, headers={'Content-Type':'application/json'})

def initialise_classifiers(filename):
    classifierpath = "./cascades/" + filename
    global _classifier
    _classifier = cv2.CascadeClassifier(classifierpath)
    print("classifier loaded")


if __name__ == '__main__':
    parser = argparse.ArgumentParser('Detect object in image')
    parser.add_argument('-rh', action='store', dest='hostname', help='RabbitMQ hostname', required=True)
    parser.add_argument('-un', action='store', dest='username', default='guest', help='RabbitMQ username', required=False)
    parser.add_argument('-pw', action='store', dest='password', default='guest', help='RabbitMQ password', required=False)
    parser.add_argument('-qn', action='store', dest='queuename', default='vision_cmd_detect-face', help='RabbitMQ queue name', required=False)
    parser.add_argument('-hc', action='store', dest='haar', default='haarcascade_frontalface_default.xml', help='haar cascade filename', required=False)
    parser.add_argument('-nm', action='store', dest='objectname', default='face', help='detected object name', required=False)
    parser.add_argument('-is', action='store', dest='imagestore', default='127.0.0.1', help='Url of ImageStore', required=True)

    myargs = parser.parse_args()
    _channel=configure_rabbitmq(myargs.hostname, myargs.username, myargs.password)
    initialise_classifiers(myargs.haar)

    main(myargs.queuename, myargs.objectname, myargs.imagestore)
