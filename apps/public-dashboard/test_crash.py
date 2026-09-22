from selenium import webdriver
from selenium.webdriver.common.by import By
import time
options = webdriver.ChromeOptions()
options.add_argument('--headless')
driver = webdriver.Chrome(options=options)
driver.get('http://localhost:8000')
time.sleep(1)
driver.execute_script("go('ghg')")
time.sleep(1)
print(driver.get_log('browser'))
driver.quit()
