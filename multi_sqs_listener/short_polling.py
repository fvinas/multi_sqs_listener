# -*- coding: utf-8 -*-

# System
import time
import logging
from threading import Thread

# Third party
import boto3


class _ShortPollSQSListener(Thread):
    """A SQS listener designed to work alone in a separate thread.
    This listener is in short polling mode, i.e. based on a regular, periodic polling.

    https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-long-polling.html
    """

    def __init__(self, thread_id, queue_name, outbound_bus, run_event, handler_available_event, poll_interval=10, logger=None, **kwargs):
        Thread.__init__(self, name=queue_name)
        self._logger = logger or logging.getLogger(__name__)
        self.thread_id = thread_id
        self._region_name = kwargs['region_name'] if 'region_name' in kwargs else 'eu-west-1'
        self._outbound_bus = outbound_bus
        self._queue_name = queue_name
        self._poll_interval = poll_interval
        self._handler_available_event = handler_available_event
        sqs = boto3.resource('sqs', region_name=self._region_name)
        self._queue = sqs.get_queue_by_name(QueueName=self._queue_name)
        self._run_event = run_event

        self._logger.debug('Starting up thread {} and short-polling inbound queue {}'.format(
            self.thread_id, self._queue_name
        ))

    def run(self):
        self._logger.debug('Short polling queue {}'.format(self._queue_name))

        while True and self._run_event.is_set():
            self._handler_available_event.wait()
            self._outbound_bus.join()
            messages = self._queue.receive_messages(MaxNumberOfMessages=1)
            if len(messages) > 0:
                self._outbound_bus.join()
                self._outbound_bus.put((1, self._queue_name, messages[0]))
            else:
                time.sleep(self._poll_interval)

    def stop(self):
        self._logger.debug('Thread {} stopped'.format(self.thread_id))
