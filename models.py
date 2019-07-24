class Image:
    def __init__(self, imageid, source, correlationid, sequencenumber, eventtime, url):
        self.imageid = imageid
        self.source = source
        self.correlationid = correlationid
        self.sequencenumber =  sequencenumber
        self.eventtime = eventtime
        self.imageurl = url

class ImageContent:
    def __init__(self, id, imageid, url, x, y, width, height, description, data, source):
        self.ContentId = id
        self.ImageId = imageid
        self.ImageUrl = url
        self.X = x
        self.Y = y
        self.Width = width
        self.Height = height
        self.ContentDescription = description
        self.ContentData = data
        self.Source = source
