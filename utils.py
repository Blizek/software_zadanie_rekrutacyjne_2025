import logging
from typing import Optional

from communication_library.communication_manager import CommunicationManager
from communication_library.tcp_transport import TcpSettings
from communication_library.transport import TransportType
from communication_library.frame import Frame
from communication_library import ids
from communication_library.exceptions import TransportTimeoutError, UnregisteredCallbackError

logger = logging.getLogger('utils')


def connect_manager(proxy_address: str = '127.0.0.1', proxy_port: int = 3000) -> CommunicationManager:
    """Create and connect a CommunicationManager to the TCP proxy.

    Returns a connected CommunicationManager instance or raises on error.
    """
    cm = CommunicationManager()
    cm.change_transport_type(TransportType.TCP)
    cm.connect(TcpSettings(proxy_address, proxy_port))
    logger.debug(f'Connected CommunicationManager to {proxy_address}:{proxy_port}')
    return cm


def push_and_send(cm: CommunicationManager, frame: Frame) -> None:
    """Push a frame into the manager queue and send it.

    Non-fatal transport timeouts are logged but do not raise.
    """
    logger.debug(f'push_and_send: {frame}')
    cm.push(frame)
    try:
        cm.send()
    except TransportTimeoutError:
        logger.error('Transport timeout while sending frame')


def receive_frame(cm: CommunicationManager, timeout: float = 0) -> Optional[Frame]:
    """Attempt to receive a frame from the manager.

    - Returns a Frame when available.
    - Returns None when no frame was available (transport timeout).
    - Returns the frame embedded in UnregisteredCallbackError when no callback matched.
    """
    try:
        frame = cm.receive()
        return frame
    except TransportTimeoutError:
        return None
    except UnregisteredCallbackError as e:
        # Return the frame that didn't match a callback so caller can handle it
        return e.frame
    except Exception as e:
        logger.debug(f'Unexpected error while receiving frame: {e}')
        return None


def build_servo_frame(config: dict, servo_name: str, position: int) -> Frame:
    sconf = config['devices']['servo'][servo_name]
    device_id = sconf['device_id']
    frame = Frame(destination=ids.BoardID.ROCKET,
                  priority=ids.PriorityID.LOW,
                  action=ids.ActionID.SERVICE,
                  source=ids.BoardID.SOFTWARE,
                  device_type=ids.DeviceID.SERVO,
                  device_id=device_id,
                  data_type=ids.DataTypeID.INT16,
                  operation=ids.OperationID.SERVO.value.POSITION,
                  payload=(int(position),))
    return frame


def send_servo(cm: CommunicationManager, config: dict, servo_name: str, position: int) -> None:
    frame = build_servo_frame(config, servo_name, position)
    push_and_send(cm, frame)


def build_relay_frame(config: dict, relay_name: str, open_: bool) -> Frame:
    rconf = config['devices']['relay'][relay_name]
    device_id = rconf['device_id']
    op = ids.OperationID.RELAY.value.OPEN if open_ else ids.OperationID.RELAY.value.CLOSE
    frame = Frame(destination=ids.BoardID.ROCKET,
                  priority=ids.PriorityID.LOW,
                  action=ids.ActionID.SERVICE,
                  source=ids.BoardID.SOFTWARE,
                  device_type=ids.DeviceID.RELAY,
                  device_id=device_id,
                  data_type=ids.DataTypeID.NO_DATA,
                  operation=op,
                  payload=())
    return frame


def send_relay(cm: CommunicationManager, config: dict, relay_name: str, open_: bool) -> None:
    frame = build_relay_frame(config, relay_name, open_)
    push_and_send(cm, frame)


def compute_vertical_velocity(last_alt: Optional[float], last_time: Optional[float],
                              new_alt: float, new_time: float) -> Optional[float]:
    """Return vertical velocity (m/s) given two altitude samples or None if not computable.

    Positive = ascending, Negative = descending.
    """
    if last_alt is None or last_time is None:
        return None
    dt = new_time - last_time
    if dt <= 0:
        return None
    try:
        return (new_alt - last_alt) / dt
    except Exception:
        return None


def parse_feed_frame(frame: Frame, config: dict) -> Optional[dict]:
    """Parse a FEED Frame into a dict: {'kind': 'sensor'|'servo'|'relay','name':str,'value':number}.

    Returns None if the frame is not an ActionID.FEED or mapping not found.
    """
    try:
        if frame.action != ids.ActionID.FEED:
            return None

        # sensors
        if frame.device_type == ids.DeviceID.SENSOR:
            for name, sconf in config['devices'].get('sensor', {}).items():
                if sconf['device_id'] == frame.device_id:
                    # sensors treated as float
                    return {'kind': 'sensor', 'name': name, 'value': float(frame.data)}
            return None

        # servos
        if frame.device_type == ids.DeviceID.SERVO:
            for name, sconf in config['devices'].get('servo', {}).items():
                if sconf['device_id'] == frame.device_id:
                    return {'kind': 'servo', 'name': name, 'value': int(frame.data)}
            return None

        # relays
        if frame.device_type == ids.DeviceID.RELAY:
            for name, rconf in config['devices'].get('relay', {}).items():
                if rconf['device_id'] == frame.device_id:
                    # relay payload may be empty; interpret presence as 1
                    try:
                        val = int(frame.data)
                    except Exception:
                        val = 1
                    return {'kind': 'relay', 'name': name, 'value': val}

    except Exception as e:
        logger.debug(f'parse_feed_frame error: {e}')
    return None


def apply_parsed_feed_to_state(state_obj: object, parsed: dict) -> Optional[tuple]:
    """Apply parsed feed dict to state object which must have `sensors`, `servos`, `relays` dicts.

    Returns tuple (kind, name, old, new) or None if not applied.
    """
    try:
        kind = parsed['kind']
        name = parsed['name']
        value = parsed['value']
        if kind == 'sensor':
            old = state_obj.sensors.get(name)
            state_obj.sensors[name] = value
            return (kind, name, old, value)
        if kind == 'servo':
            old = state_obj.servos.get(name)
            state_obj.servos[name] = value
            return (kind, name, old, value)
        if kind == 'relay':
            old = state_obj.relays.get(name)
            state_obj.relays[name] = value
            return (kind, name, old, value)
    except Exception as e:
        logger.debug(f'apply_parsed_feed_to_state error: {e}')
    return None
