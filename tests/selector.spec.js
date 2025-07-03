 import { test, expect } from '@playwright/test'


 test('Selectors Demo', async ({ page }) => {
    await page.goto('https://www.saucedemo.com/v1/')
    await page.pause()
    //using any object property
    await page.click('id=user-name')
    await page.locator('id=user-name').fill('Edison')
    //using CSS selector of login button
    await page.locator('#login-button').click()
    //using Xpath
    await page.locator('//*[@id="password"]').fill('Farahday')
    //sing text
    await page.locator('text=Login').click()






 });