from task_manager.events.WireloftEventEmitter import WireloftEventEmitter
from pyventus.events import EventEmitter


WIRELOFT_EVENT_EMITTER = WireloftEventEmitter()

def get_wireloft_event_emitter() -> EventEmitter:
    global WIRELOFT_EVENT_EMITTER
    return WIRELOFT_EVENT_EMITTER