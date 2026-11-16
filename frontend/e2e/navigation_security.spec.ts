import { expect, test } from '@playwright/test'

test('saved Google sources cannot expose executable or lookalike links', async ({ page }) => {
  const urls = [
    'https://docs.google.com/spreadsheets/d/synthetic/edit#gid=0',
    'javascript:alert(1)',
    'https://docs.google.com.attacker.example/spreadsheets/d/synthetic',
  ]
  await page.route('**/connectors/sheets/sources', route => route.fulfill({
    json: {
      available: true,
      sources: urls.map((source_url, index) => ({
        id: `synthetic-${index}`, source_url, display_name: `Fuente ${index}`,
        gid: '0', sync_mode: 'manual', update_available: false, last_status: 'ok',
      })),
    },
  }))
  await page.goto('/conectores')
  const links = page.getByText('Abrir en Google', { exact: true })
  await expect(links).toHaveCount(3)
  await expect(links.nth(0)).toHaveAttribute('href', urls[0])
  expect(await links.nth(1).getAttribute('href')).toBeNull()
  expect(await links.nth(2).getAttribute('href')).toBeNull()
})
