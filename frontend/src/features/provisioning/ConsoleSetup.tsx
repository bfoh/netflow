import { Notice } from '../../components/Notice';
import { LoadingLines } from '../../components/Page';
import { useDrivers } from '../../hooks/queries';
import type { Device } from '../../types/api';
import { ArubaBootstrap } from './ArubaBootstrap';
import { CONSOLE_PLATFORMS, MODEM_PLATFORM } from './consolePlatforms';
import { ModemFirstAccess } from './ModemFirstAccess';

/** The console work of one device, whichever it is: a 2930F's console setup or the modem's
 *  first access (D-121). The same form in the console tool and inside Stage a system. */
export function ConsoleSetup({ device, back }: { device: Device; back?: { label: string; onClick: () => void } }) {
  const drivers = useDrivers();
  const driver = drivers.data?.find((d) => d.driver_id === device.driver_id);
  if (!driver) return <LoadingLines lines={4} />;
  if (!CONSOLE_PLATFORMS.has(driver.platform ?? '')) {
    return <Notice kind="settled" title="No console setup for this device">It answers at its factory address over the network.</Notice>;
  }
  return driver.platform === MODEM_PLATFORM
    ? <ModemFirstAccess key={device.id} device={device} simulated={driver.simulated} back={back} />
    : <ArubaBootstrap key={device.id} device={device} simulated={driver.simulated} back={back} />;
}
