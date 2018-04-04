# -*- coding: utf-8 -*-

# System
import time
import logging
from threading import Event
from Queue import PriorityQueue, Empty
from abc import ABCMeta, abstractmethod

# Project
from .long_polling import _LongPollSQSListener
from .short_polling import _ShortPollSQSListener


logging.getLogger(__name__).addHandler(logging.NullHandler())


class SQSListenerConfig(object):
    """A class to store an individual SQS listener configuration."""

    def __init__(self, queue_name, **kwargs):
        self.queue_name = queue_name
        self.priority_number = kwargs['priority_number'] if 'priority_number' in kwargs else 1
        self.bus_name = kwargs['bus_name'] if 'bus_name' in kwargs else 'default-bus'
        self.queue_type = kwargs['queue_type'] if 'queue_type' in kwargs else 'long-poll'
        self.queue_url = ''

    def __repr__(self):
        return '(name={}, url={})'.format(self.queue_name, self.queue_url)


class MultiSQSListener(object):
    """Main class: instanciates the listeners."""

    __metaclass__ = ABCMeta

    def __init__(self, queues_configuration, logger=None, **kwargs):
        self._logger = logger or logging.getLogger(__name__)
        self._poll_interval = kwargs['poll_interval'] if 'poll_interval' in kwargs else 60
        self._region_name = kwargs['region_name'] if 'region_name' in kwargs else 'eu-west-1'
        self._queues_configuration = queues_configuration
        self.outbound_buses = dict()

    def _start_listeners(self):
        threads = []
        run_event = Event()
        run_event.set()
        handler_available_event = Event()
        handler_available_event.set()

        for i, queue in enumerate(self._queues_configuration):
            if queue.bus_name not in self.outbound_buses:
                self.outbound_buses[queue.bus_name] = PriorityQueue(maxsize=1)
            self._logger.debug('Launching listener for {} in thread {}, outbound bus {}, type {}'.format(queue.queue_name, i, queue.bus_name, queue.queue_type))

            if queue.queue_type == 'long-poll':
                listener_thread = _LongPollSQSListener(
                    i,
                    queue.queue_name,
                    self.outbound_buses[queue.bus_name],
                    queue.priority_number,
                    run_event,
                    handler_available_event,
                    region_name=self._region_name
                )
            else:
                listener_thread = _ShortPollSQSListener(
                    i,
                    queue.queue_name,
                    self.outbound_buses[queue.bus_name],
                    run_event,
                    handler_available_event,
                    self._poll_interval,
                    region_name=self._region_name
                )
            listener_thread.start()
            threads.append(listener_thread)

        # TODO: put mechanism in place so that the threads no longer add things to the queue
        # while the handler is dealing with a message
        try:
            while True:
                for bus_name, bus in self.outbound_buses.iteritems():
                    # bus_size = bus.qsize()
                    try:
                        message = bus.get(block=False)
                        handler_available_event.clear()
                        try:
                            self.handle_message(message[1], bus_name, message[0], message[2])
                            # If handle message worked, then delete the message from SQS
                            message[2].delete()
                        except Exception:
                            # TODO: add another behaviour?
                            self._logger.error('Exception: unable to handle message', exc_info=True)
                        finally:
                            bus.task_done()
                        handler_available_event.set()
                    except Empty:
                        pass
                time.sleep(0.1)
        except KeyboardInterrupt:
            # Queues threads are also asked to gracefully close
            run_event.clear()
            for thread in threads:
                thread.join()

    def listen(self):
        self._logger.info('Registering listeners on all queues')
        self._start_listeners()

    @abstractmethod
    def handle_message(self, queue_name, bus_name, priority, sqs_message):
        pass