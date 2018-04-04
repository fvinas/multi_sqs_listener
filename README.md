multi_sqs_listener
==================

A Python package to listen in parallel to events coming from multiple AWS SQS queues

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

Quick example
-------------

Here a very simple example of a worker waiting for messages coming from one SQS queue:

```python
from multi_sqs_listener import SQSListenerConfig, MultiSQSListener

class MyListener(MultiSQSListener):
    def handle_message(self, queue, bus, priority, message):
        print(message.body)

my_queue = SQSListenerConfig('name-of-my-queue')  # multiple default values used here, for instance polling type defaulting to long polling
my_listener = MyListener([my_queue])
my_listener.listen()
```


Common usage patterns
---------------------

### Broadcasting events to a pool of servers

A common pattern when you have a pool of EC2 instances is to have a dedicated, temporary SQS queue for each server (for instance named after its instance ID), all subscribing to a shared SNS topic and listened to by their server via a dedicated `SQSListenerConfig`.

When you send a message to the SNS topic, it will the be broadcasted to all SQS queues via AWS native mechanisms, then sending an event to all your servers.

### Fast & slow lane

Another common pattern is to deal with events with different priorities, processing first those with the highest priority.

`multi_sqs_listener` supports this priority natively, allowing you to priorize *per queue*.

Below is a example of a main loop processing long, low priority events but needed to react as soon as possible to a high priority one.
Note that it does not interrupt any event being currently processed, but rather puts the one with the highest priority next first the list before any low priority event.

```python
# Server code
# Assuming you have two SQS queues named 'low-priority-queue' and 'high-priority-queue'

import time
from multi_sqs_listener import SQSListenerConfig, MultiSQSListener


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

low_prioriy_queue = SQSListenerConfig('low-priority-queue', priority_number=1)
high_prioriy_queue = SQSListenerConfig('high-priority-queue', priority_number=5, bus_name='high-priority-bus')
my_listener = MyListener([low_prioriy_queue, high_prioriy_queue])
my_listener.listen()
```

To test this code we send events on the SQS from somewhere else (here using AWS CLI):

```python
import boto3

sqs = boto3.resource('sqs')
low_q = sqs.get_queue_by_name(QueueName='low-priority-queue')
high_q = sqs.get_queue_by_name(QueueName='high-priority-queue')

for job_index in range(5):
    low_q.send_message(MessageBody='Job #{} with no priority'.format(job_index))

high_q.send_message(MessageBody='Priority message')
```

You would get an output close to this one, highlighting the fact that "priority message" has been prioritized by the worker over messages with low priority.
```bash
Starting low priority, long job: Job #0 with no priority
Ended low priority job: Job #0 with no priority
Starting low priority, long job: Job #4 with no priority
Ended low priority job: Job #4 with no priority
Starting high priority, quick job: Priority message
Ended high priority job: Priority message
Starting low priority, long job: Job #1 with no priority
Ended low priority job: Job #1 with no priority
Starting low priority, long job: Job #2 with no priority
Ended low priority job: Job #2 with no priority
Starting low priority, long job: Job #3 with no priority
Ended low priority job: Job #3 with no priority
```

### Concurrent work & administrative events

In this common pattern, you have multiple queues, with different priorities, for work-related messages, plus another one for administrative messages (e.g. the server should update a model, it should reboot, …). This use case is thus a combination of the two cases described below: shared queues with multiple priorities and a queue dedicated to the current worker. 

Details
-------

### `SQSListenerConfig`

This object holds the configuration for a SQS queue to be subscribed and comes with the following parameters:

 - `queue_name` (string, mandatory): the AWS name of the queue
 - `priority_number` (integer, optional, defaults to `1`): defines the priority level of the events coming from this SQS queue (the higher, the more priority)
 - `bus_name` (string, optional, defaults to `'default-bus'`): defines the internal name of the event bus to which the SQS queue events will be forwarded (details below)
 - `queue_type` (string valued to `'long-poll'` or `'short-poll'`, optional, defaults to `'long-poll'`): defines the way the SQS queue will be polled by the listener thread (long or short polling -- details below).

