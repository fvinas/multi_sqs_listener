# -*- coding: utf-8 -*-

"""Definition of QueueConfig & EventBus objects."""

# System
import logging
from queue import Queue
from operator import attrgetter


EVENT_BUSES_REGISTER = []


logger = logging.getLogger(__name__)


# pylint: disable=too-few-public-methods
class QueueConfig(object):
    """A class to store an individual SQS listener configuration."""

    def __init__(self, queue_name, bus, **kwargs):
        self.queue_name = queue_name
        self.bus = bus
        self.queue_type = kwargs['queue_type'] if 'queue_type' in kwargs else 'long-poll'
        self.region_name = kwargs['region_name'] if 'region_name' in kwargs else 'eu-west-1'

        # Only for short polling queues
        self.poll_interval = kwargs['poll_interval'] if 'poll_interval' in kwargs else 60

    def __repr__(self):
        return '(name={}, type={}, region_name={})'.format(
            self.queue_name, self.queue_type, self.region_name
        )


class EventBus(object):
    """A class to store a priority-aware event bus."""

    def __init__(self, name='default-bus', priority=1):
        self.name = name
        self.priority = priority

        # Actual event bus -- maxsize is set to 1 so that any attempt to put
        # a second message will block the thread until the current one is processed
        # (thus leaving messages for the other, ready to work SQS consumers)
        self._bus = Queue(maxsize=1)

    def __repr__(self):
        return '{}: {}'.format(self.name, self.priority)

    def get(self):
        """Getter for actual Queue.Queue object."""
        return self._bus

    @staticmethod
    def register_buses(buses):
        """Register event buses and sort them by priority."""
        for bus in buses:
            EVENT_BUSES_REGISTER.append(bus)

        # Sort buses by priority (highest first)
        EVENT_BUSES_REGISTER.sort(key=attrgetter('priority'), reverse=True)

        EventBus.display_buses()

    @staticmethod
    def display_buses():
        """Display current list of event buses."""
        logger.info('Registered event buses:')
        for bus in EVENT_BUSES_REGISTER:
            logger.info(' - {}'.format(bus))
