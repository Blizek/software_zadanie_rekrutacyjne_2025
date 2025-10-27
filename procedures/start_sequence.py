import time

from typing import Any


def run_start(seq: Any) -> bool:
    seq.logger.info('Starting automated start sequence')

    seq.logger.info('Opening oxidizer intake')
    open_pos = seq.config['devices']['servo']['oxidizer_intake']['open_pos']
    closed_pos = seq.config['devices']['servo']['oxidizer_intake']['closed_pos']
    seq.send_servo('oxidizer_intake', open_pos)

    ok = seq.wait_for(lambda: seq.sensors.get('oxidizer_level') >= 100.0, timeout=60.0)
    if not ok:
        seq.logger.error('Timeout while filling oxidizer tank')
        return False

    seq.logger.info('Oxidizer filled')
    seq.logger.info("Closing oxidizer intake")
    seq.send_servo('oxidizer_intake', closed_pos)

    seq.logger.info('Opening fuel intake')
    f_open = seq.config['devices']['servo']['fuel_intake']['open_pos']
    f_closed = seq.config['devices']['servo']['fuel_intake']['closed_pos']
    seq.send_servo('fuel_intake', f_open)

    ok = seq.wait_for(lambda: seq.sensors.get('fuel_level') >= 100.0, timeout=60.0)
    if not ok:
        seq.logger.error('Timeout while filling fuel tank')
        return False

    seq.logger.info('Fuel filled')
    seq.logger.info("Closing fuel intake")
    seq.send_servo('fuel_intake', f_closed)

    seq.logger.info('Turning on oxidizer heater')
    seq.send_relay('oxidizer_heater', True)

    ok = seq.wait_for(lambda: seq.sensors.get('oxidizer_pressure') >= 55.0, timeout=120.0)
    if not ok:
        seq.logger.warning('Not reached target pressure of 55 bar in given time')

    if seq.sensors.get('oxidizer_pressure') >= 90.0:
        seq.logger.error('Oxidizer pressure exceeded 90 bar — abort')
        seq.send_relay('oxidizer_heater', False)
        return False

    seq.logger.info('Ignition sequence — opening main valves and starting igniter')

    ox_pressure = seq.sensors.get('oxidizer_pressure') or 0.0
    if ox_pressure < 40.0:
        seq.logger.error(f'Oxidizer pressure too low for ignition: {ox_pressure:.1f} bar')
        return False
    if ox_pressure > 65.0:
        seq.logger.error(f'Oxidizer pressure too high for ignition: {ox_pressure:.1f} bar')
        return False

    if (seq.servos.get('fuel_intake') is not None and seq.servos.get('fuel_intake') < 50) or \
       (seq.servos.get('oxidizer_intake') is not None and seq.servos.get('oxidizer_intake') < 50):
        seq.logger.error('Intake valves appear to be open during ignition — abort')
        return False

    main_open = seq.config['devices']['servo']['fuel_main']['open_pos']
    seq.send_servo('fuel_main', main_open)
    t1 = time.perf_counter()
    time.sleep(0.2)
    seq.send_servo('oxidizer_main', seq.config['devices']['servo']['oxidizer_main']['open_pos'])
    t2 = time.perf_counter()
    if abs(t2 - t1) > 1.0:
        seq.logger.error('Różnica czasu otwarcia zaworów głównych > 1s — abort')
        return False
    
    seq.send_relay('igniter', True)

    ok = seq.wait_for(lambda: seq.sensors.get('altitude') is not None and seq.sensors.get('altitude') > 1.0,
                       timeout=10.0)
    if not ok:
        seq.logger.error('No altitude increase detected after ignition — abort')
        return False

    seq.logger.info('Start completed successfully — rocket is in flight')
    return True
