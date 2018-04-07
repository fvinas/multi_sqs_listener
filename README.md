multi_sqs_listener
==================

A Python package to listen in parallel to events coming from multiple AWS SQS queues


![Packagist](https://img.shields.io/packagist/l/doctrine/orm.svg)
[![PyPI](https://img.shields.io/pypi/v/nine.svg)](https://pypi.org/project/multi_sqs_listener/1.0.1/)


Getting started
---------------

`multi_sqs_listener` allows you to quickly add AWS SQS events handlers to your event-based softwares (daemons, services…).

The package doesn't deal with the daemon / service part of the code but creates the main event waiting loop.

Also, it assumes that your AWS SQS queues already exist and won't create them for you.

It builds an event loop in the main thread along with as dedicated queue threads (one per SQS queue that is listened to).

Main features include:
 - supports *long* and *short polling* (see https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-long-polling.html)
 - creates an event loop in the current thread
 - creates a dedicated, synchronized thread for each SQS queue
 - deals with priorities

`multi_sqs_listener` uses `boto3` for all AWS operations, so your AWS authentication is that of `boto3` (role, credentials, …).

Tested with Python 2.7 and 3.6.

Quick example
-------------

Here a very simple example of a worker waiting for messages coming from one SQS queue:

```python
from multi_sqs_listener import QueueConfig, EventBus, MultiSQSListener

class MyListener(MultiSQSListener):
    def handle_message(self, queue, bus, priority, message):
        # This is where your actual event handler code would sit
        print(message.body)

my_event_bus = EventBus()  # leaving default name & priority
EventBus.register_buses([my_event_bus])

my_queue = QueueConfig('my-queue', my_event_bus)  # multiple default values here
my_listener = MyListener([my_queue])
my_listener.listen()
```


Common usage patterns
---------------------

### Broadcasting events to a pool of servers

A common pattern when you have a pool of EC2 instances is to have a dedicated, temporary SQS queue for each server (for instance named after its instance ID), all subscribing to a shared SNS topic and listened to by their server via a dedicated `SQSListenerConfig`.

When you send a message to the SNS topic, it will then be broadcast to all SQS queues via AWS native mechanisms, then sending an event to all your servers.

### Handling fast & slow lanes

Another common pattern is to deal with events with different priorities, processing first those with the highest priority.

`multi_sqs_listener` supports this priority natively, allowing you to priorize *per queue*.

Below is a example of a main loop processing long, low priority events but needed to react as soon as possible to a high priority one.
Note that it does not interrupt any event being currently processed, but rather puts the one with the highest priority next first the list before any low priority event.

```python
# Server code
# Assuming you have two SQS queues named 'low-priority-queue' and 'high-priority-queue'

import time
from multi_sqs_listener import QueueConfig, EventBus, MultiSQSListener


class MyListener(MultiSQSListener):
    def low_priority_job(self, message):
        print('Starting low priority, long job: {}'.format(message))
        time.sleep(5)
        print('Ended low priority job: {}'.format(message))
    def high_priority_job(self, message):
        print('Starting high priority, quick job: {}'.format(message))
        time.sleep(.2)
        print('Ended high priority job: {}'.format(message))
    def handle_message(self, queue, bus, priority, message):
        if bus == 'high-priority-bus':
            self.high_priority_job(message.body)
        else:
            self.low_priority_job(message.body)

low_priority_bus = EventBus('low-priority-bus', priority=1)
high_priority_bus = EventBus('high-priority-bus', priority=5)
EventBus.register_buses([low_priority_bus, high_priority_bus])

low_priority_queue = QueueConfig('low-priority-queue', low_priority_bus)
high_priority_queue = QueueConfig('high-priority-queue', high_priority_bus)
my_listener = MyListener([low_priority_queue, high_priority_queue])
my_listener.listen()
```

To test this code we send events on the SQS from somewhere else:

```python
import boto3

sqs = boto3.resource('sqs')
low_q = sqs.get_queue_by_name(QueueName='low-priority-queue')
high_q = sqs.get_queue_by_name(QueueName='high-priority-queue')

for job_index in range(100):
    low_q.send_message(MessageBody='Job #{} with no priority'.format(job_index))

high_q.send_message(MessageBody='Priority message')
high_q.send_message(MessageBody='Priority message')
```

You would get an output close to this one, highlighting the fact that "priority message" has been prioritized by the worker over messages with low priority.

```bash
Starting low priority, long job: Job #0 with no priority
Ended low priority job: Job #0 with no priority
Starting high priority, quick job: Priority message
Ended high priority job: Priority message
Starting high priority, quick job: Priority message
Ended high priority job: Priority message
Starting low priority, long job: Job #4 with no priority
Ended low priority job: Job #4 with no priority
Starting low priority, long job: Job #1 with no priority
Ended low priority job: Job #1 with no priority
Starting low priority, long job: Job #2 with no priority
Ended low priority job: Job #2 with no priority
Starting low priority, long job: Job #3 with no priority
Ended low priority job: Job #3 with no priority
```

### Concurrent work & administrative events

In this common pattern, you have multiple queues, with different priorities, for work-related messages, plus another one for administrative messages (e.g. the server should update a model, it should reboot, …). This use case is thus a combination of the two cases described below: shared queues with multiple priorities and a queue dedicated to the current worker. 

```python
# Server code
# Assuming you have:
#  - two 'work' related SQS queues named 'low-priority-queue' and 'high-priority-queue'
#  - one 'administrative-events-queue'

import time
from multi_sqs_listener import QueueConfig, EventBus, MultiSQSListener


class MyListener(MultiSQSListener):
    def job_event(self, message):
        print('Starting job: {}'.format(message))
        time.sleep(2)
        print('Ended job: {}'.format(message))
    def administrative_event(self, message):
        print('Starting administrative event: {}'.format(message))
        time.sleep(.2)
        print('Ended administrative_event: {}'.format(message))
    def handle_message(self, queue, bus, priority, message):
        if bus == 'administrative-bus':
            self.administrative_event(message.body)
        else:
            self.job_event(message.body)


if __name__ == '__main__':
    # Event buses
    low_priority_job_bus = EventBus('low-priority-bus', priority=1)
    high_priority_job_bus = EventBus('high-priority-bus', priority=5)
    administrative_event_bus = EventBus('high-priority-bus', priority=10)
    EventBus.register_buses([
        low_priority_job_bus,
        high_priority_job_bus,
        administrative_event_bus
    ])

    # Queues
    low_prioriy_queue = QueueConfig('low-priority-queue', low_priority_job_bus)
    high_prioriy_queue = QueueConfig('high-priority-queue', administrative_event_bus)
    admin_queue = QueueConfig('admin-queue', administrative_event_bus)

    # Listener
    my_listener = MyListener([low_priority_queue, high_priority_queue, admin_queue])
    my_listener.listen()

```

Details
-------

### `EventBus`

An event bus is where the events messages will be put once retrieved by the listeners.
Different queues listeners may put messages in the same bus if you wish to.

The benefit of using multiple queues is to prioritize messages: each time a worker finishes a job, it starts looking at potential messages waiting in the buses ordered by their priority (highest first).

Once instanciated, you have to register the buses using the `EventBus.register_buses` static method.

Thus, the following default config defines only one bus, with the default name `'default-bus'`:

```python
from multi_sqs_listener import EventBus

event_bus = EventBus()  # defaults: name='default-bus', priority=1
EventBus.register_buses([event_bus])
```

But if you wish to elaborate a more advanced configuration with multiple priorities, you would need something like this:

```python
from multi_sqs_listener import EventBus

low_priority_bus = EventBus('low-priority-bus', priority=1)
medium_priority_bus = EventBus('medium-priority-bus', priority=2)
high_priority_bus = EventBus('high-priority-bus', priority=3)
EventBus.register_buses([low_priority_bus, medium_priority_bus, high_priority_bus])
```

Internally the `EventBus.register_buses` method not only registers them, but also sorts them so that any iteration will always start with the highest priority bus.

### `QueueConfig`

This object holds the configuration for a SQS queue to be subscribed.
It refers to an SQS object and must indicate in which event bus messages from this SQS queue will be put.

It comes with the following parameters:

 - `queue_name` (string, mandatory): the AWS name of the queue, will be used to build the actual object.
 - `bus` (`EventBus`, mandatory): incidates in which event bus messages coming from this SQS queue will be put
 - `queue_type` (string valued to `'long-poll'` or `'short-poll'`, optional, defaults to `'long-poll'`): defines the way the SQS queue will be polled by the listener thread (long or short polling -- details below).
 - `region_name` (string, optional, defaults to `'eu-west-1'`): AWS region the SQS queue belongs to.
 - `poll_interval` (integer, optional, defaults to `60`): polling interval, in seconds, in the case of short polling.

### `MultiSQSListener`

This object is the main class for the package to instanciate all components.
It's an abstract class that you're expected to derive by implementing the `handle_message` method that will be called when an event is coming in.

Once you've implemented your custom version of the abstract class, you can instanciate it with the following parameter:
 - `queues_configuration` (list of `QueueConfig` objects, mandatory): a list holding the configuration of the SQS queues to listen to.

### Long vs short polling

At the beginning of SQS, AWS only allowed polling queues using periodic polling based on a subset of all SQS hosts.
This method had multiple drawbacks: a balance had to be found between the number of API calls (and thus the cost of SQS) and the ability to react quickly to events coming in SQS queues. Moreover there was no guarantee to get a message even if it was in the queue, since the actual implementation of short polling only polled a random subset of all SQS hosts).


Then, in late 2012 [AWS released][1] the *long polling* feature: based on long TCP connections, this allows a SQS client to subscribe to SQS queues keeping a connection open until a message is coming in. Thus the SQS client no longer has to deal with periodic polling, plus it's requesting messages from all SQS hosts and not only a subset of them.


In most cases you won't even have to think about it and leave the default `queue_type='long-poll'` parameter when instanciating your `SQSListenerConfig`. In specific cases, especially when the throughput of messages in the queue is really high, you may consider using short polling instead. We advise you to refer to the [AWS SQS documentation][2] and [AWS SQS FAQ][3].

Please also read this [very interesting article][4] about long vs short polling SQS queues.

[1]: https://aws.amazon.com/blogs/aws/amazon-sqs-long-polling-batching/
[2]: https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-long-polling.html
[3]: https://aws.amazon.com/sqs/faqs/?nc1=h_ls
[4]: http://pragmaticnotes.com/2017/11/20/amazon-sqs-long-polling-versus-short-polling/

Authors
-------

Originally created and maintained by [Fabien Vinas](https://github.com/fvinas)

License
-------

MIT Licensed. See LICENSE.txt for full details.
