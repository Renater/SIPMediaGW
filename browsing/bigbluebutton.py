#!/usr/bin/env python

import sys
import time
import traceback
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException

args = sys.argv
dispName = args[2]
url = 'https://demo.bigbluebutton.org/'+args[1]
print("Web browsing URL: "+url, flush=True)
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

try:
    driver = webdriver.Chrome('/usr/bin/chromedriver',options=chrome_options, service_log_path='/dev/null')
    driver.get(url)

    # Accept Cookies
    try:
        element = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR,"#cookies-agree-button")))
        element.click()
    except Exception as e:
        print("Cookies banner not found", flush=True)

    # Enter name
    room = args[1].split('/')
    selector = '#_'+room[0]+'_'+room[1]+'_join_name'
    try:
        element = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR,selector)))
        all_options = element.find_elements_by_tag_name("option")
        element.send_keys(dispName)
        element.submit()
    except Exception as e:
        print("Name submit failed", flush=True)

    # Activate microphone
    try:
        element = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR,"button.jumbo--Z12Rgj4:nth-child(1)")))
        element.click()
        element = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR,"button.jumbo--Z12Rgj4:nth-child(1)")))
        element.click()
    except Exception as e:
        print("Microphone activation failed", flush=True)

    # Activate camera
    time.sleep(10)
    try:
        element = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR,".icon-bbb-video_off")))
        element.click()
        time.sleep(2)
        element = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR,".actions--15NFtQ")))
        element.click()
    except Exception as e:
        print("Camera activation failed", flush=True)

    while True:
        time.sleep(1)
        try:
            driver.title
        except WebDriverException:
            break

    driver.quit()

except Exception as e:
    traceback.print_exc(file=sys.stdout)

print("All done!")




