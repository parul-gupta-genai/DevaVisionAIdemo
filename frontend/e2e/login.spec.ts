import { test, expect } from '@playwright/test';

test('login page loads and can login', async ({ page }) => {
  // Navigate to login
  await page.goto('/');
  await expect(page).toHaveTitle(/DevaVisionAI/i);

  // Fill credentials
  await page.fill('input[type="email"]', 'gauriirajpoot@gmail.com');
  await page.fill('input[type="password"]', 'admin');
  
  // Click login
  await page.click('button[type="submit"]');

  // Verify dashboard loads
  await expect(page).toHaveURL('http://localhost:5173/');
  await expect(page.locator('text=Dashboard')).toBeVisible();
});
