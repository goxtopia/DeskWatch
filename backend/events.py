import logging
from typing import Callable, Dict, List

logger = logging.getLogger("deskwatch.events")

class EventBus:
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}

    def subscribe(self, event_type: str, callback: Callable):
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        if callback not in self._subscribers[event_type]:
            self._subscribers[event_type].append(callback)
            logger.info(f"Subscribed callback {callback.__name__} to event {event_type}")

    def unsubscribe(self, event_type: str, callback: Callable):
        if event_type in self._subscribers:
            try:
                self._subscribers[event_type].remove(callback)
                logger.info(f"Unsubscribed callback {callback.__name__} from event {event_type}")
            except ValueError:
                pass

    def publish(self, event_type: str, *args, **kwargs):
        if event_type in self._subscribers:
            for callback in self._subscribers[event_type]:
                try:
                    callback(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Error executing callback {callback} for event {event_type}: {e}", exc_info=True)

# Global event bus instance
event_bus = EventBus()
