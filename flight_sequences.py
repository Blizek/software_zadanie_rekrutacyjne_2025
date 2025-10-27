import time
import yaml
import logging
import utils

from argparse import ArgumentParser
from typing import Callable

from communication_library.frame import Frame
from procedures.start_sequence import run_start
from procedures.landing_sequence import run_landing


class FlightSequences:
    def __init__(self, proxy_address: str = "127.0.0.1", proxy_port: int = 3000,
                 config_path: str = 'simulator_config.yaml', verbose: bool = False,
                 parachute_velocity_threshold: float = 30.0, parachute_deploy_delay: float = 10.0):
        
        # initializing logger
        self.logger = logging.getLogger('flight_sequences')
        self.logger.setLevel(logging.DEBUG if verbose else logging.INFO)
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s'))
        self.logger.addHandler(ch)

        # load config
        with open(config_path, 'r') as fh:
            self.config = yaml.safe_load(fh)

        # connect manager to connect with rocket via TCP proxy
        self.cm = utils.connect_manager(proxy_address, proxy_port)

        # dictionaries of all sensors, servos and relays in rocket
        self.sensors = {name: None for name in self.config['devices'].get('sensor', {})}
        self.servos = {name: None for name in self.config['devices'].get('servo', {})}
        self.relays = {name: None for name in self.config['devices'].get('relay', {})}

        # parachute configuration
        self.parachute_velocity_threshold = parachute_velocity_threshold
        self.parachute_deploy_delay = parachute_deploy_delay

        # altitude/velocity tracking
        self._last_altitude = None
        self._last_alt_time = None
        self._last_velocity = None

        # apogee timestamp
        self._apogee_time = None

    # send commands to rocket's servos
    def send_servo(self, servo_name: str, position: int) -> None:
        utils.send_servo(self.cm, self.config, servo_name, position)

    # send commands to rocket's relays
    def send_relay(self, relay_name: str, open_: bool) -> None:
        utils.send_relay(self.cm, self.config, relay_name, open_)


    def _handle_incoming_frame(self, frame: Frame) -> None:
        try:
            parsed = utils.parse_feed_frame(frame, self.config)
            if parsed is not None:
                result = utils.apply_parsed_feed_to_state(self, parsed)
                if result:
                    kind, name, _, new = result
                    if kind == 'sensor' and name == 'altitude': # if altitude sensor updated we compute vertical velocity
                        try:
                            now = time.perf_counter()
                            vel = utils.compute_vertical_velocity(self._last_altitude, self._last_alt_time, new, now)
                            if vel is not None:
                                self._last_velocity = vel
                            self._last_altitude = new
                            self._last_alt_time = now
                        except Exception:
                            pass
                return
        except Exception as e:
            self.logger.debug(f'While handling frame {frame} an error occurred: {e}')

    # polling incoming frames and handling them
    def _poll_once(self, timeout_sec: float = 0.1) -> None:
        start = time.perf_counter()
        while time.perf_counter() - start < timeout_sec:
            frame = utils.receive_frame(self.cm, timeout=0)
            if frame is None:
                return
            self._handle_incoming_frame(frame)

    # wait for a predicate to become true or timeout
    def wait_for(self, predicate: Callable[[], bool], timeout: float, poll_interval: float = 0.2) -> bool:
        end = time.perf_counter() + timeout
        while time.perf_counter() < end:
            self._poll_once(poll_interval)
            try:
                if predicate():
                    return True
            except Exception:
                pass
        return False

    # main function to run flight sequences
    def run(self) -> bool:
        ok = run_start(self)
        if not ok:
            return False

        return run_landing(self)


def main():
    parser = ArgumentParser()
    parser.add_argument('--proxy-address', default='127.0.0.1')
    parser.add_argument('--proxy-port', default=3000, type=int)
    parser.add_argument('--config', default='simulator_config.yaml')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--parachute-velocity-threshold', type=float, default=30.0,
                        help='Max vertical speed (m/s) allowed for parachute deployment')
    parser.add_argument('--parachute-deploy-delay', type=float, default=10.0,
                        help='Time (s) to wait after apogee before deploying parachute')
    args = parser.parse_args()

    seq = FlightSequences(proxy_address=args.proxy_address,
                        proxy_port=args.proxy_port,
                        config_path=args.config,
                        verbose=args.verbose,
                        parachute_velocity_threshold=args.parachute_velocity_threshold,
                        parachute_deploy_delay=args.parachute_deploy_delay)

    ok = seq.run()
    if ok:
        print('Start sequence completed successfully')
    else:
        print('Start sequence failed')


if __name__ == '__main__':
    main()
