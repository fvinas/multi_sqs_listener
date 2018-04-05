# -*- coding: utf-8 -*-

"""multi_sqs_listener:
A Python package to listen in parallel to events coming from multiple AWS SQS queues."""


from .config import QueueConfig, EventBus
from .multi_sqs_listener import MultiSQSListener


__all__ = [
    'EventBus',
    'QueueConfig',
    'MultiSQSListener'
]
