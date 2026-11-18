import { NotImplemented } from '../components/NotImplemented';
import { PageHeader } from '../components/Page';

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
