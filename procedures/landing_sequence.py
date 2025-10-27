import time

from typing import Any


def run_landing(seq: Any) -> bool:
    try:
        # Monitoring altitude to detect rocket's apogee
        seq.logger.info('Monitoring altitude')
        prev_alt = None
        is_falling = False
        while True:
            seq._poll_once(0.5)
            alt = seq.sensors.get('altitude')
            fuel = seq.sensors.get('fuel_level')
            if alt is None:
                continue
            if prev_alt is None:
                prev_alt = alt
                continue
            if alt < prev_alt: # if previous altitude greater than current it means that rocket is falling
                is_falling = True
            else:
                is_falling = False
            prev_alt = alt
            
            if is_falling and fuel == 0.0: # if rocket is falling and fuel is empty we reached apogee
                seq._apogee_time = time.perf_counter()
                seq.logger.info('Apogee detected')
                break

        # function to check if parachute should be deployed due to velocity threshold
        def parachute_pred():
            vel = seq._last_velocity
            # to avoid deploying parachute with velocity over the threshold we deploy it when rocket is falling with velocity near the threshold (around 90%)
            if vel is not None and vel < 0 and abs(vel) >= 0.9 * seq.parachute_velocity_threshold:
                seq.logger.info(f'Deploying parachute due to velocity threshold: |v|={abs(vel):.2f} >= 90% of threshold')
                return True

            return False

        # checking rocket's free fall velocity and deciding when to deploy parachute
        seq.logger.info(f'Monitoring velocity for parachute deployment ({seq.parachute_deploy_delay}s window)')
        deployed = False
        end_check = time.perf_counter() + seq.parachute_deploy_delay
        while time.perf_counter() < end_check:
            seq._poll_once(1.0)
            try:
                if parachute_pred():
                    seq.logger.info('Deploying parachute')
                    seq.send_relay('parachute', True)
                    deployed = True
                    break
            except Exception:
                pass

        if not deployed:
            seq.logger.info('10s elapsed without safe deploy - forcing parachute')
            seq.send_relay('parachute', True)

        # waiting for landing of the rocket (due to receiving previous altitude after landing (which is not zero) we check every second if velocity changed, 
        # if not that means rocket has landed)
        seq.logger.info('Waiting for landing')
        landed = False
        prev_altitude = None
        alt_epsilon = 0.01
        while not landed:
            seq._poll_once(0.5)
            alt = seq.sensors.get('altitude')
            if (prev_altitude is not None) and (alt is not None) and (abs(alt - prev_altitude) <= alt_epsilon):
                try:
                    seq.sensors['altitude'] = 0.0
                except Exception:
                    pass
                seq.logger.info('Rocket has landed')
                landed = True
                break
            prev_altitude = alt
            time.sleep(1)

        return True
    except Exception:
        seq.logger.exception('Error during landing sequence')
        return False
