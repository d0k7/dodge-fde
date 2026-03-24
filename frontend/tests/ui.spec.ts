import { test, expect } from '@playwright/test';

test('chat UI renders key panels', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByText('Chat with Graph')).toBeVisible();
  await expect(page.getByText('Order to Cash')).toBeVisible();

  await expect(page.getByText('Executive Summary')).toBeVisible();
  await expect(page.getByPlaceholder('Analyze anything...')).toBeVisible();
});
