import { Button, Group, Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconCopy } from '@tabler/icons-react';

function copy(text: string) {
  try {
    void navigator.clipboard?.writeText(text);
  } catch {
    // no clipboard (insecure context): the text stays visible to copy by hand
  }
}

/** An error message that stays until it is closed, with a button to copy it for a colleague. */
export function showError(message: string, title = 'That did not work') {
  notifications.show({
    color: 'red', title, autoClose: false, withCloseButton: true,
    message: (
      <>
        <Text size="sm" style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{message}</Text>
        <Group justify="flex-end" mt={4}>
          <Button size="compact-xs" variant="subtle" leftSection={<IconCopy size={12} />}
            onClick={() => copy(`${title}: ${message}`)}>Copy details</Button>
        </Group>
      </>
    ),
  });
}

export function showSuccess(message: string) {
  notifications.show({ color: 'teal', message });
}
