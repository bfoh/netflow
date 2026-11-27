import type { Device, DeviceConnection } from '../../types/api';

/**
 * How UNDM reaches the device now (D-125): its bench address on the bench, its network
 * address in the network. Older answers without `connection` mean the bench.
 */
export function connectionOf(device: Device): DeviceConnection {
  return device.connection ?? {
    via: 'bench', address: device.management_address, port: device.management_port,
    driver_id: device.driver_id, capabilities: device.capabilities, problem: null,
  };
}

/** The device's system is in the network: changes (plans, console setup) are bench only. */
export const inNetwork = (device: Device) => connectionOf(device).via === 'network';
