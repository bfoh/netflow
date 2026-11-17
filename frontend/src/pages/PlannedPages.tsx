import { NotImplemented } from '../components/NotImplemented';
import { PageHeader } from '../components/Page';

export function TopologyPage() {
  return (
    <>
      <PageHeader title="Topology Designer" description="Graph-based network design: devices, interfaces and links." />
      <NotImplemented title="The topology designer" phase="Phase 3" planned={[
        'Interactive canvas with device placement (graph model is the source of truth, not screen coordinates)',
        'Interface-to-interface links, VLAN and IP planning',
        'Validation: duplicate addresses, duplicate interface assignments, incompatible link settings',
        'Drawn links are design intent, never proof of physical connectivity',
      ]} />
    </>
  );
}

export function ProvisioningPage() {
  return (
    <>
      <PageHeader title="Provisioning Center" description="Onboarding of factory-default devices." />
      <NotImplemented title="Provisioning" phase="Phase 6 (simulation earlier)" planned={[
        'Existing management connectivity (SSH / REST / NETCONF)',
        'Serial or USB console provisioning through a local agent',
        'Vendor-supported zero-touch provisioning, tested only on isolated infrastructure',
        'Site-level provisioning agent for devices the central server cannot reach',
      ]} />
    </>
  );
}

export function FirmwarePage() {
  return (
    <>
      <PageHeader title="Firmware Manager" description="Firmware inventory, compatibility and controlled upgrades." />
      <NotImplemented title="Firmware management" phase="Phase 7" planned={[
        'Approved firmware repository with integrity (SHA-256) and vendor signature checks where supported',
        'Compatibility records and upgrade-path validation',
        'Maintenance-window approval, staging, installation, reboot monitoring and post-checks',
        'No firmware is installed on real equipment without dedicated lab validation and explicit authorization',
      ]} />
    </>
  );
}
