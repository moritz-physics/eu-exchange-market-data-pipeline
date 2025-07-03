import {test, expect} from '@playwright/test'

test('Login Demo', async ({page}) => {

    await page.goto('https://demo.applitools.com/')
    await page.pause()
    await page.getByRole('textbox', { name: 'Enter your username' }).fill('Moli')
    await page.getByRole('textbox', { name: 'Enter your password' }).fill('Applitools')
    await page.getByRole('link', { name: 'Sign in' }).click()






})