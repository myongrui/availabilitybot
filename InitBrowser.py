from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import subprocess

command = "chrome.exe --remote-debugging-port=9222 --user-data-dir=C:/ChromeData"  
target_directory = r"C:/Program Files/Google/Chrome/Application"
result = subprocess.Popen(command, cwd=target_directory, shell=True)
