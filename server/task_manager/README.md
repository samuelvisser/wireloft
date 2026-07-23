# WireLoft Motherboard

This package is meant to link together the various components of WireLoft.
It contains a scheduler to schedule and run jobs at a given time or interval. It also contains
an event bus to communicate between components. It is designed to keep WireLoft dynamic and extensible.

For example, if a show gets added certain actions need to run, and others (like checking for new episodes)
need to start running periodically. This allows for a more dynamic and extensible system, where new features
can be added without requiring significant changes to existing code.

The scheduler is built on top of APScheduler and supports both interval and cron-based scheduling. It also provides
a simple API for registering tasks and scheduling them to run at specific times or intervals. The event bus is built
on top of Pyventus, a lightweight and efficient event bus for Python.