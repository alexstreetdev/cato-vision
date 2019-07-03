import argparse
import cv2
import urllib
import numpy as np
import time
import imutils
import os
import datetime
import requests
import getopt
import sys
import pika
import jsonpickle
import uuid
from models import ImageContent


class Image:
    def __init__(self, imageid, source, correlationid, sequencenumber, eventtime, url):
        self.imageid = imageid
        self.source = source
        self.correlationid = correlationid
        self.sequencenumber = sequencenumber
        self.eventtime = eventtime
        self.imageurl = url

def main(myargs):
    inputUrl = myargs.inputurl
    outputUrl = myargs.outputurl
    cameraName = myargs.cameraname
    threshold = myargs.threshold
    messagingEnabled = False
    if myargs.messaging == 'Y':
        messagingEnabled = True
    messageServer = myargs.messageServer
    messageQueue = myargs.messageQueue
    #
    avgImg = None
    connection = None
    isInProcess = False # true if in sequence mode
    sequencenumber = 1
    tailFrameCount = 0  # count of extra frames appended
    tailFrameLimit = 5  # max number of tail frames to app

    print ("-i: " + inputUrl)
    print ("-o: " + outputUrl)
    print ("name: " + cameraName)
    print ("thresh: " + str(threshold))
    print ("messagingEnabled: " + str(messagingEnabled))
    if messagingEnabled:
        print ("messageServer: " + messageServer)
        print ("messageQueue: " + messageQueue)

    # rabbitmq
    if messagingEnabled:
        credentials = pika.PlainCredentials('cato', 'cato')
        parameters = pika.ConnectionParameters(messageServer, 5672, '/', credentials)
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        statuskey = 'vision.' + cameraName + '.status-online'
        channel.basic_publish(exchange='msg_gateway', routing_key=statuskey, body='Camera [' + cameraName + '] starting')

    # loop camera stream
    while True:
        frame = getFrame(inputUrl)
        if frame is not None:

            contentsarray = []
            # process frame using opencv
            gray = prepareFrame(frame)

            if avgImg is None:
                avgImg = gray.copy().astype("float")
                continue

            # get contours
            cnts = getContours(gray, avgImg)

            # create message
            # if not in process create a new correlation id
            if not isInProcess:
                correlationId = str(uuid.uuid4())
            eventTime = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
            imageid = correlationId + '_' + str(sequencenumber) + '.jpg'
            imageUrl = outputUrl + '/api/image/' + imageid
            m = Image(imageid, cameraName, correlationId, sequencenumber, eventTime, imageUrl)

            detection = False
            for c in cnts:
                diff = cv2.contourArea(c)
                if diff >= threshold:
                    detection = True
                    (x,y,w,h) = cv2.boundingRect(c)
                    contentsarray.append(ImageContent(imageid,imageUrl,x,y,w,h,'movement',"",'camera-movement'))
                else:
                    print("diff: " + str(diff) + " / " + str(threshold))

            isInProcess = calculateInProcess(detection, sequencenumber, tailFrameCount, tailFrameLimit)

            if isInProcess:
                try:
                    # upload image
                    uploadImage(frame, imageid, outputUrl)
                    uploadImageData(m, outputUrl)
                    for c in contentsarray:
                        uploadImageContents(c, outputUrl)
                        if messagingEnabled:
                            sendMovementMessage(channel,c)
                except requests.exceptions.RequestException as e:
                    # catches all, todo handle error types differently send msg
                    print(e)
                #if messagingEnabled:
                #    for c in contentsarray
                #    sendMovementMessage(channel, m)
                #
                sequencenumber +=1
                if not detection:
                    tailFrameCount += 1
            else:
                sequencenumber = 1

def prepareFrame(frame):
    # process frame using opencv
    img_array = np.fromstring(frame, dtype=np.uint8)
    image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    colour= cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(colour, (21,21), 0)
    return gray

def getContours(gray, avgImg):
    cv2.accumulateWeighted(gray, avgImg, 0.5)
    frameDelta = cv2.absdiff(gray, cv2.convertScaleAbs(avgImg))
    thresh = cv2.threshold(frameDelta, 5, 255, cv2.THRESH_BINARY)[1]
    thresh = cv2.dilate(thresh, None, iterations=2)
    cnts = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = cnts[0] if imutils.is_cv2() else cnts[1]
    return cnts

def uploadImage(image, imageid, host):
    targetUrl = host + '/api/image/' + imageid
    requests.post(targetUrl, data=image, headers={'Content-Type':'image/jpeg'})

def uploadImageData(m, host):
    targetUrl = host + '/api/imagedata/addimage'
    #jsonBody = jsonpickle.encode(m)
    jsonBody = objectToJson(m)
    resp = requests.post(targetUrl, data=jsonBody, headers={'Content-Type':'application/json'})
    print("image data sent: " + str(resp))

def uploadImageContents(contents, host):
    targetUrl = host + '/api/imagedata/addcontent'
    #jsonBody = jsonpickle.encode(c)
    jsonBody = objectToJson(contents)
    resp = requests.post(targetUrl, data=jsonBody, headers={'Content-Type':'application/json'})
    print("image contents sent: " + str(resp))

def sendMovementMessage(channel, m):
    jsonBody = jsonpickle.encode(m,unpicklable=False)
    messagekey = 'vision.evt.detected-movement'
    channel.basic_publish(exchange='msg_gateway',
                            routing_key=messagekey,
                            properties=pika.BasicProperties(
                                app_id='camera-movement', type='ImageContent'),
                            body=jsonBody)

def objectToJson(cls):
    # must be doing something wrong to make this required, but...
    jsonBody = jsonpickle.encode(cls, unpicklable=False)
    jsonBody = jsonBody.replace('"', r'\"')
    jsonBody = '"' + jsonBody + '"'
    return jsonBody

def getFrame(inputUrl):
    response = requests.get(inputUrl, stream=True)
    for chunk in response.iter_content(chunk_size=250000, decode_unicode=False):
        startIx = chunk.find(b'\xff\xd8')
        if startIx != -1:
            endIx = chunk.find(b'\xff\xd9', startIx)
            if endIx != -1:
                frame = chunk[startIx:endIx+2]
                return frame
    return None

def calculateInProcess(detection, sequencenumber, tailFrameCount, tailFrameLimit):
    if detection:
        # if detection then we are in process
        return True
    if sequencenumber==1:
        # detection false and sequence 1 then ignore frame
        return False
    if tailFrameCount < tailFrameLimit:
        return True
    return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser('Detect movement in jpg stream')
    parser.add_argument('-i', action='store', dest='inputurl', help='jpeg stream used for input', required=True)
    parser.add_argument('-o', action='store', dest='outputurl', help='url for imagestore', required=True)
    parser.add_argument('-n', action='store', dest='cameraname', default='camera', help='name for source camera', required=False)
    parser.add_argument('-t', action='store', dest='threshold', type=float, default=5000, help='threshold value for movement detection', required=False)
    parser.add_argument('-r', action='store', dest='messaging', default='N', help='Enable RabbitMq messaging Y/N', required=False)
    parser.add_argument('-s', action='store', dest='messageServer', default='', help='RabbitMq server name', required=False)
    parser.add_argument('-q', action='store', dest='messageQueue', default='', help='RabbitMq queue name', required=False)
    myargs = parser.parse_args()
    main(myargs)
