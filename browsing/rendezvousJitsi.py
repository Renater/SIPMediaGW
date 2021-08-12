#!/usr/bin/env python

import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException

args = sys.argv
dispName = args[2]
url = 'https://rendez-vous.renater.fr/'+args[1]+'#userInfo.displayName="'+dispName+'"'
dispRes = args[3]
dispWidth = dispRes.split('x')[0]
dispHeight = dispRes.split('x')[1]

chrome_options = Options()
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--use-fake-ui-for-media-stream')
chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('--start-fullscreen')
chrome_options.add_argument('--window-size='+dispWidth+','+dispHeight)
chrome_options.add_argument('--window-position=0,0')
chrome_options.add_argument('--hide-scrollbars')
chrome_options.add_argument('--disable-notifications')
chrome_options.add_argument('--disable-logging') 
chrome_options.add_argument("--log-level=3")
chrome_options.add_experimental_option("excludeSwitches", ['enable-automation']);

driver = webdriver.Chrome('/usr/bin/chromedriver',options=chrome_options, service_log_path='/dev/null')
driver.get(url)


# Validate MOTD
element = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR,"#motd_do_not_show_again")))
element.click()

# Accept Cookies
element = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR,"#cookie_footer > section:nth-child(1) > section:nth-child(1) > section:nth-child(4)")))
element.click()

while True:
  time.sleep(1)
  try:
    driver.title
  except WebDriverException:
    break

driver.quit()

print("All done!")




