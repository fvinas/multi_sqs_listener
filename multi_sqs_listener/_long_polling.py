# -*- coding: utf-8 -*-

"""Listener for long polling SQS queues."""

# System
import logging
from threading import Thread

# Third party
import boto3


logger = logging.getLogger(__name__)


class _LongPollSQSListener(Thread):
    """A SQS listener designed to work alone in a separate thread.
    This listener is in long polling mode, i.e. allows us to be immediately triggered
    in case of an incoming message.

    https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-long-polling.html
    """

    # pylint: disable=too-many-arguments
    def __init__(self, thread_id, queue_name, outbound_bus, run_event,
                 handler_available_event, **kwargs):
        Thread.__init__(self, name=queue_name)
        self.thread_id = thread_id
        self._region_name = kwargs['region_name'] if 'region_name' in kwargs else 'eu-west-1'
        self._queue_acct_id = kwargs.get('queue_acct_id')
        self._outbound_bus = outbound_bus
        self._queue_name = queue_name
        self._handler_available_event = handler_available_event
        sqs = boto3.resource('sqs', region_name=self._region_name)
        if self._queue_acct_id is not None:
            self._queue = sqs.get_queue_by_name(QueueName=self._queue_name, QueueOwnerAWSAccountId=self._queue_acct_id)
        else:
            self._queue = sqs.get_queue_by_name(QueueName=self._queue_name)


        self._run_event = run_event

        logger.debug('Starting up thread {} and long-polling inbound queue {}'.format(
            self.thread_id, self._queue_name
        ))

    def run(self):
        """Start event of the listener thread."""
        logger.info('Long polling queue {}'.format(self._queue_name))
        while True and self._run_event.is_set():
            # TODO: make MaxNumberOfMessages customizable?
            self._handler_available_event.wait()
            self._outbound_bus.join()
            messages = self._queue.receive_messages(MaxNumberOfMessages=1, WaitTimeSeconds=5)
            if messages:
                self._outbound_bus.join()
                self._outbound_bus.put((self._queue_name, messages[0]))

    def stop(self):
        """Stop event of the listener thread."""
        logger.debug('Thread {} stopped'.format(self.thread_id))
