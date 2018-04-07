# -*- coding: utf-8 -*-

"""Package setup for multi_sqs_listener."""

from setuptools import setup, find_packages

setup(
    name='multi_sqs_listener',
    version='1.0.1',
    description='A Python package to listen in parallel to events coming from multiple AWS SQS queues.',
    url='https://github.com/fvinas/multi_sqs_listener.git',
    author='Fabien Vinas',
    author_email='fabien.vinas@gmail.com',
    license='MIT',
    packages=find_packages(),
    install_requires=[
        'boto3'
    ],
    zip_safe=False
)
