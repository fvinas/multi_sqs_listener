# -*- encoding: utf-8 -*-

import time
import json
from threading import Thread, Event
from Queue import PriorityQueue, Empty
import boto3
from abc import ABCMeta, abstractmethod


class SQSListenerConfig(object):
  '''A class to store an individual queue configuration
  '''
  def __init__(self, queue_name, **kwargs):
    self.queue_name = queue_name
    self.priority_number = kwargs['priority_number'] if 'priority_number' in kwargs else 1
    self.bus_name = kwargs['bus_name'] if 'bus_name' in kwargs else 'default-bus'
    self.queue_type = kwargs['queue_type'] if 'queue_type' in kwargs else 'long-poll'
    self.queue_url = ''

  def __repr__(self):
  	return '(name={}, url={})'.format(self.queue_name, self.queue_url)



class _LongPollSQSListener(Thread):
  '''A SQS listener designed to work alone in a separate thread
  '''
  def __init__(self, thread_id, queue_name, outbound_bus, priority_number, run_event, handler_available_event, **kwargs):
    Thread.__init__(self)
    self.thread_id = thread_id 
    self._region_name = kwargs['region_name'] if 'region_name' in kwargs else 'eu-west-1'
    self._outbound_bus = outbound_bus
    self._queue_name = queue_name
    self._priority_number = priority_number
    self._handler_available_event = handler_available_event
    sqs = boto3.resource('sqs', region_name=self._region_name)
    self._queue = sqs.get_queue_by_name(QueueName=self._queue_name)
    self._run_event = run_event
    print('Starting up thread {} and long-polling inbound queue {}'.format(self.thread_id, self._queue_name))

  def run(self):
    print('Long polling queue {}'.format(self._queue_name))
    while True and self._run_event.is_set():
      # TODO: make MaxNumberOfMessages customizable?
      self._handler_available_event.wait()
      while self._outbound_bus.full():
        time.sleep(0.01)
      messages = self._queue.receive_messages(MaxNumberOfMessages=1, WaitTimeSeconds=5)
      if len(messages) > 0:
        while self._outbound_bus.full():
          time.sleep(0.01) 
        self._outbound_bus.put((self._priority_number, self._queue_name, messages[0]))

  def stop(self):
    print('Thread {} stopped'.format(self.thread_id))
    pass


class _ShortPollSQSListener(Thread):
  '''A SQS listener designed to work alone in a separate thread
  '''
  def __init__(self, thread_id, queue_name, outbound_bus, run_event, handler_available_event, poll_interval = 10, **kwargs):
    Thread.__init__(self)
    self.thread_id = thread_id 
    self._region_name = kwargs['region_name'] if 'region_name' in kwargs else 'eu-west-1'
    self._outbound_bus = outbound_bus
    self._queue_name = queue_name
    self._poll_interval = poll_interval
    self._handler_available_event = handler_available_event
    sqs = boto3.resource('sqs', region_name=self._region_name)
    self._queue = sqs.get_queue_by_name(QueueName=self._queue_name)
    self._run_event = run_event
    print('Starting up thread {} and short-polling inbound queue {}'.format(self.thread_id, self._queue_name))

  def run(self):
    print('Short polling queue {}'.format(self._queue_name))
    while True and self._run_event.is_set():
      self._handler_available_event.wait()
      while self._outbound_bus.full():
        time.sleep(0.01)
      messages = self._queue.receive_messages(MaxNumberOfMessages=1)
      if len(messages) > 0:
        while self._outbound_bus.full():
          time.sleep(0.01) 
        self._outbound_bus.put((1, self._queue_name, messages[0]))
      else:
        time.sleep(self._poll_interval)

  def stop(self):
    print('Thread {} stopped'.format(self.thread_id))
    pass


class MultiSQSListener(object):
  __metaclass__ = ABCMeta

  def __init__(self, queues_configuration, **kwargs):
    self._poll_interval = kwargs['poll_interval'] if 'poll_interval' in kwargs else 60
    self._region_name = kwargs['region_name'] if 'region_name' in kwargs else 'eu-west-1'
    self._force_delete = kwargs['force_delete'] if 'force_delete' in kwargs else False
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
      print('Launching listener for {} in thread {}, outbound bus {}, type {}'.format(queue.queue_name, i, queue.bus_name, queue.queue_type))
      if queue.queue_type == 'long-poll':
        listener_thread = _LongPollSQSListener(
          i,
          queue.queue_name,
          self.outbound_buses[queue.bus_name],
          queue.priority_number,
          run_event,
          handler_available_event
        )
      else:
        listener_thread = _ShortPollSQSListener(
          i,
          queue.queue_name,
          self.outbound_buses[queue.bus_name],
          run_event,
          handler_available_event,
          self._poll_interval
        )
      listener_thread.start()
      threads.append(listener_thread)

    # TODO: put mechanism in place so that the threads no longer add things to the queue
    # while the handler is dealing with a message
    try:
      while True:
      	for bus_name, bus in self.outbound_buses.iteritems():
      	  bus_size = bus.qsize()
      	  print('Bus size {} == {}'.format(bus_name, bus.qsize()))
      	  try:
      	  	message = bus.get(block=False)
      	  	handler_available_event.clear()
      	  	try:
      	  	  self.handle_message(message[1], bus_name, message[0], message[2])
      	  	  # If handle message worked, then delete the message from SQS
      	  	  message[2].delete()
      	  	except Exception as ex:
      	  	  # TODO: add another behaviour?
      	  	  raise Exception(ex)
      	  	handler_available_event.set()
      	  except Empty:
      	  	pass
        time.sleep(0.5)
    except KeyboardInterrupt:
      # Queues threads are also asked to gracefully close
      run_event.clear()
      for thread in threads:
        thread.join()

  def listen(self):
    print("Listening to all queues")
    self._start_listeners()

  @abstractmethod
  def handle_message(self, queue_name, bus_name, priority, sqs_message):
  	pass
