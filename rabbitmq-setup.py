import pika
import sys


def configure_rabbitmq(hostname, username, password):
    credentials = pika.PlainCredentials(username, password)
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=hostname, credentials=credentials))
    channel = connection.channel()

    # Exchanges
    # -------------------------

    # Declares the entry exchange to be used by all producers to send messages.
    channel.exchange_declare(exchange='msg_gateway',
                             exchange_type='fanout',
                             durable=True,
                             auto_delete=False)

    # Routes messages to various queues. For internal use only
    channel.exchange_declare(exchange='msg_distributor',
                             exchange_type='topic',
                             internal=True,
                             durable=True,
                             auto_delete=False)

    #
    channel.exchange_declare(exchange='logging',
                             exchange_type='fanout',
                             internal=True,
                             durable=True,
                             auto_delete=False)

    # Exchange for all vision messages
    channel.exchange_declare(exchange='vision',
                             exchange_type='topic',
                             internal=True,
                             durable=True,
                             auto_delete=False)

    # Exchange for all speech messages
    channel.exchange_declare(exchange='speech',
                             exchange_type='topic',
                             internal=True,
                             durable=True,
                             auto_delete=False)

    # Exchange Bindings
    # -------------------------

    # Bind the entry exchange to the internal distributor exchange
    channel.exchange_bind(source='msg_gateway', destination='msg_distributor')

    # Route all video msgs to the video exchange
    channel.exchange_bind(source='msg_distributor', destination='vision', routing_key='vision.*.*')
    # Route all speech messages to the speech exchange
    channel.exchange_bind(source='msg_distributor', destination='speech', routing_key='speech.*.*')
    # Route all messages to logging
    channel.exchange_bind(source='msg_distributor', destination='logging', routing_key='#')

    # Queues
    # -------------------------
    five_days = 432000000
    # vision events
    channel.queue_declare(queue="vision_evt", durable=True, exclusive=False, auto_delete=False, arguments={'x-message-ttl' : five_days})
    twenty_four_hours = 86400000
    # vision commands
    channel.queue_declare(queue="vision_cmd_detect-face", durable=True, exclusive=False, auto_delete=False, arguments={'x-message-ttl' : twenty_four_hours})
    channel.queue_declare(queue="vision_cmd_detect-body", durable=True, exclusive=False, auto_delete=False, arguments={'x-message-ttl' : twenty_four_hours})
    channel.queue_declare(queue="vision_cmd_identify-face", durable=True, exclusive=False, auto_delete=False, arguments={'x-message-ttl' : twenty_four_hours})

    # Queue Bindings
    # -------------------------

    # Bind queues to exchanges and correct routing key. Allows for messages to be saved when no consumer is present
    channel.queue_bind(queue='vision_evt', exchange='vision', routing_key='vision.evt.*')
    channel.queue_bind(queue='vision_cmd_detect-face', exchange='vision', routing_key='vision.cmd.detect-face')
    channel.queue_bind(queue='vision_cmd_detect-body', exchange='vision', routing_key='vision.cmd.detect-body')
    channel.queue_bind(queue='vision_cmd_identify-face', exchange='vision', routing_key='vision.cmd.identify-face')


if __name__ == "__main__":
    configure_rabbitmq(sys.argv[1], sys.argv[2], sys.argv[3])