### `MultiSQSListener`

This object is the main class for the package to instanciate all components.
It's an abstract class that you're expected to derive by implementing the `handle_message` method that will be called when an event is coming in.

Once you've implemented your custom version of the abstract class, you can instanciate it with the following parameters:
 - `queues_configuration` (list of `SQSListenerConfig`, mandatory): a list holding the configuration of the SQS queues to listen to
 - `logger` (`logging.Logger`, optional, defaults to `logging.getLogger(__name__)`): the logger that will be used to log the listener thread's internal events (typically `logging.DEBUG` messages) 
 - `poll_interval` (integer, optional, defaults to `60`): polling interval, in seconds, in the case of short polling (for now you have to use the same polling interval for all short polled queues)
 - `region_name` (string, optional, defaults to `'eu-west-1'`): AWS region your queues will belong to. Will be used by the `SQSListenerConfig` to refer to the actual AWS SQS queues objects.

### Long vs short polling

At the beginning of SQS, AWS only allowed polling queues using periodic polling based on a subset of all SQS hosts.
This method had multiple drawbacks: a balance had to be found between the number of API calls (and thus the cost of SQS) and the ability to react quickly to events coming in SQS queues. Moreover there was no guarantee to get a message even if it was in the queue, since the actual implementation of short polling only polled a random subset of all SQS hosts).


Then, in late 2012 AWS released [1] the *long polling* feature: based on long TCP connections, this allows a SQS client to subscribe to SQS queues keeping a connection open until a message is coming in. Thus the SQS client no longer has to deal with periodic polling, plus it's requesting messages from all SQS hosts and not only a subset of them.


In most cases you won't even have to think about it and leave the default `queue_type='long-poll'` parameter when instanciating your `SQSListenerConfig`. In specific cases, especially when the throughput of messages in the queue is really high, you may consider using short polling instead. We advise you to refer to the AWS SQS documentation [2] and FAQ [3].

[1]: https://aws.amazon.com/blogs/aws/amazon-sqs-long-polling-batching/
[2]: https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-long-polling.html
[3]: https://aws.amazon.com/sqs/faqs/?nc1=h_ls

### Event buses

Internally, the `MultiSQSListener` component deals with multiple events and concurrent threads with thread safe Python `Queue.PriorityQueue` objects. This allows kind of inter threads communication, preventing a thread from retrieving messages from SQS while it's already working on a message with a higher priority (thus delaying their processing).


If you're not happy with the way concurrent messages are prioritized between the listeners, you should understand how it works:
 - there is a big, infinite event loop
 - each iteration of this loop will iterate through all registered buses (each of them gathering events from one or more SQS queues), one by one
    - if the current bus is empty, then it doesn't block the main thread and iterates to the next one
    - 



You won't really have to deal with buses except when instanciating `SQSListenerConfig` objects: you may need to define a `bus_name` other than the default `'default-bus'` if you want to 

Known issues and todos
======================

- In case of multiple events waiting in a high priority SQS, the listeners sometimes interleave low priority events in between when they come from long polled queues (which is not the purpose: all events with higher priority should be considered first ✌️). So, naming `H` events with high priority and `L` events with low priority, it sometimes happen to process: `L L L L H L H L H L H L H L L L L L` (considering a sequence of 5 `H`s arrives in the SQS while the fourth `L` is being processed). This behaviour is easy to simulate with one instance only, long polling a high- and a low-priority queue. It is more rare when there are multiple workers consuming messages from the queues, and fully disappears when the low-priority queue is short-polled

- Allow poll interval to be customized per queue.

- Allow `region_name` to be defined per SQS queue (or to define the queues also by full URL instead of names).

Authors
=======

Originally created and maintained by [Fabien Vinas](https://github.com/fvinas)

License
=======

MIT Licensed. See LICENSE.txt for full details.
