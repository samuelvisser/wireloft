from pyventus.events import EventEmitter, AsyncIOEventEmitter


WIRELOFT_EVENT_EMITTER = AsyncIOEventEmitter()

def get_wireloft_event_emitter() -> EventEmitter:
    global WIRELOFT_EVENT_EMITTER
    return WIRELOFT_EVENT_EMITTER