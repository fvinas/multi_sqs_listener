# -*- coding: utf-8 -*-

"""Main module of multi_sqs_listener."""

# System
import time
import logging
from threading import Event
from Queue import Empty
from abc import ABCMeta, abstractmethod

# Project
from .config import EVENT_BUSES_REGISTER
from ._long_polling import _LongPollSQSListener
from ._short_polling import _ShortPollSQSListener


logger = logging.getLogger(__name__)


class MultiSQSListener(object):
    """Main class: instanciates the listeners and runs the main event loop.
    This abstract class must implement handle_message method to be instanciated.
    """

    __metaclass__ = ABCMeta

    def __init__(self, queues_configuration):
        self._queues_configuration = queues_configuration

    def _start_listeners(self):
        threads = []
        run_event = Event()
        run_event.set()
        handler_available_event = Event()
        handler_available_event.set()

        for index, queue in enumerate(self._queues_configuration):
            logger.debug('Launching listener for {} in thread {}, outbound bus {}, type {}'.format(
                queue.queue_name, index, queue.bus.name, queue.queue_type
            ))

            if queue.queue_type == 'long-poll':
                listener_thread = _LongPollSQSListener(
                    index,
                    queue.queue_name,
                    queue.bus.get(),
                    run_event,
                    handler_available_event,
                    region_name=queue.region_name
                )
            else:
                listener_thread = _ShortPollSQSListener(
                    index,
                    queue.queue_name,
                    queue.bus.get(),
                    run_event,
                    handler_available_event,
                    queue.poll_interval,
                    region_name=queue.region_name
                )
            listener_thread.start()
            threads.append(listener_thread)

        # pylint: disable=too-many-nested-blocks
        try:
            while True:
                for bus in EVENT_BUSES_REGISTER:
                    # bus_size = bus.qsize()
                    a_message_was_processed = False
                    try:
                        message = bus.get().get(block=False)
                        handler_available_event.clear()
                        try:
                            self.handle_message(message[0], bus.name, bus.priority, message[1])
                            a_message_was_processed = True
                            # If handle message worked, then delete the message from SQS
                            message[1].delete()
                        except Exception:  # pylint: disable=broad-except
                            logger.error('Exception: unable to handle message', exc_info=True)
                            # SQS message won't be deleted and will probably end up in a dead-letter queue
                        finally:
                            bus.get().task_done()
                        handler_available_event.set()
                    except Empty:
                        pass

                    if a_message_was_processed:
                        # If a message was processed, we break the for loop
                        # so that we start it again via the while True
                        # This will allow to start again to process the top priority buses first
                        # (if any message is awaiting)
                        break

                time.sleep(0.1)
        except KeyboardInterrupt:
            # Queues threads are also asked to gracefully close
            run_event.clear()
            for thread in threads:
                thread.join()

    def listen(self):
        """Start listeners threads."""
        logger.info('Registering listeners on all queues')
        self._start_listeners()

    @abstractmethod
    def handle_message(self, queue_name, bus_name, priority, sqs_message):
        """Abstract method to be implemented: will take care of all messages received by the listeners."""
        pass
